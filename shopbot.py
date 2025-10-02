import os
import sys
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from logger import print

# === 載入環境變數 ===
load_dotenv()
STAGE = os.getenv("SHOP_STAGE", "dev")
version = "1.0.0 (開發階段)" if STAGE != "prod" else "1.0.0"

# === Discord Bot 設定 ===
TOKEN = os.getenv("SHOP_DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("SHOP_DISCORD_GUILD_ID")
SYS_CHANNEL_ID = int(os.getenv("SHOP_DISCORD_SYS_CHANNEL_ID", 0))

if not TOKEN:
    raise RuntimeError("❌ SHOP_DISCORD_BOT_TOKEN 未在 .env 中設定")

guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True
intents.members = True

client = commands.Bot(command_prefix="!", help_command=None, intents=intents)


# === 遞歸載入模組 ===
async def find_and_load_extensions(base_path, package_prefix="", client=None):
    """遞歸搜尋並載入所有 Python 擴展"""
    loaded_extensions = []
    
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        
        # 如果是目錄且包含 __init__.py，則遞歸搜尋
        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            sub_package = f"{package_prefix}.{item}" if package_prefix else item
            sub_extensions = await find_and_load_extensions(item_path, sub_package, client)
            loaded_extensions.extend(sub_extensions)
        
        # 如果是 Python 文件且不是 __init__.py
        elif item.endswith(".py") and item != "__init__.py":
            module_name = item[:-3]  # 移除 .py 擴展名
            ext_name = f"{package_prefix}.{module_name}" if package_prefix else module_name
            
            try:
                await client.load_extension(ext_name)
                loaded_extensions.append(ext_name)
                print(f"✅ 已載入 {ext_name}")
            except Exception as e:
                print(f"❌ 載入 {ext_name} 失敗: {e}")
    
    return loaded_extensions

async def setup_modules(tree, client, module_dirs):
    """設置模組"""
    all_loaded = []
    
    for module_dir, prefix in module_dirs:
        full_path = os.path.join(os.path.dirname(__file__), module_dir)
        
        if not os.path.exists(full_path):
            print(f"⚠️ 目錄不存在: {full_path}，將自動創建")
            os.makedirs(full_path)
            # 創建 __init__.py
            init_file = os.path.join(full_path, "__init__.py")
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write("# Shop Commands Module\n")
            continue
            
        print(f"🔍 搜尋模組目錄: {full_path}")
        loaded = await find_and_load_extensions(full_path, prefix, client)
        all_loaded.extend(loaded)
    
    return all_loaded

async def reload_extension_on_change(ext_name):
    try:
        await client.reload_extension(ext_name)
        print(f"🔄 已自動 reload: {ext_name}")
        
        # 重新同步命令
        try:
            synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
            print(f"🔄 命令重新同步完成: {len(synced)} 個命令")
        except Exception as sync_e:
            print(f"⚠️ 命令同步失敗: {sync_e}")
            
    except Exception as e:
        print(f"❌ reload {ext_name} 失敗: {e}")

# === 增強的熱重載用的檔案監控器 ===
class FileEventHandler(FileSystemEventHandler):
    def __init__(self, loop, prefix):
        self.loop = loop
        self.prefix = prefix

    def on_modified(self, event): self.handle(event)
    def on_created(self, event): self.handle(event)
    def on_moved(self, event): self.handle(event)

    def handle(self, event):
        if not event.is_directory and event.src_path.endswith(".py"):
            filename = os.path.basename(event.src_path)
            if filename == "__init__.py":
                return
            
            # 計算正確的擴展名稱
            rel_path = os.path.relpath(event.src_path, os.path.join(os.path.dirname(__file__), "shop_commands"))
            module_path = rel_path.replace(os.sep, ".")[:-3]  # 移除 .py 並轉換路徑分隔符
            ext_name = f"shop_commands.{module_path}"
            
            print(f"📂 檢測到模組變動: {event.src_path}")
            print(f"🔄 嘗試 reload: {ext_name}")
            asyncio.run_coroutine_threadsafe(reload_extension_on_change(ext_name), self.loop)

# === Bot 事件處理 ===
@client.event
async def on_ready():
    print(f"🚀 黑市商人 Bot 正在初始化... (版本: {version})")
    try:
        if STAGE != "prod":
            print("⚠️ 正在開發環境執行，僅同步至指定 GUILD")

        if guild:
            await client.tree.clear_commands(guild=guild)
            print("🧹 已清除指定伺服器的所有已註冊指令")

        # 載入所有模組
        loaded_extensions = await setup_modules(client.tree, client, [
            ("shop_commands", "shop_commands")
        ])
        
        print(f"📦 總共載入了 {len(loaded_extensions)} 個擴展:")
        for ext in loaded_extensions:
            print(f"  - {ext}")
        
        # 同步命令
        synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        print(f"✅ 指令同步完成: {[cmd.name for cmd in synced]}")

        print(f"🛒 登入成功: {client.user}（ID: {client.user.id}）")
        print(f"📦 當前版本: {version}")
        print(f"📊 連接到 {len(client.guilds)} 個伺服器")

        # 列出所有指令      
        print("🟦 Slash 指令列表：")
        for cmd in client.tree.get_commands():
            print(f"  /{cmd.name} - {cmd.description}")
        print("🟧 前綴指令列表：")
        for cmd in client.commands:
            print(f"  !{cmd.name} - {cmd.help or '無說明'}")

        # 設置狀態
        await client.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="黑市交易"
            )
        )

        # 發送啟動訊息到系統頻道
        if STAGE == "prod" and SYS_CHANNEL_ID:
            channel = client.get_channel(SYS_CHANNEL_ID)
            if channel:
                await channel.send(
                    f"🛒 黑市商人 Bot 已啟動\n"
                    f"📦 當前版本: {version}\n"
                    f"🔧 載入擴展: {len(loaded_extensions)} 個\n"
                    f"📊 連接到 {len(client.guilds)} 個伺服器\n"
                    f"🟦 Slash 指令: {', '.join(f'/{cmd.name}' for cmd in client.tree.get_commands())}\n"
                    f"🟧 前綴指令: {', '.join(f'!{cmd.name}' for cmd in client.commands)}"
                )
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        import traceback
        traceback.print_exc()

