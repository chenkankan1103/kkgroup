#!/usr/bin/env python3
"""
自動更新和重啟腳本
功能：
1. 檢查並拉取 git 更新
2. 關閉指定的機器人進程
3. 發送更新通知到 Discord
4. 讓 systemd 自動重啟服務
"""

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess
import time
import signal
import psutil
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID")

# 需要關閉的機器人腳本名稱
BOT_SCRIPTS = ["bot.py", "shopbot.py", "uibot.py"]

def check_git_updates():
    """檢查是否有新的 git 更新"""
    try:
        # 先 fetch 遠端更新
        subprocess.run(["git", "fetch"], cwd="/home/e193752468/kkgroup", check=True)
        
        # 比較本地和遠端的差異
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd="/home/e193752468/kkgroup",
            capture_output=True,
            text=True,
            check=True
        )
        
        commits_behind = int(result.stdout.strip())
        return commits_behind > 0
    except Exception as e:
        print(f"❌ 檢查更新失敗: {e}")
        return False

def pull_git_updates():
    """拉取 git 更新"""
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd="/home/e193752468/kkgroup",
            capture_output=True,
            text=True,
            check=True
        )
        print("✅ Git 更新完成")
        return True
    except Exception as e:
        print(f"❌ Git 更新失敗: {e}")
        return False

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

def find_bot_processes():
    """找到所有指定的機器人進程"""
    bot_processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if not cmdline:
                continue
                
            # 檢查是否是 Python 進程且執行我們的機器人腳本
            if len(cmdline) >= 2 and 'python' in cmdline[0].lower():
                script_name = os.path.basename(cmdline[1]) if len(cmdline) > 1 else ""
                if script_name in BOT_SCRIPTS:
                    bot_processes.append({
                        'pid': proc.info['pid'],
                        'script': script_name,
                        'process': proc
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied, IndexError):
            continue
    
    return bot_processes

def stop_bot_processes():
    """優雅地停止所有機器人進程"""
    print("🔍 尋找機器人進程...")
    bot_processes = find_bot_processes()
    
    if not bot_processes:
        print("ℹ️ 沒有找到運行中的機器人進程")
        return True
    
    print(f"📍 找到 {len(bot_processes)} 個機器人進程")
    
    # 先嘗試優雅關閉 (SIGTERM)
    for bot in bot_processes:
        try:
            print(f"🛑 正在關閉 {bot['script']} (PID: {bot['pid']})")
            bot['process'].terminate()
        except psutil.NoSuchProcess:
            print(f"✅ {bot['script']} 已經停止")
        except Exception as e:
            print(f"⚠️ 無法關閉 {bot['script']}: {e}")
    
    # 等待進程優雅退出
    print("⏳ 等待進程優雅退出...")
    time.sleep(5)
    
    # 檢查是否還有未關閉的進程，強制終止
    remaining_processes = find_bot_processes()
    if remaining_processes:
        print("💀 強制終止剩餘進程...")
        for bot in remaining_processes:
            try:
                bot['process'].kill()
                print(f"💀 強制終止 {bot['script']} (PID: {bot['pid']})")
            except psutil.NoSuchProcess:
                print(f"✅ {bot['script']} 已經停止")
            except Exception as e:
                print(f"❌ 無法強制終止 {bot['script']}: {e}")
        time.sleep(2)
    
    # 最終檢查
    final_check = find_bot_processes()
    if final_check:
        print("❌ 仍有機器人進程未能停止:")
        for bot in final_check:
            print(f"  - {bot['script']} (PID: {bot['pid']})")
        return False
    else:
        print("✅ 所有機器人進程已成功停止")
        return True

async def send_update_notification(update_content):
    """發送更新通知到Discord"""
    intents = discord.Intents.default()
    notification_bot = commands.Bot(command_prefix="!", intents=intents)
    
    @notification_bot.event
    async def on_ready():
        try:
            channel = notification_bot.get_channel(int(DISCORD_SYS_CHANNEL_ID))
            if channel:
                await channel.send(f"🔄 BOT 正在更新重啟中...\n📌 更新內容：{update_content}")
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

def restart_systemd_services():
    """重啟 systemd 服務 (如果有配置的話)"""
    # 這裡假設你的 systemd 服務名稱，你需要根據實際情況調整
    services = ["discord-bot", "discord-shopbot", "discord-uibot"]
    
    for service in services:
        try:
            # 檢查服務是否存在
            check_result = subprocess.run(
                ["systemctl", "is-enabled", service],
                capture_output=True,
                text=True
            )
            
            if check_result.returncode == 0:
                print(f"🔄 重啟服務: {service}")
                subprocess.run(["systemctl", "restart", service], check=True)
                print(f"✅ 服務 {service} 重啟成功")
            else:
                print(f"ℹ️ 服務 {service} 不存在或未啟用")
                
        except subprocess.CalledProcessError as e:
            print(f"❌ 重啟服務 {service} 失敗: {e}")
        except Exception as e:
            print(f"❌ 處理服務 {service} 時發生錯誤: {e}")

async def main():
    """主要執行流程"""
    print("🔍 開始檢查更新...")
    
    # 檢查是否有更新
    if not check_git_updates():
        print("ℹ️ 沒有新的更新，程式結束")
        return
    
    print("📥 發現新更新，開始更新流程...")
    
    # 獲取更新內容
    update_content = get_last_commit()
    
    # 發送開始更新的通知
    try:
        await send_update_notification(update_content)
        await asyncio.sleep(3)  # 等待通知發送完成
    except Exception as e:
        print(f"⚠️ 發送開始通知失敗: {e}")
    
    # 停止機器人進程
    if not stop_bot_processes():
        print("❌ 無法停止所有機器人進程，取消更新")
        return
    
    # 拉取更新
    if not pull_git_updates():
        print("❌ Git 更新失敗")
        return
    
    # 重啟 systemd 服務 (如果配置了的話)
    restart_systemd_services()
    
    print("✅ 更新流程完成！")
    print("ℹ️ systemd 將自動重啟機器人服務")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 收到中斷信號，程式結束")
    except Exception as e:
        print(f"❌ 程式執行異常: {e}")
