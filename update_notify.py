import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    channel = bot.get_channel(int(DISCORD_SYS_CHANNEL_ID))
    if channel:
        await channel.send("✅ BOT 已更新並重啟完成！")
    await bot.close()

bot.run(TOKEN)
