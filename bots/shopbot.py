# -*- coding: utf-8 -*-
import os
import sys
import asyncio

# Fix sys.path for proper imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# 初始化全局 UTF-8 編碼
from shared.utils.encoding_handler import init_all, setup_utf8_logging

init_all()

import discord
from discord.ext import commands, tasks
from datetime import datetime
from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler

from shared.utils.bot_status import build_discord_activity
from shared.utils.mutual_rescue import ensure_mutual_rescue_monitor
from shared.db.feature_usage import track_discord_interaction
from shared.db.async_adapter import init_async_db, close_async_db
from status_dashboard import (
    initialize_dashboard,
    load_message_ids,
    update_dashboard_logs,
)
import syslog
import logging

# 設置日誌
logger = setup_utf8_logging(__name__, logging.INFO)

# ============================================================
# file_log 函數定義（必須有）
# ============================================================
try:
    import syslog

    HAS_SYSLOG = True
except ImportError:
    # Windows 上沒有 syslog
    HAS_SYSLOG = False

LOG_FILE = "/tmp/shopbot-debug.log"


def file_log(msg):
    """寫入日誌到檔案、syslog 並同時調用 print"""
    try:
        # 確保字符串是 UTF-8 編碼的 (防止亂碼)
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", errors="replace")
        output = f"[FILE_LOG] {msg}".encode("utf-8", errors="replace").decode(
            "utf-8", errors="replace"
        )
        print(output, flush=True)
        sys.stdout.flush()
    except Exception:
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
            syslog.syslog(syslog.LOG_INFO, f"[SHOPBOT_DEBUG] {msg}")
        except OSError:
            pass
    sys.stdout.flush()


# ============================================================
# 配置區 - 根據不同 BOT 修改此區域
# ============================================================
BOT_NAME = "Shop"  # 可改為 "Shop" 或 "UI"
BOT_TYPE = "shopbot"  # 狀態主題: bot / shopbot / uibot (須與 BOT_CONFIG 匹配)
BOT_PREFIX = "SHOP_DISCORD"  # 環境變數前綴: DISCORD / SHOP_DISCORD / UI_DISCORD
COMMANDS_DIR = "cogs/shop"  # 指令目錄: cogs/common / cogs/shop / cogs/ui (已重構)
VERSION = "1.0.0"
EMOJI = "🛒"  # Bot 代表符號: 🤖 / 🛒 / 🎨

# ============================================================
# 環境變數載入
# ============================================================
load_dotenv()

# 減少 discord 庫的日誌噪音（只顯示警告及以上）
import logging

discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.WARNING)
discord_webhook_logger = logging.getLogger("discord.webhook")
discord_webhook_logger.setLevel(logging.WARNING)

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

# 如果機器人被加入多個伺服器，使用自動分片可以減少單個 websocket
# 當出現 "Can't keep up" 警告時，啟用分片是一個常見建議。
# 可透過 SHARD_COUNT 環境變數手動指定，否則 AutoShardedBot 會自動計算。
shard_count = os.getenv(f"{BOT_PREFIX}_SHARD_COUNT")
if shard_count:
    shard_count = int(shard_count)

client_kwargs = {"command_prefix": "!", "help_command": None, "intents": intents}
if shard_count:
    client_kwargs["shard_count"] = shard_count

client = commands.AutoShardedBot(**client_kwargs)

# ============================================================
# 模組載入系統
# ============================================================
# 防止重複載入的鎖
_reload_lock = asyncio.Lock()
_pending_reloads = set()

# 追蹤 on_ready 是否被觸發
_on_ready_called = False
_on_ready_check_task = None

# Gateway 事件日誌控制（避免刷屏）
_last_disconnect_log_time = 0
_last_resumed_log_time = 0
_GATEWAY_LOG_INTERVAL = 30  # 每 30 秒最多輸出一次相同日誌


