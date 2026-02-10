import os
import sys
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from logger import print
from bot_status import build_discord_activity
from webhook_logger import update_bot_info, send_or_update_startup_info
from status_dashboard import initialize_dashboard, update_dashboard, add_log, load_message_ids, set_bot_type, DashboardButtons, ensure_dashboard_messages

# ============================================================
# 配置區 - 根據不同 BOT 修改此區域
# ============================================================
BOT_NAME = "Bot"  # 可改為 "Shop" 或 "UI"
BOT_TYPE = "scam"  # 狀態主題: scam / shop / ui
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

client = commands.Bot(command_prefix="!", help_command=None, intents=intents)

# ============================================================
# 模組載入系統
# ============================================================
# 防止重複載入的鎖
_reload_lock = asyncio.Lock()
_pending_reloads = set()

async def find_and_load_extensions(base_path, package_prefix="", client=None):
    """遞歸搜尋並載入所有 Python 擴展（只加載有效的 Cog）"""
    loaded_extensions = []
    
    # 列出不應該被加載為 Cog 的模組
    excluded_modules = {
        'cannabis_farming', 'cannabis_merchant_view', 'cannabis_merchant_view_v2',
        'cannabis_config', 'database', 'config', 'views', 'views_base',
        'paperdoll_system', 'gambling', 'role_expiry_manager', 'locker_panel'
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
@tasks.loop(minutes=5)
async def update_status():
    """定期更新 Bot 狀態"""
    try:
        activity = build_discord_activity(BOT_TYPE)
        await client.change_presence(activity=activity)
    except Exception as e:
        print(f"❌ 狀態更新失敗: {e}")

@update_status.before_loop
async def before_update_status():
    """等待 Bot 準備完成"""
    await client.wait_until_ready()

# ============================================================
# Bot 事件處理
# ============================================================
@client.event
async def on_ready():
    """Bot 啟動完成"""
    stage_text = "DEV" if STAGE != "prod" else "PROD"
    
    try:
        # 清除舊指令
        if guild and STAGE != "prod":
            await client.tree.clear_commands(guild=guild)
        
        # 載入模組
        loaded_extensions = await setup_modules(client)
        
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
        
        # ⚠️ 重要：使用單一 print 調用輸出所有內容
        # 這樣 logger.py 只會產生一條日誌記錄
        print("\n".join(lines))
        
        # 設定初始狀態
        activity = build_discord_activity(BOT_TYPE)
        await client.change_presence(activity=activity)
        
        # ============================================================
        # 自動刪除舊訊息
        # ============================================================
        # 頻道 ID 固定為機器人秘書頻道，用於啟動時清理舊訊息
        CHANNEL_ID_TO_CLEAN = 1470788880805531702
        MAX_MESSAGES_TO_DELETE = 100
        DELETE_DELAY = 0.1  # 每條訊息間隔 0.1 秒，防止 API 限流
        
        deleted_count = 0
        try:
            print(f"🗑️  開始清理頻道 {CHANNEL_ID_TO_CLEAN} 的舊訊息...")
            
            # 嘗試獲取頻道
            channel = None
            try:
                channel = client.get_channel(CHANNEL_ID_TO_CLEAN)
                if channel is None:
                    # 如果 get_channel 返回 None，嘗試使用 fetch_channel
                    try:
                        channel = await asyncio.wait_for(
                            client.fetch_channel(CHANNEL_ID_TO_CLEAN),
                            timeout=10.0
                        )
                    except asyncio.TimeoutError:
                        print(f"⚠️  獲取頻道超時（頻道 ID: {CHANNEL_ID_TO_CLEAN}）")
                        channel = None
                    except discord.NotFound:
                        print(f"⚠️  頻道不存在（頻道 ID: {CHANNEL_ID_TO_CLEAN}）")
                        channel = None
                    except discord.Forbidden:
                        print(f"⚠️  沒有權限訪問頻道（頻道 ID: {CHANNEL_ID_TO_CLEAN}）")
                        channel = None
            except Exception as e:
                print(f"⚠️  獲取頻道時發生錯誤: {type(e).__name__}: {e}")
                channel = None
            
            if channel:
                print(f"✅ 成功獲取頻道: {channel.name}")
                
                # 嘗試獲取並刪除訊息
                try:
                    # 使用 asyncio.wait_for 設置整體超時（例如 60 秒）
                    async def delete_messages():
                        nonlocal deleted_count
                        try:
                            async for message in channel.history(limit=MAX_MESSAGES_TO_DELETE):
                                try:
                                    # 嘗試刪除單條訊息
                                    await message.delete()
                                    deleted_count += 1
                                    
                                    # 日誌輸出（每 10 條輸出一次進度）
                                    if deleted_count % 10 == 0:
                                        print(f"  📊 已刪除 {deleted_count} 條訊息")
                                    
                                    # API 限流保護 - 每條訊息間隔 0.1 秒
                                    await asyncio.sleep(DELETE_DELAY)
                                    
                                except discord.NotFound:
                                    # 訊息已經不存在，跳過
                                    pass
                                except discord.Forbidden:
                                    # 權限不足，無法刪除此訊息
                                    print(f"  ⚠️  權限不足，無法刪除訊息 ID: {message.id}")
                                except discord.HTTPException as e:
                                    # HTTP 錯誤（如 429 限流）
                                    print(f"  ⚠️  HTTP 錯誤刪除訊息 ID {message.id}: {e}")
                                    # 如果遇到限流，等待更長時間
                                    if e.status == 429:
                                        retry_after = e.retry_after if hasattr(e, 'retry_after') else 5.0
                                        if not hasattr(e, 'retry_after'):
                                            print(f"  ⚠️  警告: API 未提供 retry_after，使用預設值 {retry_after} 秒")
                                        print(f"  ⏳ 遇到限流，等待 {retry_after} 秒...")
                                        await asyncio.sleep(retry_after)
                                except Exception as e:
                                    # 其他未預期的錯誤，不中斷迴圈
                                    print(f"  ⚠️  刪除訊息時發生錯誤 (ID: {message.id}): {type(e).__name__}: {e}")
                        except discord.Forbidden:
                            print(f"⚠️  沒有權限讀取頻道歷史訊息")
                        except discord.HTTPException as e:
                            print(f"⚠️  讀取訊息歷史時發生 HTTP 錯誤: {e}")
                        except Exception as e:
                            print(f"⚠️  讀取訊息歷史時發生錯誤: {type(e).__name__}: {e}")
                    
                    # 設置整體超時為 120 秒
                    await asyncio.wait_for(delete_messages(), timeout=120.0)
                    
                except asyncio.TimeoutError:
                    print(f"⚠️  刪除訊息操作超時（已刪除 {deleted_count} 條）")
                except Exception as e:
                    print(f"⚠️  刪除訊息過程中發生未預期錯誤: {type(e).__name__}: {e}")
                
                # 最終報告
                if deleted_count > 0:
                    print(f"✅ 成功刪除 {deleted_count} 條舊訊息")
                else:
                    print(f"ℹ️  沒有訊息需要刪除")
            else:
                print(f"⚠️  無法獲取頻道，跳過訊息清理")
                
        except Exception as e:
            # 最外層錯誤捕獲，確保 Bot 不會因此崩潰
            print(f"⚠️  訊息清理過程發生嚴重錯誤: {type(e).__name__}: {e}")
            print(f"ℹ️  已刪除 {deleted_count} 條訊息後中止")
        
        # ============================================================
        # 更新機器人秘書頻道的啟動資訊
        # ============================================================
        try:
            from webhook_logger import update_bot_info, send_or_update_startup_info
            
            # 收集指令和擴展信息
            ext_names = [ext.split('.')[-1] for ext in loaded_extensions]
            cmd_names = [f"/{cmd.name}" for cmd in synced]
            prefix_cmd_names = [f"!{cmd.name}" for cmd in prefix_cmds]
            all_cmds = cmd_names + prefix_cmd_names
            
            # 更新該 bot 的資訊
            startup_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            await update_bot_info("bot", startup_time, cmd_names, ext_names)
            
            # 發送/編輯啟動訊息（只有 bot 會發送統一訊息）
            await send_or_update_startup_info("bot")
            
            add_log("bot", "✅ 啟動資訊已更新到機器人秘書")
        except Exception as e:
            print(f"⚠️ 更新啟動資訊失敗: {e}")
        
        # ============================================================
        # 初始化監控儀表板及日誌系統
        # ============================================================
        try:
            # 設置當前 bot 類型
            set_bot_type("bot")
            load_message_ids("bot")
            
            # 初始化儀表板（只初始化當前 bot 的面板）
            dashboard_ready = await initialize_dashboard(client, "bot")
            if dashboard_ready:
                add_log("bot", "✅ 儀表板已初始化")
                # 註冊持久化按鈕視圖
                client.add_view(DashboardButtons("bot", client))
                print("✅ 控制面板按鈕已註冊")
                if not update_logs_task.is_running():
                    update_logs_task.start()
                print(f"✅ 日誌系統已啟動")
            
            # 確保儀表板消息按正確順序存在（bot → shopbot → uibot）
            await ensure_dashboard_messages(client, "bot")
            
            # 註冊機器人實例供日誌更新使用
            from status_dashboard import register_bot_instance
            register_bot_instance("bot", client)
        except Exception as e:
            print(f"⚠️ 儀表板初始化失敗: {e}")
        
        # ============================================================
        # 發送啟動資訊到 Webhook
        # ============================================================
        try:
            add_log("bot", "✅ 啟動資訊已發送到 Webhook")
        except Exception as e:
            print(f"⚠️ Webhook 發送失敗: {e}")
        
        # 啟動狀態更新任務
        if not update_status.is_running():
            update_status.start()
        
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
    """主程序"""
    loop = asyncio.get_event_loop()
    observer = Observer()
    
    commands_path = os.path.join(os.path.dirname(__file__), COMMANDS_DIR)
    
    if not os.path.exists(commands_path):
        os.makedirs(commands_path)
        init_file = os.path.join(commands_path, "__init__.py")
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write(f"# {BOT_NAME} Bot Commands Module\n")
    
    observer.schedule(
        FileEventHandler(loop),
        path=commands_path,
        recursive=True
    )
    observer.start()

    try:
        async with client:
            await client.start(TOKEN)
    except KeyboardInterrupt:
        print(f"\n👋 {BOT_NAME} Bot 已停止")
    except discord.LoginFailure:
        print("❌ Discord Token 無效")
    except Exception as e:
        print(f"❌ 運行失敗: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if update_status.is_running():
            update_status.stop()
        observer.stop()
        observer.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ 啟動失敗: {e}")
        sys.exit(1)
