import discord
from discord.ext import commands

BOT_TOKEN = "MTA3ODg5NDI5NTM0NTUzNzA0NA.GJ-0Qa.UbCSi-fGdbJSsS4mW2uob5ViG6ZVYpOvt6a26Q"

intents = discord.Intents.default()
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

bot.run(BOT_TOKEN)