# ============================================================
# 事件監視函數
# ============================================================
async def _check_ready_timeout():
    """監視 ready 狀態，如果超時就手動調用 on_ready()"""
    global _on_ready_called
    # file_log("[READY_MONITOR] 開始監視 ready 狀態（10 秒超時）")  # 日誌已停用

    for i in range(10):
        await asyncio.sleep(1)
        # file_log(f"[READY_MONITOR] {i+1}s - ready={client.is_ready()} - on_ready_called={_on_ready_called}")  # 日誌已停用

        if _on_ready_called:
            # file_log("[READY_MONITOR] on_ready 已被正常觸發")  # 日誌已停用
            return

    if not _on_ready_called:
        file_log("[READY_MONITOR] 10 秒超時，on_ready 未被觸發，嘗試手動調用")
        try:
            await on_ready()
        except Exception as e:
            file_log(f"[READY_MONITOR] 手動調用 on_ready 失敗: {e}")


async def find_and_load_extensions(base_path, package_prefix="", client=None):
    """遞歸搜尋並載入所有 Python 擴展（只加載有效的 Cog）。

    跳過任何名為 `views` 的子包，以避免載入僅包含 View/Modal 的檔案。
    """
    if package_prefix.split(".")[-1] == "views":
        return []

    loaded_extensions = []

    # 列出不應該被加載為 Cog 的模組
    excluded_modules = {
        "cannabis_farming",
        "cannabis_merchant_view_v2",
        "cannabis_config",
        "database",
        "config",
        "views",
        "views_base",
        "paperdoll_system",
        "gambling",
        "role_expiry_manager",
        "ai_client_liteLLM",
        "auto_debug_system",
    }

    for item in sorted(os.listdir(base_path)):
        item_path = os.path.join(base_path, item)

        if os.path.isdir(item_path) and os.path.exists(
            os.path.join(item_path, "__init__.py")
        ):
            sub_package = f"{package_prefix}.{item}" if package_prefix else item
            sub_extensions = await find_and_load_extensions(
                item_path, sub_package, client
            )
            loaded_extensions.extend(sub_extensions)

        elif item.endswith(".py") and item != "__init__.py":
            module_name = item[:-3]

            # 跳過不應該被加載為 Cog 的模組
            if module_name in excluded_modules:
                continue

            ext_name = (
                f"{package_prefix}.{module_name}" if package_prefix else module_name
            )

            try:
                await client.load_extension(ext_name)
                loaded_extensions.append(ext_name)
            except Exception as e:
                print(f"❌ 載入失敗: {ext_name} - {e}")

    return loaded_extensions


async def setup_modules(client):
    """載入所有模組"""
    # 轉換路徑為包名（cogs/shop → cogs.shop）
    package_prefix = COMMANDS_DIR.replace("/", ".")

    # 從父目錄開始計算路徑（cogs/shop -> cogs_base_path, shop_subdir）
    if "/" in COMMANDS_DIR:
        parts = COMMANDS_DIR.split("/")
        # 從 bots/ 向上一級到根目錄
        root_path = os.path.dirname(os.path.dirname(__file__))
        full_path = os.path.join(root_path, *parts)
    else:
        full_path = os.path.join(os.path.dirname(__file__), COMMANDS_DIR)

    if not os.path.exists(full_path):
        os.makedirs(full_path)
        init_file = os.path.join(full_path, "__init__.py")
        with open(init_file, "w", encoding="utf-8") as f:
            f.write(f"# {BOT_NAME} Bot Commands Module\n")
        return []

    return await find_and_load_extensions(full_path, package_prefix, client)


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

            synced = (
                await client.tree.sync(guild=guild)
                if guild
                else await client.tree.sync()
            )
            print(f"✓ 同步完成: {len(synced)} 個指令")
        except Exception as e:
            print(f"❌ 重載失敗: {ext_name} - {e}")
        finally:
            _pending_reloads.discard(ext_name)





# ============================================================
# 日誌更新任務（每 15 秒更新一次）
# ============================================================
# 日誌更新任務現在由 status_dashboard.py 的全域任務處理


