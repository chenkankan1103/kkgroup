import os
import sys
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime
from dotenv import load_dotenv
from bot_status import build_discord_activity

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
        except (OSError, Exception):
            pass
    
    # 同時 print
    print(msg, flush=True)
    sys.stdout.flush()

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
COMMANDS_DIR = "commands"  # 指令目錄: commands / shop_commands / uicommands
VERSION = "1.0.0"
EMOJI = "🤖"  # Bot 代表符號: 🤖 / 🛒 / 🎨

# ============================================================
# 環境變數載入
# ============================================================
load_dotenv()
STAGE = os.getenv("STAGE", "dev")
TOKEN = os.getenv(f"{BOT_PREFIX}_BOT_TOKEN")
GUILD_ID = os.getenv(f"{BOT_PREFIX}_GUILD_ID")
SYS_CHANNEL_ID = int(os.getenv(f"{BOT_PREFIX}_SYS_CHANNEL_ID", 0))

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

async def find_and_load_extensions(base_path, package_prefix="", client=None):
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
        'uibody',  # UserPanel 由 uibody.setup() 統一管理
    }
    
    for item in sorted(os.listdir(base_path)):
        item_path = os.path.join(base_path, item)
        
        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            sub_package = f"{package_prefix}.{item}" if package_prefix else item
            sub_extensions = await find_and_load_extensions(item_path, sub_package, client)
            loaded_extensions.extend(sub_extensions)
        
        elif item.endswith(".py") and item != "__init__.py":
            module_name = item[:-3]
            
            # 跳過不應該被加載為 Cog 的模組
            if module_name in excluded_modules:
                continue
            
            ext_name = f"{package_prefix}.{module_name}" if package_prefix else module_name
            
            try:
                await client.load_extension(ext_name)
                loaded_extensions.append(ext_name)
            except Exception as e:
                print(f"❌ 載入失敗: {ext_name} - {e}")
    
    return loaded_extensions

async def setup_modules(client):
    """載入所有模組"""
    full_path = os.path.join(os.path.dirname(__file__), COMMANDS_DIR)
    
    if not os.path.exists(full_path):
        os.makedirs(full_path)
        init_file = os.path.join(full_path, "__init__.py")
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write(f"# {BOT_NAME} Bot Commands Module\n")
        return []
    
    return await find_and_load_extensions(full_path, COMMANDS_DIR, client)

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
            print(f"🔄 已重載: {ext_name}")
            
            synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
            print(f"✓ 同步完成: {len(synced)} 個指令")
        except Exception as e:
            print(f"❌ 重載失敗: {ext_name} - {e}")
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
# 定期清理過期角色的任務 (每 5 分鐘檢查一次)
# ============================================================
@tasks.loop(minutes=5)
async def cleanup_expired_roles_loop():
    """定期檢查並移除過期的臨時角色"""
    try:
        from shop_commands.role_expiration_manager import get_manager as get_expiration_manager
        manager = get_expiration_manager()
        removed_count = await manager.cleanup_expired_roles(client)
        if removed_count > 0:
            print(f"[RoleExpiration] ✅ 定期檢查移除了 {removed_count} 個過期角色")
    except Exception as e:
        print(f"[RoleExpiration] ⚠️ 定期清理失敗: {e}")

@cleanup_expired_roles_loop.before_loop
async def before_cleanup_expired_roles():
    """等待 Bot 準備完成"""
    await client.wait_until_ready()

@tasks.loop(minutes=2)
async def update_status():
    """定期更新 Bot 狀態和日誌 Embed"""
    try:
        activity = build_discord_activity(BOT_TYPE)
        await client.change_presence(activity=activity)
        
        # 每 2 分鐘更新一次日誌 embed
        from status_dashboard import update_dashboard_logs
        await update_dashboard_logs(client, BOT_TYPE)
    except Exception as e:
        print(f"❌ 狀態更新失敗: {e}")

@update_status.before_loop
async def before_update_status():
    """等待 Bot 準備完成"""
    await client.wait_until_ready()

# ============================================================
# 事件監視函數
# ============================================================
async def _check_ready_timeout():
    """監視 ready 狀態，如果超時就手動調用 on_ready()"""
    global _on_ready_called
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
    file_log("=== ON_CONNECT CALLED ===")
    print("[DISCORD] gateway connected", flush=True)
    
    # 启动 ready 状态检查
    if _on_ready_check_task is None:
        _on_ready_check_task = asyncio.create_task(_check_ready_timeout())

