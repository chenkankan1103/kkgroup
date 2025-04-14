import discord
from discord.ext import tasks
from discord import app_commands
import feedparser
import re
import asyncio
import os
import aiohttp
import json
import subprocess
from dotenv import load_dotenv
import traceback
import sys

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
FASTGPT_API_KEY = os.getenv("FASTGPT_API_KEY")
FASTGPT_API_URL = os.getenv("FASTGPT_API_URL", "https://openrouter.ai/api/v1/chat/completions")
FASTGPT_MODEL = os.getenv("FASTGPT_MODEL", "mistralai/mistral-7b-instruct")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))
MAG_THRESHOLD = float(os.getenv("MAG_THRESHOLD", 4.5))
LATEST_EQ_FILE = "latest_earthquake.json"

def get_git_version():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
    except Exception:
        return "unknown"

VERSION = f"v0.0.1 ({get_git_version()})"

def load_latest_eq_guid():
    if os.path.exists(LATEST_EQ_FILE):
        try:
            with open(LATEST_EQ_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("guid")
        except Exception as e:
            print(f"⚠️ 無法載入地震快取: {e}")
    return None

def save_latest_eq_guid(guid):
    try:
        with open(LATEST_EQ_FILE, "w", encoding="utf-8") as f:
            json.dump({"guid": guid}, f)
    except Exception as e:
        print(f"⚠️ 無法儲存地震快取: {e}")

latest_eq_guid = load_latest_eq_guid()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    print(f"✅ 已登入 {client.user.name}")
    synced = await tree.sync()
    print(f"🔁 已同步指令: {[cmd.name for cmd in synced]}")
    check_earthquake.start()
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(f"🔄 機器人已啟動，版本：{VERSION}")

@tasks.loop(minutes=1)
async def check_earthquake():
    global latest_eq_guid
    feed = feedparser.parse("https://www.cwa.gov.tw/rss/earthquake.xml")
    if not feed.entries:
        return

    latest_entry = feed.entries[0]
    title = latest_entry.title
    link = latest_entry.link
    summary = latest_entry.summary
    guid = latest_entry.get("id", link)

    if guid == latest_eq_guid:
        return

    latest_eq_guid = guid
    save_latest_eq_guid(guid)

    mag_match = re.search(r"規模(?:約)?([\d.]+)", title + summary)
    if mag_match:
        magnitude = float(mag_match.group(1))
        if magnitude < MAG_THRESHOLD:
            return
    else:
        magnitude = "?"

    img_match = re.search(r'<img src="(.*?)"', summary)
    image_url = img_match.group(1) if img_match else None

    embed = discord.Embed(
        title=title,
        description=summary,
        url=link,
        color=discord.Color.red()
    )
    if image_url:
        embed.set_image(url=image_url)

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)
    else:
        print("❌ 找不到指定頻道")

@tree.command(name="測試地震", description="發送測試地震報告")
async def test_earthquake(interaction: discord.Interaction):
    embed = discord.Embed(
        title="有感地震報告 - 規模5.6 - 臺東近海",
        description="發震時間：2025/04/13 10:45\n震中位置：臺東外海\n規模5.6",
        url="https://www.cwa.gov.tw/V8/C/E/index.html",
        color=discord.Color.orange()
    )
    embed.set_image(url="https://www.cwa.gov.tw/Data/earthquake_img/EEA20250413104500.jpg")
    await interaction.response.send_message(embed=embed)

async def ask_openrouter_ai(question):
    headers = {
        "Authorization": f"Bearer {FASTGPT_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "user", "content": question}
        ],
        "model": nvidia/llama-3.1-nemotron-nano-8b-v1:free,
        "stream": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(FASTGPT_API_URL, headers=headers, json=payload) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "❓ 沒有回應")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    mention = f"<@{client.user.id}>"
    if message.content.startswith(mention):
        question = message.content[len(mention):].strip()
        if not question:
            await message.channel.send("✉️ 您好，我是 KK 中控室 AI。想問什麼？")
            return

        await message.channel.typing()
        reply = await ask_openrouter_ai(question)
        if reply is None:
            await message.channel.send("❌ 無法連線到 AI 伺服器。")
            return
        await message.channel.send(reply)

@tree.command(name="ai", description="與 KK 中控室 AI 對話")
@app_commands.describe(question="你想問什麼？")
async def ask_ai(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    reply = await ask_openrouter_ai(question)
    if reply is None:
        await interaction.followup.send("❌ 無法連線到 AI 伺服器。")
        return
    await interaction.followup.send(reply)

@tree.command(name="更新機器人", description="從 GitHub 更新 bot 代碼")
async def update_bot(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        output = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT)
        await interaction.followup.send(f"✅ 代碼更新成功\n```{output.decode()}\n重新啟動 bot...```")
        os.execv(sys.executable, [sys.executable, "bot.py"])
    except subprocess.CalledProcessError as e:
        await interaction.followup.send(f"❌ 更新失敗\n```{e.output.decode()}```")

@client.event
async def on_error(event, *args, **kwargs):
    print(f"出錯的事件: {event}")
    traceback.print_exc()

client.run(TOKEN)