# ============================================================
# 狀態更新任務
# ============================================================
@tasks.loop(minutes=10)
async def update_status():
    """定期更新 Bot 狀態和日誌 Embed"""
    try:
        activity = build_discord_activity(BOT_TYPE)
        await asyncio.wait_for(client.change_presence(activity=activity), timeout=10.0)

        # 每 10 分鐘更新一次日誌 embed
        from status_dashboard import update_dashboard_logs

        await update_dashboard_logs(client, BOT_TYPE)
        file_log("[DEBUG] Status updated")
    except asyncio.TimeoutError:
        file_log("[ERROR] Status update timeout - presence change exceeded 10s")
        print("[ERROR] Status update timeout")
    except (ImportError, OSError, RuntimeError, discord.HTTPException, discord.Forbidden, discord.NotFound, discord.InvalidArgument, discord.GatewayNotFound) as e:
        file_log(f"[ERROR] Failed to update status: {type(e).__name__}: {e}")
        print(f"[ERROR] Failed to update status: {type(e).__name__}: {e}")
    except Exception as e:
        # 兜底：任何未預期的異常都記錄但不讓任務崩潰
        file_log(f"[ERROR] Unexpected error in update_status: {type(e).__name__}: {e}")
        print(f"[ERROR] Unexpected error in update_status: {type(e).__name__}: {e}")


@update_status.before_loop
async def before_update_status():
    """等待 Bot 準備完成"""
    await client.wait_until_ready()


# Gateway lifecycle logging
@client.event
async def on_connect():
    global _on_ready_check_task
    file_log("=== ON_CONNECT CALLED ===")
    print("[DISCORD] gateway connected", flush=True)

    if _on_ready_check_task is None:
        _on_ready_check_task = asyncio.create_task(_check_ready_timeout())


@client.event
async def on_disconnect():
    global _last_disconnect_log_time
    import time

    current_time = time.time()
    # 只在间隔足够长时才输出日志（避免刷屏）
    if current_time - _last_disconnect_log_time >= _GATEWAY_LOG_INTERVAL:
        print("[DISCORD] gateway disconnected")
        _last_disconnect_log_time = current_time


@client.event
async def on_resumed():
    global _last_resumed_log_time
    import time

    current_time = time.time()
    # 只在间隔足够长时才输出日志（避免刷屏）
    if current_time - _last_resumed_log_time >= _GATEWAY_LOG_INTERVAL:
        print("[DISCORD] session resumed")
        _last_resumed_log_time = current_time


@client.event
async def on_interaction(interaction: discord.Interaction):
    try:
        await track_discord_interaction(interaction, BOT_TYPE)
    except Exception as e:
        file_log(f"⚠️ 功能使用量追蹤失敗: {e}")


