import os
import sys
from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# 加入 utils 模組路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))

# 自訂模組引入
from utils.env import update_env_file
from commands import setup_commands

# 載入 .env 環境變數
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
SYS_CHANNEL_ID = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))

if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN 未在 .env 中設定")

guild = discord.Object(id=GUILD_ID) if GUILD_ID else None

# 設定 intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True
intents.members = True

# 建立 bot 實例
client = commands.Bot(command_prefix="!", intents=intents)

# Bot 啟動事件
@client.event
async def on_ready():
    print("🚀 Bot 正在初始化...")
    try:
        if guild:
            await client.tree.clear_commands(guild=guild)
            print("🧹 已清除指定伺服器的所有已註冊指令")
        
        # 使用改進後的 setup_commands 自動載入所有模組
        await setup_commands(client.tree, client)
        
        # 同步指令
        synced = await client.tree.sync(guild=guild) if guild else await client.tree.sync()
        print(f"✅ 指令同步完成: {[cmd.name for cmd in synced]}")
        print(f"🤖 登入成功: {client.user}（ID: {client.user.id}）")
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")

# 主程序入口
if __name__ == "__main__":
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"❌ Bot 啟動失敗: {e}")