@client.event
async def on_command_error(ctx, error):
    """錯誤處理"""
    if isinstance(error, commands.CommandNotFound):
        return  # 忽略未知指令
    elif isinstance(error, commands.MissingPermissions):
        print(f"⚠️ 權限不足: {ctx.author} 在 {ctx.guild} 嘗試執行 {ctx.command}")
    elif isinstance(error, commands.BotMissingPermissions):
        print(f"⚠️ 機器人權限不足: {ctx.command} 在 {ctx.guild}")
    else:
        print(f"❌ 指令錯誤 [{ctx.command}]: {error}")

# === 調試指令 ===
@client.command(name="reload_all")
@commands.is_owner()
async def reload_all(ctx):
    """重新載入所有擴展（僅擁有者可用）"""
    try:
        # 獲取所有已載入的擴展
        extensions = list(client.extensions.keys())
        
        reloaded = []
        failed = []
        
        for ext in extensions:
            try:
                await client.reload_extension(ext)
                reloaded.append(ext)
            except Exception as e:
                failed.append(f"{ext}: {str(e)}")
        
        # 重新同步命令
        synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        
        result = f"🔄 重新載入完成:\n"
        result += f"✅ 成功: {len(reloaded)} 個\n"
        if failed:
            result += f"❌ 失敗: {len(failed)} 個\n"
            for fail in failed[:5]:  # 只顯示前5個失敗
                result += f"  - {fail}\n"
        result += f"🔄 重新同步了 {len(synced)} 個命令"
        
        await ctx.send(result)
        print(f"🔄 {ctx.author} 執行了 reload_all 指令")
        
    except Exception as e:
        await ctx.send(f"❌ 重新載入失敗: {e}")
        print(f"❌ reload_all 指令失敗: {e}")

@client.command(name="list_extensions")
@commands.is_owner()
async def list_extensions(ctx):
    """列出所有已載入的擴展"""
    extensions = list(client.extensions.keys())
    if extensions:
        result = f"📦 已載入 {len(extensions)} 個擴展:\n"
        for i, ext in enumerate(extensions, 1):
            result += f"{i}. {ext}\n"
    else:
        result = "❌ 沒有載入任何擴展"
    
    await ctx.send(f"```{result}```")
    print(f"📋 {ctx.author} 查看了擴展列表")

# === 主程序入口 ===
async def main():
    loop = asyncio.get_event_loop()
    observer = Observer()
    
    # 監視 shop_commands 目錄（遞歸監視所有子目錄）
    commands_path = os.path.join(os.path.dirname(__file__), "shop_commands")
    
    # 確保目錄存在
    if not os.path.exists(commands_path):
        os.makedirs(commands_path)
        # 創建 __init__.py
        init_file = os.path.join(commands_path, "__init__.py")
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write("# Shop Commands Module\n")
        print(f"📁 已創建目錄: {commands_path}")
    
    observer.schedule(FileEventHandler(loop, "shop_commands"),
                      path=commands_path,
                      recursive=True)  # 設為 True 以監視子目錄
    
    observer.start()
    print(f"👀 開始監視目錄: {commands_path} (遞歸)")

    try:
        async with client:
            await client.start(TOKEN)
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    print("=== 準備啟動黑市商人 Discord Bot ===")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 黑市商人 Bot 已手動停止")
    except discord.LoginFailure:
        print("❌ Discord Token 無效")
    except Exception as e:
        print(f"❌ 啟動失敗: {e}")
        import traceback
        traceback.print_exc()
