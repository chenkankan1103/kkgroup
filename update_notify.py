import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess
import threading
import time
import socket

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID")

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

def wait_for_network(host="discord.com", port=443, retries=5, delay=5):
    """等待網路可用：試著解析 discord.com DNS"""
    for i in range(retries):
        try:
            socket.create_connection((host, port), timeout=3)
            print(f"✅ 網路已連通：{host}:{port}")
            return True
        except OSError:
            print(f"⏳ DNS 尚未就緒，等待 {delay} 秒...（第 {i+1}/{retries} 次）")
            time.sleep(delay)
    print(f"❌ 無法連線到 {host}:{port}，可能會造成 Discord bot 啟動失敗")
    return False

def run_process(command, delay=0):
    """執行子程式，並可延遲執行"""
    if delay > 0:
        print(f"⏳ 等待 {delay} 秒再啟動: {command}")
        time.sleep(delay)
    print(f"🚀 啟動進程: {command}")
    try:
        process = subprocess.Popen(command, shell=True, cwd="/home/e193752468/kkgroup")
        process.wait()
        print(f"✅ 進程結束: {command}")
    except Exception as e:
        print(f"❌ 執行失敗: {command} - {e}")

def start_all_bots():
    """啟動所有BOT服務"""
    print("🚀 準備啟動所有BOT服務...")
    
    # 等待網路（避免 Discord DNS 問題）
    wait_for_network()
    
    # 定義所有要啟動的服務（命令, 延遲秒數）
    services = [
        ("python bot.py", 5),        # 主 bot 延遲 5 秒
        ("python uibot.py", 10),     # UI bot 延遲 10 秒
        ("python web.py", 0),        # Flask 後台不用延遲
        ("python shopbot.py", 7),    # 黑市 bot 延遲 7 秒
    ]
    
    threads = []
    for command, delay in services:
        t = threading.Thread(target=run_process, args=(command, delay))
        t.daemon = True  # 設為 daemon thread，主程式結束時會自動結束
        t.start()
        threads.append(t)
    
    print("🎯 所有BOT服務已在背景啟動")
    return threads

async def send_restart_notification():
    """發送重啟通知到Discord"""
    intents = discord.Intents.default()
    notification_bot = commands.Bot(command_prefix="!", intents=intents)
    
    @notification_bot.event
    async def on_ready():
        try:
            channel = notification_bot.get_channel(int(DISCORD_SYS_CHANNEL_ID))
            if channel:
                last_update = get_last_commit()
                await channel.send(f"✅ BOT 已更新並重啟完成！\n📌 更新內容：{last_update}")
                print("📢 更新通知已發送")
            else:
                print("❌ 找不到指定的Discord頻道")
        except Exception as e:
            print(f"❌ 發送通知失敗: {e}")
        finally:
            await notification_bot.close()
    
    try:
        await notification_bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Discord通知BOT啟動失敗: {e}")

if __name__ == "__main__":
    print("🔄 開始更新流程...")
    
    # 步驟1：發送更新通知
    import asyncio
    try:
        asyncio.run(send_restart_notification())
    except Exception as e:
        print(f"⚠️ 通知發送過程中出現問題: {e}")
    
    # 步驟2：等待一下讓通知發送完成
    print("⏳ 等待通知發送完成...")
    time.sleep(3)
    
    # 步驟3：啟動所有BOT服務
    bot_threads = start_all_bots()
    
    # 步驟4：保持主程式運行（可選）
    try:
        print("🔄 所有服務運行中... 按 Ctrl+C 停止")
        while True:
            time.sleep(60)
            # 檢查所有線程是否還活著
            alive_threads = [t for t in bot_threads if t.is_alive()]
            if not alive_threads:
                print("⚠️ 所有BOT服務已停止")
                break
    except KeyboardInterrupt:
        print("\n🛑 收到停止信號，正在結束...")
    except Exception as e:
        print(f"❌ 主程式異常: {e}")
    
    print("🔚 程式結束")
