# -*- coding: utf-8 -*-
import os
import sys
import asyncio

# Fix sys.path for proper imports
# This ensures that imports like 'from shared' work correctly
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 🔧 在任何其他導入之前初始化全局 UTF-8 編碼
from shared.utils.encoding_handler import init_all, setup_utf8_logging
init_all()

import discord
from discord.ext import commands, tasks
from discord.ext.commands import ExtensionError
from datetime import datetime
from dotenv import load_dotenv
from shared.utils.bot_status import build_discord_activity
from watchdog.events import FileSystemEventHandler
import logging

# ============================================================
# 日誌配置 (使用全局 UTF-8 編碼處理)
# ============================================================
logger = setup_utf8_logging(__name__, logging.INFO)

# 減少 discord 庫的日誌噪音（只顯示警告及以上）
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)
discord_webhook_logger = logging.getLogger('discord.webhook')
discord_webhook_logger.setLevel(logging.WARNING)

# ============================================================
# 文件日誌輔助函數（用於調試 systemd 中的輸出問題）
# ============================================================
try:
    import syslog
    HAS_SYSLOG = True
except ImportError:
    # Windows 上沒有 syslog
    HAS_SYSLOG = False

LOG_FILE = "/tmp/bot-debug.log"

def file_log(msg):
    """寫入日誌到檔案、syslog 並同時調用 print"""
    try:
        # 確保字符串是 UTF-8 編碼的 (防止亂碼)
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', errors='replace')
        output = f"[FILE_LOG] {msg}".encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        print(output, flush=True)
        sys.stdout.flush()
    except Exception as e:
        pass
    
    try:
        # 寫入文件
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            f.flush()
    except (IOError, OSError):
        pass
    # 寫入 syslog
    if HAS_SYSLOG:
        try:
            syslog.syslog(syslog.LOG_INFO, f"[BOT_DEBUG] {msg}")
        except OSError:
            pass
    sys.stdout.flush()

