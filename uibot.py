import os
import sys
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# === 載入環境變數 ===
load_dotenv()
STAGE = os.getenv("STAGE", "dev")
version = "UI Bot 0.1.0 (開發階段)" if STAGE != "prod" else "UI Bot 0.1.0"

# === 系統路徑 ===
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))

# === Discord Bot 設定 ===
TOKEN = os.getenv("UI_DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
SYS_CHANNEL_ID = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))

if not TOKEN:
    raise RuntimeError("❌ UI_DISCORD_BOT_TOKEN 未在 .env 中設定")

guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True
intents.members = True

client = commands.Bot(command_prefix="!", help_command=None, intents=intents)

# === 簡單的狀態任務 ===
async def change_status_task():
    """保持 bot 活躍狀態的背景任務"""
    await client.wait_until_ready()
    while not client.is_closed():
        activity = discord.Activity(type=discord.ActivityType.watching, name="UI 介面設計")
        await client.change_presence(status=discord.Status.online, activity=activity)
        await asyncio.sleep(300)  # 每5分鐘更新一次

# === 載入模組（uicommands）===
async def setup_modules(tree, client, module_dirs):
    """載入指定目錄下的所有模組"""
    for module_dir, prefix in module_dirs:
        full_path = os.path.join(os.path.dirname(__file__), module_dir)
        if not os.path.exists(full_path):
            print(f"⚠️ 目錄不存在: {full_path}")
            continue
            
        for filename in os.listdir(full_path):
            if filename.endswith(".py") and filename != "__init__.py":
                ext = f"{prefix}.{filename[:-3]}"
                try:
                    await client.load_extension(ext)
                    print(f"✅ 已載入 {ext}")
                except Exception as e:
                    print(f"❌ 載入 {ext} 失敗: {e}")

async def reload_extension_on_change(ext_name):
    """重新載入指定的擴展模組"""
    try:
        await client.reload_extension(ext_name)
        print(f"🔄 已自動 reload: {ext_name}")
    except Exception as e:
        print(f"❌ reload {ext_name} 失敗: {e}")

# === 檔案監控器 ===
class FileEventHandler(FileSystemEventHandler):
    def __init__(self, loop, prefix):
        self.loop = loop
        self.prefix = prefix

    def on_modified(self, event): 
        self.handle(event)
    
    def on_created(self, event): 
        self.handle(event)
    
    def on_moved(self, event): 
        self.handle(event)

    def handle(self, event):
        """處理檔案變動事件"""
        if not event.is_directory and event.src_path.endswith(".py"):
            filename = os.path.basename(event.src_path)
            if filename == "__init__.py":
                return
            ext_name = f"{self.prefix}.{filename[:-3]}"
            print(f"📂 檢測到 {self.prefix} 模組變動: {filename}，自動 reload")
            asyncio.run_coroutine_threadsafe(reload_extension_on_change(ext_name), self.loop)

# === Bot 事件處理 ===
@client.event
async def on_ready():
    """Bot 啟動完成事件"""
    print(f"🚀 UI Bot 正在初始化... (版本: {version})")
    try:
        if STAGE != "prod":
            print("⚠️ 正在開發環境執行，僅同步至指定 GUILD")

        if guild:
            await client.tree.clear_commands(guild=guild)
            print("🧹 已清除指定伺服器的所有已註冊指令")

        await setup_modules(client.tree, client, [
            ("uicommands", "uicommands")
        ])
        
        synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        print(f"✅ 指令同步完成: {[cmd.name for cmd in synced]}")

        print(f"🤖 登入成功: {client.user}（ID: {client.user.id}）")
        print(f"📦 當前版本: {version}")

        # 顯示指令列表
        print("🟦 Slash 指令列表：")
        for cmd in client.tree.get_commands():
            print(f"  /{cmd.name} - {cmd.description}")
        print("🟧 前綴指令列表：")
        for cmd in client.commands:
            print(f"  !{cmd.name} - {cmd.help or '無說明'}")

        # 在生產環境發送啟動通知
        if STAGE == "prod" and SYS_CHANNEL_ID:
            channel = client.get_channel(SYS_CHANNEL_ID)
            if channel:
                await channel.send(
                    f"🤖 UI Bot 已啟動\n"
                    f"📦 當前版本: {version}\n"
                    f"🟦 Slash 指令: {', '.join(f'/{cmd.name}' for cmd in client.tree.get_commands())}\n"
                    f"🟧 前綴指令: {', '.join(f'!{cmd.name}' for cmd in client.commands)}"
                )
                
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        raise

@client.event
async def on_connect():
    """Bot 連接事件 - 啟動背景任務"""
    if not hasattr(client, "status_task_started"):
        client.loop.create_task(change_status_task())
        client.status_task_started = True
        print("🔄 狀態背景任務已啟動")

@client.event
async def on_disconnect():
    """Bot 斷線事件"""
    print("⚠️ Bot 已斷線")

@client.event
async def on_resumed():
    """Bot 重新連接事件"""
    print("🔄 Bot 已重新連接")

# === 主程序入口 ===
async def main():
    """主程序入口點"""
    loop = asyncio.get_event_loop()
    observer = Observer()
    
    # 檢查並創建監控目錄
    uicommands_path = os.path.join(os.path.dirname(__file__), "uicommands")
    if os.path.exists(uicommands_path):
        observer.schedule(FileEventHandler(loop, "uicommands"),
                         path=uicommands_path,
                         recursive=False)
        print(f"📁 正在監控目錄: {uicommands_path}")
    else:
        print(f"⚠️ uicommands 目錄不存在: {uicommands_path}")
    
    observer.start()
    print("👀 檔案監控器已啟動")

    try:
        async with client:
            await client.start(TOKEN)
    except KeyboardInterrupt:
        print("🛑 收到中斷信號，正在關閉...")
    except Exception as e:
        print(f"❌ Bot 運行時發生錯誤: {e}")
        raise
    finally:
        print("🧹 正在清理資源...")
        observer.stop()
        observer.join()
        print("✅ 資源清理完成")

if __name__ == "__main__":
    print("=== 準備啟動 UI Discord Bot ===")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Bot 已停止")
    except Exception as e:
        print(f"❌ 啟動失敗: {e}")
        sys.exit(1)