@client.event
async def on_disconnect():
    file_log("=== ON_DISCONNECT CALLED ===")
    print("[DISCORD] gateway disconnected", flush=True)

@client.event
async def on_resumed():
    file_log("=== ON_RESUMED CALLED ===")
    # when the gateway reconnects, our periodic tasks may have sent edits
    # while the connection was down and Discord might not deliver them to
    # clients.  force an immediate refresh of both log and metrics embeds so
    # that the dashboard doesn't appear frozen after a disconnect.
    try:
        from status_dashboard import update_dashboard_logs, get_bot_instance
        # bot type is defined at module level
        bot_type = BOT_TYPE
        bot_inst = client
        # update logs embed
        await update_dashboard_logs(bot_inst, bot_type)
        print("[on_resumed] forced log embed refresh")
    except Exception as e:
        print(f"[on_resumed] log refresh failed: {e}")
    try:
        # metrics update task is not directly callable, but we can trigger
        # a one-shot by creating a temporary loop and running it once.  the
        # easiest option is to import create_metrics_update_task and run the
        # underlying function directly.
        from status_dashboard import create_metrics_update_task
        loop = await create_metrics_update_task(bot_type)
        # loop._function is the coroutine that actually does the work
        if hasattr(loop, '_function'):
            await loop._function()
            print("[on_resumed] forced metrics embed refresh")
    except Exception as e:
        print(f"[on_resumed] metrics refresh failed: {e}")