def _get_memory_usage():
    """取得當前進程的內存使用情況"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        return f"{memory_mb:.1f}MB"
    except (ImportError, OSError):
        return "unknown"

# dashboard helpers
# add_log removed; status_dashboard handles logs internally
from status_dashboard import initialize_dashboard, load_message_ids

# 全局變量：GCP Metrics 數據採集器
_metrics_collector = None
_metrics_collector_task = None

# ============================================================
# 配置區 - 根據不同 BOT 修改此區域
# ============================================================
BOT_NAME = "Bot"  # 可改為 "Shop" 或 "UI"
BOT_TYPE = "bot"  # 狀態主題: bot / shopbot / uibot (須與 BOT_CONFIG 匹配)
BOT_PREFIX = "DISCORD"  # 環境變數前綴: DISCORD / SHOP_DISCORD / UI_DISCORD
COMMANDS_DIR = "cogs/common"  # 指令目錄: cogs/common / cogs/shop / cogs/ui (已重構)
VERSION = "1.0.0"
EMOJI = "🤖"  # Bot 代表符號: 🤖 / 🛒 / 🎨

# ============================================================
# 環境變數載入
# ============================================================
load_dotenv()
STAGE = os.getenv("STAGE", "dev")
TOKEN = os.getenv(f"{BOT_PREFIX}_BOT_TOKEN")
GUILD_ID = os.getenv(f"{BOT_PREFIX}_GUILD_ID")
SYS_CHANNEL_ID_STR = os.getenv(f"{BOT_PREFIX}_SYS_CHANNEL_ID", "0")
SYS_CHANNEL_ID = int(SYS_CHANNEL_ID_STR) if SYS_CHANNEL_ID_STR else 0

if not TOKEN:
    raise RuntimeError(f"❌ {BOT_PREFIX}_BOT_TOKEN 未在 .env 中設定")

# ============================================================
# Discord 客戶端初始化
# ============================================================
guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True
intents.members = True
intents.voice_states = True  # needed to receive on_voice_state_update events

client = commands.Bot(command_prefix="!", help_command=None, intents=intents)

# ============================================================
# 模組載入系統
# ============================================================
# 防止重複載入的鎖
_reload_lock = asyncio.Lock()

# 追蹤 on_ready 是否被觸發
_on_ready_called = False
_on_ready_check_task = None
_pending_reloads = set()

async def find_and_load_extensions(base_path, package_prefix="", bot_client=None):
    """遞歸搜尋並載入所有 Python 擴展（只加載有效的 Cog）。

    為了避免 `views` 目錄被當成 Cog 而引發 “has no setup
    function” 的錯誤，任何 package_prefix 以 "views" 結尾的
    目錄都會直接跳過掃描。
    """
    # 如果我們已經在某個 views 子包內，就不要繼續遞歸，
    # views 裡面只含 Discord View/Modal 類，沒有 Cog。
    if package_prefix.split('.')[-1] == 'views':
        return []

    loaded_extensions = []
    
    # 列出不應該被加載為 Cog 的模組
    excluded_modules = {
        'cannabis_farming', 'cannabis_merchant_view', 'cannabis_merchant_view_v2',
        'cannabis_config', 'database', 'config', 'views', 'views_base',
        'paperdoll_system', 'gambling', 'role_expiry_manager', 'locker_panel',
        'locker_events',  # 事件定義模組，不是 Cog
        'leaderboard_manager',  # 工具模組：由 kcoin Cog 導入使用，不是獨立 Cog
        'uibody',  # UserPanel 由 uibody.setup() 統一管理
    }
    
    for item in sorted(os.listdir(base_path)):
        item_path = os.path.join(base_path, item)
        
        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            sub_package = f"{package_prefix}.{item}" if package_prefix else item
            sub_extensions = await find_and_load_extensions(item_path, sub_package, bot_client)
            loaded_extensions.extend(sub_extensions)
        
        elif item.endswith(".py") and item != "__init__.py":
            module_name = item[:-3]
            
            # 跳過不應該被加載為 Cog 的模組
            if module_name in excluded_modules:
                continue
            
            ext_name = f"{package_prefix}.{module_name}" if package_prefix else module_name
            
            try:
                await bot_client.load_extension(ext_name)
                loaded_extensions.append(ext_name)
                print(f"✅ 載入成功: {ext_name}")
            except Exception as e:
                import traceback
                print(f"❌ 載入失敗: {ext_name}")
                print(f"   錯誤: {e}")
                print(f"   Traceback:")
                traceback.print_exc()
    
    return loaded_extensions

async def setup_modules(bot_client):
    """載入所有模組"""
    file_log("[setup_modules] 函數開始")
    
    # 轉換路徑為包名（cogs/common → cogs.common）
    package_prefix = COMMANDS_DIR.replace('/', '.')
    
    # 從父目錄開始計算路徑（cogs/common -> cogs_base_path, common_subdir）
    if '/' in COMMANDS_DIR:
        parts = COMMANDS_DIR.split('/')
        # 從 bots/ 向上一級到根目錄
        root_path = os.path.dirname(os.path.dirname(__file__))
        full_path = os.path.join(root_path, *parts)
    else:
        full_path = os.path.join(os.path.dirname(__file__), COMMANDS_DIR)
    
    if not os.path.exists(full_path):
        os.makedirs(full_path)
        init_file = os.path.join(full_path, "__init__.py")
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write(f"# {BOT_NAME} Bot Commands Module\n")
        file_log(f"[setup_modules] 建立目錄: {full_path}")
        return []
    
    file_log(f"[setup_modules] 調用 find_and_load_extensions() - 包: {package_prefix}")
    
    extensions = await find_and_load_extensions(full_path, package_prefix, bot_client)
    
    file_log(f"[setup_modules] find_and_load_extensions() 返回 {len(extensions)} 擴展")
    file_log(f"[setup_modules] 函數完成，共 {len(extensions)} 個擴展")
    
    return extensions

async def reload_extension_on_change(ext_name):
    """熱重載擴展（防止重複觸發）"""
    async with _reload_lock:
        # 如果已經在等待重載，跳過
        if ext_name in _pending_reloads:
            return
        
        _pending_reloads.add(ext_name)
        
        try:
            # 等待一小段時間，避免檔案系統多次觸發
            await asyncio.sleep(0.5)
            
            await client.reload_extension(ext_name)
            print(f"[RELOAD] {ext_name}")
            
            synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
            print(f"[SYNC] {len(synced)} commands synced")
        except (ExtensionError, ImportError) as e:
            print(f"[ERROR] Reload failed: {ext_name} - {e}")
        finally:
            _pending_reloads.discard(ext_name)

# ============================================================
# 檔案監控系統
# ============================================================
class FileEventHandler(FileSystemEventHandler):
    def __init__(self, loop):
        self.loop = loop
        self.last_modified = {}

    def on_modified(self, event): self.handle(event)
    def on_created(self, event): self.handle(event)
    def on_moved(self, event): self.handle(event)

    def handle(self, event):
        if not event.is_directory and event.src_path.endswith(".py"):
            # 排除 __pycache__ 目錄中的文件
            if "__pycache__" in event.src_path:
                return
                
            filename = os.path.basename(event.src_path)
            if filename == "__init__.py":
                return
            
            # 防止重複觸發（1秒內同一檔案只處理一次）
            import time
            current_time = time.time()
            if event.src_path in self.last_modified:
                if current_time - self.last_modified[event.src_path] < 1.0:
                    return
            self.last_modified[event.src_path] = current_time
            
            rel_path = os.path.relpath(
                event.src_path, 
                os.path.join(os.path.dirname(__file__), COMMANDS_DIR)
            )
            module_path = rel_path.replace(os.sep, ".")[:-3]
            ext_name = f"{COMMANDS_DIR}.{module_path}"
            
            asyncio.run_coroutine_threadsafe(
                reload_extension_on_change(ext_name), 
                self.loop
            )

# ============================================================
# 日誌更新任務（每 15 秒更新一次）
# ============================================================
# 日誌更新任務現在由 status_dashboard.py 的全域任務處理

# ============================================================
# 狀態更新任務
# ============================================================
# ============================================================
# 定期清理過期角色的任務 (每 1 小時檢查一次)
# ============================================================
@tasks.loop(hours=6)
async def cleanup_expired_roles_loop():
    """定期檢查並移除過期的臨時角色（每 6 小時執行一次）"""
    try:
        from cogs.shop.role_expiration_manager import get_manager as get_expiration_manager
        manager = get_expiration_manager()
        removed_count = await manager.cleanup_expired_roles(client)
        if removed_count > 0:
            print(f"[CLEANUP] ✅ 已移除 {removed_count} 個過期角色")
        else:
            print(f"[CLEANUP] 檢查完成，無過期角色")
    except (ImportError, AttributeError) as e:
        print(f"[CLEANUP] ❌ 清理失敗: {e}")

@cleanup_expired_roles_loop.before_loop
async def before_cleanup_expired_roles():
    """等待 Bot 準備完成"""
    await client.wait_until_ready()

@tasks.loop(minutes=10)
async def update_status():
    """定期更新 Bot 狀態（日誌更新由 status_dashboard.py 10 分鐘定時任務負責）"""
    try:
        # 添加超時防護，防止長時間掛起
        activity = build_discord_activity(BOT_TYPE)
        await asyncio.wait_for(client.change_presence(activity=activity), timeout=10.0)
        
        # 日誌更新已移交給 status_dashboard.py 的獨立 10 分鐘定時任務
        # 此函式現在只負責更新 bot 的狀態活動
    except asyncio.TimeoutError:
        file_log(f"[ERROR] Status update timeout - presence change exceeded 10s")
        print(f"[ERROR] Status update timeout")
    except (ImportError, OSError, RuntimeError) as e:
        file_log(f"[ERROR] Failed to update status: {e}")
        print(f"[ERROR] Failed to update status: {e}")

@update_status.before_loop
async def before_update_status():
    """等待 Bot 準備完成"""
    await client.wait_until_ready()

# ============================================================
# 事件監視函數
# ============================================================
async def _check_ready_timeout():
    """監視 ready 狀態，如果超時就手動調用 on_ready()"""
    global _on_ready_called, _on_ready_check_task
    file_log("[READY_MONITOR] 開始監視 ready 狀態（10 秒超時）")
    
    for i in range(10):
        await asyncio.sleep(1)
        file_log(f"[READY_MONITOR] {i+1}s - ready={client.is_ready()} - on_ready_called={_on_ready_called}")
        
        if _on_ready_called:
            file_log("[READY_MONITOR] on_ready 已被正常觸發")
            return
    
    # 如果 10 秒後 on_ready 還沒被觸發，手動調用
    if not _on_ready_called:
        file_log("[READY_MONITOR] 10 秒超時，on_ready 未被觸發，嘗試手動調用")
        try:
            await on_ready()
        except Exception as e:
            file_log(f"[READY_MONITOR] 手動調用 on_ready 失敗: {e}")

# ============================================================
# Bot 事件處理
# ============================================================
@client.event
async def on_voice_state_update(member, before, after):
    print(f"[global] voice_state_update member={member.id} before={getattr(before.channel, 'id', None)} after={getattr(after.channel, 'id', None)}", flush=True)

@client.event
async def on_connect():
    global _on_ready_check_task
    _on_ready_check_task = None  # 重置
    file_log("=== ON_CONNECT CALLED ===")
    print("[DISCORD] gateway connected", flush=True)
    
    # 启动 ready 状态检查
    if _on_ready_check_task is None:
        _on_ready_check_task = asyncio.create_task(_check_ready_timeout())

@client.event
async def on_disconnect():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_log(f"[{timestamp}] === ON_DISCONNECT CALLED === (Memory: {_get_memory_usage()})")
    print(f"[DISCORD] gateway disconnected at {timestamp}", flush=True)

@client.event
async def on_resumed():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_log(f"[{timestamp}] === ON_RESUMED CALLED === (Memory: {_get_memory_usage()})")
    # when the gateway reconnects, our periodic tasks may have sent edits
    # while the connection was down and Discord might not deliver them to
    # clients.  force an immediate refresh of both log and metrics embeds so
    # that the dashboard doesn't appear frozen after a disconnect.
    try:
        from status_dashboard import update_dashboard_logs
        # bot type is defined at module level
        bot_type = BOT_TYPE
        bot_inst = client
        # update logs embed
        await update_dashboard_logs(bot_inst, bot_type)
        print("[on_resumed] forced log embed refresh")
    except (ImportError, OSError, RuntimeError) as e:
        print(f"[on_resumed] log refresh failed: {e}")
    # metrics 功能已被禁用，移除相關代碼

@client.event
async def on_ready():
    """Bot 啟動完成"""
    global _on_ready_called, _metrics_collector, _metrics_collector_task
    
    # 立即寫入標記來驗證 on_ready 被調用
    file_log("=== ON_READY CALLED ===")
    _on_ready_called = True
    
    # 調試：打印到 journalctl 以確保追蹤執行
    debug1 = "[ON_READY_DEBUG] Starting on_ready execution..."
    print(debug1, flush=True)
    sys.stdout.flush()
    
    stage_text = "DEV" if STAGE != "prod" else "PROD"
    print("[bot] on_ready triggered, guilds:", [(g.id, g.name) for g in client.guilds], flush=True)
    # enumerate voice channels in each guild the bot is actually in
    for g in client.guilds:
        print(f"[bot] guild {g.id} ({g.name}) voice channels:")
        for ch in g.voice_channels:
            print(f"  {ch.id} {ch.name}")
        print(f"[bot] guild {g.id} ({g.name}) all channels:")
        for ch in g.channels:
            print(f"  {ch.id} {ch.name} ({type(ch).__name__})")
    print("[bot] guild variable type", type(guild), guild)
    # try to resolve real guild object from client cache
    real = None
    if guild:
        real = client.get_guild(int(guild.id))
        print("[bot] real guild from cache:", real)
    if real:
        print("[bot] voice channels in real guild:")
        for ch in real.voice_channels:
            print(f"  {ch.id} {ch.name}")
    else:
        print("[bot] real guild not found in cache")
    
    try:
        # 執行 DB migration（置物櫃事件驅動系統）
        try:
            from tools.migrate_locker_event_system import migrate_locker_event_columns
            migrate_locker_event_columns()
        except (ImportError, OSError) as e:
            print(f"⚠️  DB migration 失敗: {e}")
        
        # 清除舊指令
        if guild and STAGE != "prod":
            await client.tree.clear_commands(guild=guild)
        
        # 載入模組 - 添加分步驟日誌
        try:
            file_log("[SETUP_TRACE] 準備調用 setup_modules()...")
            
            debug_setup = "[SETUP] About to call setup_modules()..."
            file_log(debug_setup)
            
            loaded_extensions = await setup_modules(client)
            
            success_setup = f"[SETUP] setup_modules() completed, loaded {len(loaded_extensions)} extensions"
            file_log(success_setup)
        except Exception as e:
            error_setup = f"[SETUP] ❌ setup_modules() failed: {e}"
            file_log(error_setup)
            import traceback
            traceback.print_exc()
            raise
        
        # ⭐ 註冊所有永久視圖（timeout=None）
        # 這是解決按鈕交互失敗的關鍵步驟
        try:
            from shared.utils.view_registry import register_all_permanent_views
            register_all_permanent_views(client)
        except Exception as e:
            file_log(f"❌ 視圖註冊失敗: {e}")
            print(f"❌ 視圖註冊失敗: {e}")
        
        # 同步指令
        synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        
        # 前綴指令
        prefix_cmds = list(client.commands)
        
        # ============================================================
        # 構建單一完整輸出（避免多次調用 print）
        # ============================================================
        lines = [
            "=" * 60,
            f"{EMOJI} {BOT_NAME} Bot 啟動完成 | v{VERSION} ({stage_text})",
            "=" * 60,
            f"[STATS] {len(loaded_extensions)} Extensions | {len(synced)} Slash Commands | {len(prefix_cmds)} Prefix Commands"
        ]
        
        # 已載入擴展（緊湊格式）
        if loaded_extensions:
            lines.append("")
            lines.append("[EXTENSIONS] Loaded:")
            ext_names = [ext.split('.')[-1] for ext in loaded_extensions]
            # 每行顯示 5 個擴展
            for i in range(0, len(ext_names), 5):
                batch = ext_names[i:i+5]
                lines.append(f"   {' | '.join(batch)}")
        
        # Slash 指令（緊湊格式）
        if synced:
            lines.append("")
            lines.append("[SLASH_COMMANDS] Registered:")
            cmd_names = [f"/{cmd.name}" for cmd in synced]
            # 每行顯示 6 個指令
            for i in range(0, len(cmd_names), 6):
                batch = cmd_names[i:i+6]
                lines.append(f"   {' '.join(batch)}")
        
        # 前綴指令（緊湊格式）
        if prefix_cmds:
            lines.append("")
            lines.append("[PREFIX_COMMANDS] Registered:")
            cmd_names = [f"!{cmd.name}" for cmd in prefix_cmds]
            lines.append(f"   {' '.join(cmd_names)}")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"[SUCCESS] {client.user.name} Ready")
        lines.append("=" * 60)
        
        # 打印啟動訊息
        try:
            print("\n".join(lines))
        except (UnicodeEncodeError, OSError, RuntimeError) as e:
            print(f"[DEBUG] Failed to print startup message: {e}")
        
        # 設定初始狀態
        try:
            activity = build_discord_activity(BOT_TYPE)
            await client.change_presence(activity=activity)
            print("[DEBUG] Status updated")
        except (ImportError, OSError, RuntimeError) as e:
            print(f"[DEBUG] Failed to update status: {e}")
        
        # ============================================================
        # 清理過期的臨時角色（變色龍披風、進階組員等）
        # ============================================================
        try:
            from cogs.shop.role_expiration_manager import get_manager as get_expiration_manager
            manager = get_expiration_manager()
            print(f"[BOT] 機器人啟動時執行過期角色清理...")
            removed_count = await manager.cleanup_expired_roles(client)
            print(f"[BOT] ✅ 啟動時清理完成：移除 {removed_count} 個過期角色")
        except (ImportError, AttributeError, RuntimeError) as e:
            print(f"[BOT] ❌ 清理過期角色失敗: {e}")
        
        # ============================================================
        # 初始化監控儀表板及日誌系統（簡化版本 - 僅日誌）
        # ============================================================
        try:
            # 寫入診斷日誌到文件
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now()}] 開始初始化 dashboard\n")
                df.flush()
            
            print("[BOT] 開始初始化 dashboard...", flush=True)
            load_message_ids("bot")
            
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now()}] 調用 initialize_dashboard\n")
                df.flush()
            
            dashboard_ready = await initialize_dashboard(client, "bot")
            
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now()}] 返回 dashboard_ready={dashboard_ready}\n")
                df.flush()
            
            if dashboard_ready:
                print("[DASHBOARD] Log system initialized", flush=True)
                # 立即執行一次日誌更新以確保 Discord 能看到日誌
                print("[BOT] 執行初始日誌更新...", flush=True)
                try:
                    from status_dashboard import update_dashboard_logs
                    await update_dashboard_logs(client, "bot")
                    print("[BOT] 初始日誌更新完成", flush=True)
                except Exception as update_error:
                    print(f"[BOT] 初始日誌更新失敗: {update_error}", flush=True)
            else:
                print("[WARNING] Dashboard 初始化返回 False", flush=True)
        except Exception as e:
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now()}] 異常: {e}\n")
                import traceback
                traceback.print_exc(file=df)
                df.flush()
            
            print(f"[WARNING] Failed to initialize dashboard: {e}", flush=True)
            import traceback
            traceback.print_exc()


        # 啟動狀態更新任務
        if not update_status.is_running():
            update_status.start()
        
        # 啟動角色過期清理任務
        if not cleanup_expired_roles_loop.is_running():
            cleanup_expired_roles_loop.start()
            print("[SCHEDULER] ✅ 角色過期清理任務已啟動 (每 1 小時檢查一次)")
        
    except (ImportError, OSError, RuntimeError) as e:
        # 錯誤也使用單一 print
        error_msg = f"[ERROR] Initialization failed: {e}\n{'=' * 60}"
        print(error_msg)
# ============================================================
# 主程序入口
# ============================================================
async def main():
    """主程序

    因為網路不穩、Discord 斷線等原因，client.start 可能會在中途拋出
    例外並退出。將整個啟動包在一個 while 迴圈中，遇到錯誤時等待幾秒
    再重試；只有遇到 KeyboardInterrupt 或 LoginFailure 才會跳出迴圈。
    """
    # 立即寫入啟動標記到檔案
    file_log("=== BOT MAIN START ===")
    
    reconnect_count = 0
    max_backoff = 60  # 最大退避 60 秒

    try:
        while True:
            try:
                reconnect_count = 0  # 重置重連計數
                file_log("=== STARTING CLIENT WITH TOKEN ===")
                async with client:
                    file_log("=== CLIENT CONTEXT OPENED, CALLING client.start() ===")
                    await client.start(TOKEN)
            except KeyboardInterrupt:
                print(f"\n[SHUTDOWN] {BOT_NAME} Bot stopped")
                break
            except discord.LoginFailure:
                print("[ERROR] Invalid Discord Token")
                file_log("[FATAL] Invalid Discord Token")
                break
            except (discord.GatewayNotFound, discord.HTTPException, OSError) as e:
                reconnect_count += 1
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                error_msg = f"[{timestamp}] [ERROR] Run failed (attempt {reconnect_count}): {e}"
                file_log(error_msg)
                print(error_msg)
            
            # 指數退避：5s, 10s, 20s, 40s, 60s, 60s, ...
            wait_time = min(5 * (2 ** min(reconnect_count - 1, 0)), max_backoff)
            wait_time = max(5, wait_time)  # 最小 5 秒
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            retry_msg = f"[{timestamp}] [MAIN] 連線中斷，{wait_time}秒後重試 (嘗試 #{reconnect_count})"
            file_log(retry_msg)
            print(retry_msg)
            await asyncio.sleep(wait_time)
    finally:
        if update_status.is_running():
            update_status.stop()
        # if observer is defined:
        #     observer.stop()
        #     observer.join()

if __name__ == "__main__":
    try:
        file_log("=== BOT SCRIPT START ===")
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except (ImportError, RuntimeError, OSError) as e:
        file_log(f"[FATAL] Startup failed: {e}")
        print(f"[FATAL] Startup failed: {e}", flush=True)
        sys.exit(1)
