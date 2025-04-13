import discord
from discord.ext import tasks
from discord import app_commands
import feedparser
import re
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))  # 預設通報地震的頻道 ID
MAG_THRESHOLD = float(os.getenv("MAG_THRESHOLD", 4.5))  # 預設 4.5 級以上才通知

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

latest_eq_title = None

@client.event
async def on_ready():
    print(f"✅ 已登入 {client.user.name}")
    synced = await tree.sync()
    print(f"🔁 已同步指令: {[cmd.name for cmd in synced]}")
    check_earthquake.start()

@tasks.loop(minutes=1)
async def check_earthquake():
    global latest_eq_title, CHANNEL_ID, MAG_THRESHOLD
    feed = feedparser.parse("https://www.cwa.gov.tw/rss/earthquake.xml")
    if not feed.entries:
        return

    latest_entry = feed.entries[0]
    title = latest_entry.title
    link = latest_entry.link
    summary = latest_entry.summary

    if title == latest_eq_title:
        return  # 沒有新地震

    latest_eq_title = title

    # 從標題或摘要中提取地震規模
    mag_match = re.search(r"規模(?:約)?([\d.]+)", title + summary)
    if mag_match:
        magnitude = float(mag_match.group(1))
        if magnitude < MAG_THRESHOLD:
            return  # 太小不通報
    else:
        magnitude = "?"

    # 抓震央圖片連結（CWB 通常會放在 <img> 裡）
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
        title="有感地震報告 - 規模5.6 - 台東近海",
        description="發震時間：2025/04/13 10:45\n震央位置：台東外海\n規模5.6",
        url="https://www.cwa.gov.tw/V8/C/E/index.html",
        color=discord.Color.orange()
    )
    embed.set_image(url="https://www.cwa.gov.tw/Data/earthquake_img/EEA20250413104500.jpg")
    await interaction.response.send_message(embed=embed)

@tree.command(name="設定地震頻道", description="設定地震通報的頻道")
@app_commands.describe(channel="要通報的文字頻道")
async def set_quake_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你沒有管理員權限。", ephemeral=True)
        return
    global CHANNEL_ID
    CHANNEL_ID = channel.id
    await interaction.response.send_message(f"✅ 地震通報頻道已設定為 {channel.mention}")

@tree.command(name="設定通知規模", description="設定地震通知的最小規模")
@app_commands.describe(threshold="通知的最小地震規模")
async def set_threshold(interaction: discord.Interaction, threshold: float):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你沒有管理員權限。", ephemeral=True)
        return
    global MAG_THRESHOLD
    MAG_THRESHOLD = threshold
    await interaction.response.send_message(f"✅ 已將通知規模設定為 {threshold} 級以上")

@tree.command(name="取消地震頻道", description="取消當前的地震通報頻道")
async def unset_quake_channel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你沒有管理員權限。", ephemeral=True)
        return
    global CHANNEL_ID
    CHANNEL_ID = 0
    await interaction.response.send_message("✅ 已取消地震通報頻道設定")

import traceback

@client.event
async def on_error(event, *args, **kwargs):
    print(f"出錯的事件: {event}")
    traceback.print_exc()


client.run(TOKEN)