# ============================================================
# Bot 事件處理
# ============================================================
@client.event
async def on_ready():
    """Bot 啟動完成"""
    global _on_ready_called

    file_log("=== ON_READY CALLED ===")

    stage_text = "DEV" if STAGE != "prod" else "PROD"

    try:
        # 清除舊指令
        if guild and STAGE != "prod":
            await client.tree.clear_commands(guild=guild)

        # 載入模組（只在第一次 on_ready 執行，避免重連時重複載入 Cog）
        if not _on_ready_called:
            _on_ready_called = True
            loaded_extensions = await setup_modules(client)
        else:
            file_log("[on_ready] 重連觸發，跳過 setup_modules（已載入）")
            loaded_extensions = list(client.extensions.keys())

        # ⭐ 註冊所有永久視圖（timeout=None）
        # 這是解決按鈕交互失敗的關鍵步驟
        from shared.utils.view_registry import register_all_permanent_views

        try:
            register_all_permanent_views(client)
        except Exception as e:
            file_log(f"❌ 視圖註冊失敗: {e}")
            print(f"❌ 視圖註冊失敗: {e}")

        # 同步指令
        synced = (
            await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        )

        # 前綴指令
        prefix_cmds = list(client.commands)

        # ============================================================
        # 構建單一完整輸出（避免多次調用 print）
        # ============================================================
        lines = [
            "=" * 60,
            f"{EMOJI} {BOT_NAME} Bot 啟動完成 | v{VERSION} ({stage_text})",
            "=" * 60,
            f"📊 統計: 📦 {len(loaded_extensions)} 擴展 | ⚡ {len(synced)} Slash指令 | 🔧 {len(prefix_cmds)} 前綴指令",
        ]

        # 載入失敗的擴展（如果有）
        failed_extensions = []

        # 已載入擴展（緊湊格式）
        if loaded_extensions:
            lines.append("")
            lines.append("📦 已載入擴展:")
            ext_names = [ext.split(".")[-1] for ext in loaded_extensions]
            # 每行顯示 5 個擴展
            for i in range(0, len(ext_names), 5):
                batch = ext_names[i : i + 5]
                lines.append(f"   {' | '.join(batch)}")

        # Slash 指令（緊湊格式）
        if synced:
            lines.append("")
            lines.append("⚡ Slash 指令:")
            cmd_names = [f"/{cmd.name}" for cmd in synced]
            # 每行顯示 6 個指令
            for i in range(0, len(cmd_names), 6):
                batch = cmd_names[i : i + 6]
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
        # 初始化監控儀表板及日誌系統
        # ============================================================
        try:
            # Write diagnostic log (using ASCII only to avoid encoding issues)
            with open("/tmp/dashboard_init_shopbot.log", "a", encoding="utf-8") as df:
                df.write(
                    f"[{datetime.now()}] [INIT] Starting dashboard initialization\n"
                )
                df.flush()

            print("[SHOPBOT] Starting dashboard init...", flush=True)
            load_message_ids("shopbot")

            with open("/tmp/dashboard_init_shopbot.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now()}] [INIT] Calling initialize_dashboard\n")
                df.flush()

            dashboard_ready = await initialize_dashboard(client, "shopbot")

            with open("/tmp/dashboard_init_shopbot.log", "a", encoding="utf-8") as df:
                df.write(
                    f"[{datetime.now()}] [INIT] Result: dashboard_ready={dashboard_ready}\n"
                )
                df.flush()

            if dashboard_ready:
                print("[DASHBOARD] Shopbot log system initialized", flush=True)
                # Immediate log update to ensure Discord shows logs
                print("[SHOPBOT] Running initial log update...", flush=True)
                try:
                    await update_dashboard_logs(client, "shopbot")
                    print("[SHOPBOT] Initial log update complete", flush=True)
                except Exception as update_error:
                    print(
                        f"[SHOPBOT] Initial log update failed: {update_error}",
                        flush=True,
                    )
            else:
                print("[WARNING] Dashboard initialization returned False", flush=True)
        except Exception as e:
            with open("/tmp/dashboard_init_shopbot.log", "a", encoding="utf-8") as df:
                df.write(f"[{datetime.now()}] [ERROR] Exception: {e}\n")
                import traceback

                traceback.print_exc(file=df)

        # 啟動狀態更新任務
        if not update_status.is_running():
            update_status.start()

        ensure_mutual_rescue_monitor(client, BOT_TYPE, log_func=file_log)

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

    使用重試循環以提高連線穩定性，使 systemd/監控不必頻繁介入。
    """
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

    # 初始化資料庫連線池
    try:
        await init_async_db()
        file_log("[DB] 連線池初始化完成")
    except Exception as e:
        file_log(f"[DB] ❌ 連線池初始化失敗: {e}")
        raise

    try:
        while True:
            try:
                async with client:
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
            print("[MAIN] 連線中斷，5秒後重試")
            await asyncio.sleep(5)
    finally:
        if update_status.is_running():
            update_status.stop()
        # 關閉資料庫連線池
        try:
            await close_async_db()
            file_log("[DB] 連線池已關閉")
        except Exception as e:
            file_log(f"[DB] ❌ 關閉連線池失敗: {e}")
        # if observer is defined:
        #     observer.stop()
        #     observer.join()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ 啟動失敗: {e}")
        sys.exit(1)