@client.event
async def on_ready():
    """Bot 啟動完成"""
    global _on_ready_called
    
    # 立即寫入標記來驗證 on_ready 被調用
    file_log("=== ON_READY CALLED ===")
    _on_ready_called = True
    
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
        except Exception as e:
            print(f"⚠️  DB migration 失敗: {e}")
        
        # 清除舊指令
        if guild and STAGE != "prod":
            await client.tree.clear_commands(guild=guild)
        
        # 載入模組
        loaded_extensions = await setup_modules(client)
        
        # 明確載入 uibody 模組（UserPanel 和 LockerEventListenerCog）
        # try:
        #     from uicommands import uibody
        #     await uibody.setup(client)
        #     print("✅ uibody 模組已明確加載")
        # except Exception as e:
        #     print(f"❌ uibody 模組加載失敗: {e}")
        #     import traceback
        #     traceback.print_exc()
        
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
            f"📊 統計: 📦 {len(loaded_extensions)} 擴展 | ⚡ {len(synced)} Slash指令 | 🔧 {len(prefix_cmds)} 前綴指令"
        ]
        
        # 載入失敗的擴展（如果有）
        failed_extensions = []
        
        # 已載入擴展（緊湊格式）
        if loaded_extensions:
            lines.append("")
            lines.append("📦 已載入擴展:")
            ext_names = [ext.split('.')[-1] for ext in loaded_extensions]
            # 每行顯示 5 個擴展
            for i in range(0, len(ext_names), 5):
                batch = ext_names[i:i+5]
                lines.append(f"   {' | '.join(batch)}")
        
        # Slash 指令（緊湊格式）
        if synced:
            lines.append("")
            lines.append("⚡ Slash 指令:")
            cmd_names = [f"/{cmd.name}" for cmd in synced]
            # 每行顯示 6 個指令
            for i in range(0, len(cmd_names), 6):
                batch = cmd_names[i:i+6]
                lines.append(f"   {' '.join(batch)}")
        
        # 前綴指令（緊湊格式）
        if prefix_cmds:
            lines.append("")
            lines.append("🔧 前綴指令:")
            cmd_names = [f"!{cmd.name}" for cmd in prefix_cmds]
            lines.append(f"   {' '.join(cmd_names)}")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"✅ {client.user.name} 已就緒")
        lines.append("=" * 60)
        
        # 打印啟動訊息
        try:
            print("\n".join(lines))
        except Exception as e:
            print(f"[DEBUG] 打印啟動訊息失敗: {e}")
        
        # 設定初始狀態
        try:
            activity = build_discord_activity(BOT_TYPE)
            await client.change_presence(activity=activity)
            print("[DEBUG] 狀態已更新")
        except Exception as e:
            print(f"[DEBUG] 狀態更新失敗: {e}")
            import traceback
            traceback.print_exc()
        
        # ============================================================
        # 清理過期的臨時角色（變色龍披風、進階組員等）
        # ============================================================
        try:
            from shop_commands.role_expiration_manager import get_manager as get_expiration_manager
            manager = get_expiration_manager()
            removed_count = await manager.cleanup_expired_roles(client)
            if removed_count > 0:
                print(f"✅ 啟動清理: 已移除 {removed_count} 個過期角色")
        except Exception as e:
            print(f"⚠️ 角色過期清理失敗: {e}")
            import traceback
            traceback.print_exc()
        
        # ============================================================
        # 初始化監控儀表板及日誌系統（簡化版本 - 僅日誌）
        # ============================================================
        try:
            load_message_ids("bot")
            dashboard_ready = await initialize_dashboard(client, "bot")
            if dashboard_ready:
                print("✅ 日誌系統已初始化")
        except Exception as e:
            print(f"⚠️ 儀表板初始化失敗: {e}")

        # ============================================================
        # 啟動 GCP Metrics 數據採集器（如果 BOT_TYPE == "bot"）
        # ============================================================
        global _metrics_collector, _metrics_collector_task
        
        if BOT_TYPE == "bot" and _metrics_collector is None:  # 只在主 bot 中啟動一次
            try:
                from metrics_data_collector import MetricsDataCollector
                
                print("[bot] 初始化 GCP Metrics 數據採集器...")
                _metrics_collector = MetricsDataCollector(project_id="kkgroup")
                
                # 啟動後台採集任務（每 30 分鐘運行一次）
                if _metrics_collector_task is None:
                    _metrics_collector_task = asyncio.create_task(
                        _metrics_collector.start_background_collection(interval_minutes=30)
                    )
                    print("[bot] ✅ GCP Metrics 數據採集器已啟動（每 30 分鐘採集一次）")
                
            except ImportError:
                print("[bot] ⚠️ MetricsDataCollector 不可用（metrics_data_collector.py 不存在）")
            except Exception as e:
                print(f"[bot] ⚠️ 無法啟動 Metrics 數據採集器: {e}")
                import traceback
                traceback.print_exc()

        # 啟動狀態更新任務
        if not update_status.is_running():
            update_status.start()
        
        # 啟動角色過期清理任務
        if not cleanup_expired_roles_loop.is_running():
            cleanup_expired_roles_loop.start()
            print("✅ 角色過期清理任務已啟動 (每 5 分鐘檢查一次)")
        
    except Exception as e:
        # 錯誤也使用單一 print
        error_msg = f"❌ 初始化失敗: {e}\n{'=' * 60}"
        print(error_msg)
        import traceback
        traceback.print_exc()
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
    
    loop = asyncio.get_event_loop()
    
    # 暫時禁用檔案監控以避免重載問題
    # observer = Observer()
    # 
    # commands_path = os.path.join(os.path.dirname(__file__), COMMANDS_DIR)
    # 
    # if not os.path.exists(commands_path):
    #     os.makedirs(commands_path)
    #     init_file = os.path.join(commands_path, "__init__.py")
    #     with open(init_file, 'w', encoding='utf-8') as f:
    #         f.write(f"# {BOT_NAME} Bot Commands Module\n")
    # 
    # observer.schedule(
    #     FileEventHandler(loop),
    #     path=commands_path,
    #     recursive=True
    # )
    # observer.start()

    try:
        while True:
            try:
                file_log(f"=== STARTING CLIENT WITH TOKEN ===")
                async with client:
                    file_log("=== CLIENT CONTEXT OPENED, CALLING client.start() ===")
                    await client.start(TOKEN)
            except KeyboardInterrupt:
                print(f"\n👋 {BOT_NAME} Bot 已停止")
                break
            except discord.LoginFailure:
                print("❌ Discord Token 無效")
                break
            except Exception as e:
                print(f"[MAIN] 運行失敗: {e}")
                import traceback
                traceback.print_exc()
            # 自動重連
            print("[MAIN] 連線中斷，5秒後重試")
            await asyncio.sleep(5)
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
    except Exception as e:
        file_log(f"❌ 啟動失敗: {e}")
        print(f"❌ 啟動失敗: {e}", flush=True)
        sys.exit(1)
