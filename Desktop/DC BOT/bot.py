import customtkinter as ctk
import asyncio
import threading
import discord
from discord.ext import commands
import pyperclip
import os
from dotenv import load_dotenv
import re
from urllib.parse import urlparse
import aiohttp
from bs4 import BeautifulSoup
import time
import base64

# 載入 .env 檔案
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True 
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

guild_options = {}
channel_options = {}
selected_guild = None
selected_channel = None

clipboard_monitoring = False
last_text = ""
last_copy_time = 0

# GUI setup
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
app = ctk.CTk()
app.title("Discord Link Paster")
app.geometry("500x300")

guild_var = ctk.StringVar()
channel_var = ctk.StringVar()
status_var = ctk.StringVar(value="剪貼簿監控：關閉")

guild_menu = ctk.CTkOptionMenu(app, variable=guild_var, values=[], command=lambda _: update_channels())
guild_menu.pack(pady=10)

channel_menu = ctk.CTkOptionMenu(app, variable=channel_var, values=[])
channel_menu.pack(pady=10)

status_label = ctk.CTkLabel(app, textvariable=status_var, text_color="red")
status_label.pack(pady=5)

monitor_button = ctk.CTkButton(app, text="開始監控剪貼簿", command=lambda: toggle_monitoring())
monitor_button.pack(pady=10)

@bot.event
async def on_ready():
    print(f"✅ Bot 登入成功：{bot.user.name}")
    await load_guilds()

async def load_guilds():
    await bot.wait_until_ready()
    guild_options.clear()
    for guild in bot.guilds:
        guild_options[guild.name] = guild

    def update_gui():
        guild_names = list(guild_options.keys())
        print(f"🧭 取得到的伺服器列表：{guild_names}")
        guild_menu.configure(values=guild_names)
        if guild_names:
            guild_var.set(guild_names[0])
            update_channels()

    app.after(0, update_gui)

def run_bot():
    asyncio.set_event_loop(asyncio.new_event_loop())
    bot.run(BOT_TOKEN)

def update_channels():
    global selected_guild
    gname = guild_var.get()
    selected_guild = guild_options.get(gname)
    if not selected_guild:
        return
    asyncio.run_coroutine_threadsafe(_update_channels(), bot.loop)

async def _update_channels():
    global selected_channel
    channels = [c for c in selected_guild.text_channels if c.permissions_for(selected_guild.me).send_messages]
    channel_options.clear()
    for ch in channels:
        channel_options[ch.name] = ch

    def update_channel_gui():
        channel_menu.configure(values=list(channel_options.keys()))
        if channels:
            channel_var.set(channels[0].name)
            selected_channel = channels[0]

    app.after(0, update_channel_gui)

def toggle_monitoring():
    global clipboard_monitoring, last_text, last_copy_time
    clipboard_monitoring = not clipboard_monitoring
    if clipboard_monitoring:
        last_text = pyperclip.paste()
        last_copy_time = time.time()
        monitor_button.configure(text="停止監控剪貼簿", fg_color="red")
        status_var.set("剪貼簿監控：啟動")
        threading.Thread(target=start_clipboard_loop, daemon=True).start()
    else:
        monitor_button.configure(text="開始監控剪貼簿", fg_color="green")
        status_var.set("剪貼簿監控：關閉")

def start_clipboard_loop():
    global last_text, clipboard_monitoring, last_copy_time
    while clipboard_monitoring:
        text = pyperclip.paste()
        if text != last_text and "http" in text:
            last_text = text
            last_copy_time = time.time()
            urls = re.findall(r'https?://\S+', text)
            for url in urls:
                asyncio.run_coroutine_threadsafe(process_and_send_embed(url), bot.loop)
        elif time.time() - last_copy_time > 20:
            clipboard_monitoring = False
            app.after(0, lambda: monitor_button.configure(text="開始監控剪貼簿", fg_color="green"))
            app.after(0, lambda: status_var.set("剪貼簿監控：關閉"))
        asyncio.run(asyncio.sleep(2))

