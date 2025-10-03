import os
import sys
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from logger import print
from bot_status import build_discord_activity

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
    """遞歸搜尋並載入所有 Python 擴展"""
    loaded_extensions = []
    
    for item in sorted(os.listdir(base_path)):
        item_path = os.path.join(base_path, item)
        
        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            sub_package = f"{package_prefix}.{item}" if package_prefix else item
            sub_extensions = await find_and_load_extensions(item_path, sub_package, client)
            loaded_extensions.extend(sub_extensions)
        
        elif item.endswith(".py") and item != "__init__.py":
            module_name = item[:-3]
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
    
    print("=" * 60)
    print(f"{EMOJI} {BOT_NAME} Bot 啟動中...")
    print(f"版本: {VERSION} ({stage_text})")
    print("=" * 60)
    
    try:
        # 清除舊指令
        if guild and STAGE != "prod":
            await client.tree.clear_commands(guild=guild)
        
        # 載入模組
        loaded_extensions = await setup_modules(client)
        
        # 格式化顯示載入的擴展
        if loaded_extensions:
            print(f"\n📦 已載入擴展 ({len(loaded_extensions)}):")
            for i, ext in enumerate(loaded_extensions, 1):
                print(f"  {i:2d}. {ext}")
        else:
            print("\n⚠️  未載入任何擴展")
        
        # 同步指令
        synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        
        # 格式化顯示指令
        if synced:
            print(f"\n⚡ 已註冊指令 ({len(synced)}):")
            for i, cmd in enumerate(synced, 1):
                print(f"  {i:2d}. /{cmd.name:<20s} - {cmd.description}")
        else:
            print("\n⚠️  未註冊任何 Slash 指令")
        
        # 前綴指令
        prefix_cmds = list(client.commands)
        if prefix_cmds:
            print(f"\n🔧 前綴指令 ({len(prefix_cmds)}):")
            for i, cmd in enumerate(prefix_cmds, 1):
                help_text = cmd.help or "無說明"
                print(f"  {i:2d}. !{cmd.name:<20s} - {help_text}")
        
        print("\n" + "=" * 60)
        print(f"✅ {client.user.name} 已就緒")
        print("=" * 60 + "\n")
        
        # 設定初始狀態
        activity = build_discord_activity(BOT_TYPE)
        await client.change_presence(activity=activity)
        
        # 啟動狀態更新任務
        if not update_status.is_running():
            update_status.start()
        
        # 發送啟動通知到系統頻道
        if STAGE == "prod" and SYS_CHANNEL_ID:
            channel = client.get_channel(SYS_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title=f"{EMOJI} {BOT_NAME} Bot 已啟動",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(
                    name="📦 版本",
                    value=f"`{VERSION}`",
                    inline=True
                )
                embed.add_field(
                    name="🔧 擴展",
                    value=f"`{len(loaded_extensions)}`",
                    inline=True
                )
                embed.add_field(
                    name="⚡ 指令",
                    value=f"`{len(synced)}`",
                    inline=True
                )
                
                if loaded_extensions:
                    ext_list = "\n".join([f"• {ext.split('.')[-1]}" for ext in loaded_extensions[:10]])
                    if len(loaded_extensions) > 10:
                        ext_list += f"\n...及其他 {len(loaded_extensions) - 10} 個"
                    embed.add_field(
                        name="📦 已載入擴展",
                        value=ext_list,
                        inline=False
                    )
                
                if synced:
                    cmd_list = "\n".join([f"• `/{cmd.name}`" for cmd in synced[:10]])
                    if len(synced) > 10:
                        cmd_list += f"\n...及其他 {len(synced) - 10} 個"
                    embed.add_field(
                        name="⚡ 註冊指令",
                        value=cmd_list,
                        inline=False
                    )
                
                await channel.send(embed=embed)
                
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        import traceback
        traceback.print_exc()

@client.event
async def on_command_error(ctx, error):
    """錯誤處理"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        pass  # 靜默處理權限錯誤
    elif isinstance(error, commands.BotMissingPermissions):
        pass  # 靜默處理 Bot 權限錯誤
    else:
        print(f"❌ 指令錯誤: {error}")

# ============================================================
# 管理指令
# ============================================================
@client.command(name="reload_all")
@commands.is_owner()
async def reload_all(ctx):
    """重新載入所有擴展"""
    try:
        async with _reload_lock:
            extensions = list(client.extensions.keys())
            reloaded, failed = [], []
            
            for ext in extensions:
                try:
                    await client.reload_extension(ext)
                    reloaded.append(ext)
                except Exception as e:
                    failed.append(f"{ext}: {str(e)[:50]}")
            
            synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        
        embed = discord.Embed(title="🔄 重新載入完成", color=discord.Color.blue())
        embed.add_field(name="✅ 成功", value=f"`{len(reloaded)}`", inline=True)
        embed.add_field(name="❌ 失敗", value=f"`{len(failed)}`", inline=True)
        embed.add_field(name="⚡ 同步", value=f"`{len(synced)}`", inline=True)
        
        if failed:
            embed.add_field(
                name="失敗清單",
                value="\n".join([f"• {f}" for f in failed[:5]]),
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ 重新載入失敗: {e}")

@client.command(name="list_extensions")
@commands.is_owner()
async def list_extensions(ctx):
    """列出所有已載入的擴展"""
    extensions = list(client.extensions.keys())
    
    if not extensions:
        await ctx.send("❌ 沒有載入任何擴展")
        return
    
    embed = discord.Embed(
        title=f"📦 已載入擴展 ({len(extensions)})",
        color=discord.Color.blue()
    )
    
    ext_list = "\n".join([f"{i}. `{ext}`" for i, ext in enumerate(extensions, 1)])
    
    # 分頁處理
    if len(ext_list) > 1024:
        chunks = [extensions[i:i+10] for i in range(0, len(extensions), 10)]
        for i, chunk in enumerate(chunks, 1):
            chunk_list = "\n".join([f"{j}. `{ext}`" for j, ext in enumerate(chunk, (i-1)*10+1)])
            embed.add_field(
                name=f"第 {i} 頁",
                value=chunk_list,
                inline=False
            )
    else:
        embed.description = ext_list
    
    await ctx.send(embed=embed)

@client.command(name="change_status")
@commands.is_owner()
async def change_status(ctx):
    """手動更新 Bot 狀態"""
    try:
        activity = build_discord_activity(BOT_TYPE)
        await client.change_presence(activity=activity)
        await ctx.send(f"✅ 狀態已更新: {activity.name}")
    except Exception as e:
        await ctx.send(f"❌ 狀態更新失敗: {e}")

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
