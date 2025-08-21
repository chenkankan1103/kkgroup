import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def get_last_commit():
    """抓取最後一次 git commit 訊息"""
    try:
        commit_msg = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s (%h)"],
            cwd="/home/e193752468/kkgroup"
        ).decode("utf-8").strip()
        return commit_msg
    except Exception as e:
        return f"⚠️ 無法取得更新內容: {e}"

@bot.event
async def on_ready():
    channel = bot.get_channel(int(DISCORD_SYS_CHANNEL_ID))
    if channel:
        last_update = get_last_commit()
        await channel.send(f"✅ BOT 已更新並重啟完成！\n📌 更新內容：{last_update}")
    await bot.close()

bot.run(TOKEN)