def clean_url(url):
    parsed = urlparse(url)
    if "x.com" in parsed.netloc or "twitter.com" in parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return url

async def try_embed(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200 and response.content_type == 'application/json':
                    return await response.json()
    except Exception as e:
        print(f"❌ 連結嵌入 API 錯誤: {e}, url={url}")
    return None

async def get_twitter_embed(twitter_url):
    fx_src = "https://fxtwitter.com"
    api_url = f"{fx_src}/api/v1/preview?url={twitter_url}"
    data = await try_embed(api_url)
    if data:
        embed_url = f"{fx_src}{urlparse(twitter_url).path}"
        embed = discord.Embed(title=data.get("title", "無標題"), description=data.get("description"), url=embed_url, color=discord.Color.blue())
        if data.get("image"):
            embed.set_image(url=data["image"])
        return embed
    return None

async def simulate_img_upload(img_url):
    # 加入 Referer 頭，解決 Pixiv 防盜鏈問題
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.pixiv.net/"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(img_url, headers=headers) as response:
            if response.status == 200:
                # 如果成功，就返回原始圖片的 URL
                return img_url
            else:
                print(f"⚠️ 圖片下載失敗：{img_url}")
                return None


async def build_embed(url, color=discord.Color.blue()):
    if "x.com" in url or "twitter.com" in url:
        return await get_twitter_embed(url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                title = soup.find("meta", property="og:title") or soup.find("title")
                description = soup.find("meta", property="og:description")
                image = soup.find("meta", property="og:image")

                embed = discord.Embed(
                    title=title["content"] if title and title.has_attr("content") else title.text if title else "無標題",
                    description=description["content"] if description and description.has_attr("content") else None,
                    url=url,
                    color=color
                )
                if image and image.has_attr("content"):
                    new_img_url = await simulate_img_upload(image["content"])
                    embed.set_image(url=new_img_url)
                return embed
    except Exception as e:
        print(f"⚠️ 嵌入處理錯誤：{e}")
        return None

async def process_and_send_embed(url):
    global selected_channel
    cname = channel_var.get()
    selected_channel = channel_options.get(cname)
    url = clean_url(url)
    if selected_channel:
        embed = await build_embed(url, color=discord.Color.blue())
        try:
            if embed:
                await selected_channel.send(embed=embed)
                print(f"✅ 已嵌入：{url}")
            else:
                if "x.com" in url or "twitter.com" in url:
                    alt_url = f"https://fxtwitter.com{urlparse(url).path}"
                    await selected_channel.send(alt_url)
                    print(f"⚠️ 嵌入失敗，改貼 fxtwitter 連結：{alt_url}")
                else:
                    await selected_channel.send(url)
                    print(f"⚠️ 嵌入失敗，已貼上原始連結：{url}")
        except Exception as e:
            print(f"❌ 貼上錯誤：{e}")

threading.Thread(target=run_bot, daemon=True).start()
app.mainloop()

import pyperclip
import re
import time

# URL 正則表達式模式
url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'

def monitor_clipboard():
    last_clip = ""  # 記錄上次的剪貼簿內容
    while True:
        # 取得剪貼簿的內容
        current_clip = pyperclip.paste()
        
        # 如果剪貼簿內容有變動並且包含 URL
        if current_clip != last_clip and re.search(url_pattern, current_clip):
            last_clip = current_clip  # 更新剪貼簿內容
            urls = re.findall(url_pattern, current_clip)  # 提取所有 URL
            for url in urls:
                print(f"Found URL: {url}")
        
        # 每隔一段時間檢查剪貼簿（可以調整檢查頻率）
        time.sleep(1)

if __name__ == "__main__":
    print("Monitoring clipboard for URLs...")
    monitor_clipboard()
