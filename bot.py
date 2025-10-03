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
        # 合併輸出 - 所有信息一次性顯示
        # ============================================================
        output_lines = []
        output_lines.append("=" * 60)
        output_lines.append(f"{EMOJI} {BOT_NAME} Bot 啟動完成 | 版本: {VERSION} ({stage_text})")
        output_lines.append("=" * 60)
        
        # 摘要信息（單行）
        output_lines.append(f"📦 擴展: {len(loaded_extensions)} | ⚡ Slash指令: {len(synced)} | 🔧 前綴指令: {len(prefix_cmds)}")
        output_lines.append("")
        
        # 已載入擴展（精簡顯示）
        if loaded_extensions:
            output_lines.append(f"📦 已載入擴展:")
            for ext in loaded_extensions:
                short_name = ext.split('.')[-1]
                output_lines.append(f"  • {short_name}")
        
        # Slash 指令（精簡顯示，只顯示名稱）
        if synced:
            output_lines.append("")
            output_lines.append(f"⚡ Slash 指令:")
            # 每行顯示 4 個指令，節省空間
            cmd_names = [f"/{cmd.name}" for cmd in synced]
            for i in range(0, len(cmd_names), 4):
                line_cmds = cmd_names[i:i+4]
                output_lines.append(f"  {', '.join(line_cmds)}")
        
        # 前綴指令
        if prefix_cmds:
            output_lines.append("")
            output_lines.append(f"🔧 前綴指令:")
            cmd_names = [f"!{cmd.name}" for cmd in prefix_cmds]
            output_lines.append(f"  {', '.join(cmd_names)}")
        
        output_lines.append("")
        output_lines.append("=" * 60)
        output_lines.append(f"✅ {client.user.name} 已就緒")
        output_lines.append("=" * 60)
        
        # 一次性輸出所有內容
        print("\n".join(output_lines))
        
        # 設定初始狀態
        activity = build_discord_activity(BOT_TYPE)
        await client.change_presence(activity=activity)
        
        # 啟動狀態更新任務
        if not update_status.is_running():
            update_status.start()
        
        # 發送啟動通知到系統頻道（單一訊息）
        if STAGE == "prod" and SYS_CHANNEL_ID:
            channel = client.get_channel(SYS_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title=f"{EMOJI} {BOT_NAME} Bot 已啟動",
                    description=f"版本 `{VERSION}` | 環境: **{stage_text}**",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                
                # 統計信息（使用內聯字段）
                embed.add_field(name="📦 擴展", value=f"`{len(loaded_extensions)}`", inline=True)
                embed.add_field(name="⚡ Slash", value=f"`{len(synced)}`", inline=True)
                embed.add_field(name="🔧 前綴", value=f"`{len(prefix_cmds)}`", inline=True)
                
                # 擴展列表（精簡版，最多顯示15個）
                if loaded_extensions:
                    ext_display = [ext.split('.')[-1] for ext in loaded_extensions[:15]]
                    ext_text = ", ".join([f"`{e}`" for e in ext_display])
                    if len(loaded_extensions) > 15:
                        ext_text += f" +{len(loaded_extensions) - 15} 個"
                    embed.add_field(
                        name="📦 已載入模組",
                        value=ext_text,
                        inline=False
                    )
                
                # 指令列表（精簡版，最多顯示20個）
                if synced:
                    cmd_display = [f"`/{cmd.name}`" for cmd in synced[:20]]
                    cmd_text = ", ".join(cmd_display)
                    if len(synced) > 20:
                        cmd_text += f" +{len(synced) - 20} 個"
                    embed.add_field(
                        name="⚡ 可用指令",
                        value=cmd_text,
                        inline=False
                    )
                
                embed.set_footer(text=f"🟢 系統運行正常")
                
                # 單一訊息發送
                await channel.send(embed=embed)
                
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
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
