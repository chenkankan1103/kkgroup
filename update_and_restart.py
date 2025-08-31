#!/usr/bin/env python3
"""
自動更新和重啟腳本
功能：
1. 檢查並拉取 git 更新
2. 關閉指定的機器人進程
3. 發送詳細更新通知到 Discord
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
from datetime import datetime

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
        return commits_behind > 0, commits_behind
    except Exception as e:
        print(f"❌ 檢查更新失敗: {e}")
        return False, 0

def get_git_update_details():
    """獲取詳細的 Git 更新資訊"""
    try:
        # 獲取最新的幾個 commit
        commits = subprocess.check_output([
            "git", "log", "HEAD..origin/main", 
            "--pretty=format:• %s (%h) - %an", 
            "--max-count=5"
        ], cwd="/home/e193752468/kkgroup").decode("utf-8").strip()
        
        # 獲取更新的檔案列表
        changed_files = subprocess.check_output([
            "git", "diff", "--name-only", "HEAD", "origin/main"
        ], cwd="/home/e193752468/kkgroup").decode("utf-8").strip()
        
        # 獲取新增和刪除的行數
        stats = subprocess.check_output([
            "git", "diff", "--stat", "HEAD", "origin/main"
        ], cwd="/home/e193752468/kkgroup").decode("utf-8").strip()
        
        return {
            "commits": commits if commits else "沒有具體 commit 資訊",
            "files": changed_files.split('\n') if changed_files else [],
            "stats": stats if stats else "沒有統計資訊"
        }
    except Exception as e:
        print(f"⚠️ 獲取更新詳情失敗: {e}")
        return {
            "commits": f"⚠️ 無法取得 commit 資訊: {e}",
            "files": [],
            "stats": "無法取得統計資訊"
        }

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
        return True, result.stdout
    except Exception as e:
        print(f"❌ Git 更新失敗: {e}")
        return False, str(e)

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

async def send_update_notification(update_details, commits_count, notification_type="start"):
    """發送詳細更新通知到Discord"""
    intents = discord.Intents.default()
    intents.message_content = True  # 確保有訊息內容權限
    notification_bot = commands.Bot(command_prefix="!", intents=intents)
    
    @notification_bot.event
    async def on_ready():
        print(f"🔗 Discord BOT 已連線: {notification_bot.user}")
        try:
            channel_id = int(DISCORD_SYS_CHANNEL_ID)
            print(f"🎯 嘗試取得頻道 ID: {channel_id}")
            
            channel = notification_bot.get_channel(channel_id)
            if not channel:
                print("❌ 透過 get_channel 找不到頻道，嘗試 fetch_channel...")
                try:
                    channel = await notification_bot.fetch_channel(channel_id)
                except Exception as fetch_error:
                    print(f"❌ fetch_channel 也失敗: {fetch_error}")
                    return
            
            print(f"📍 找到頻道: {channel.name} (ID: {channel.id})")
            
            if notification_type == "start":
                # 開始更新通知
                embed = discord.Embed(
                    title="🔄 BOT 更新開始",
                    description="正在進行自動更新和重啟...",
                    color=0xFFA500,  # 橙色
                    timestamp=datetime.now()
                )
                
                # 添加 commit 資訊
                commit_text = update_details.get('commits', '無 commit 資訊')
                if len(commit_text) > 1000:  # Discord field 限制
                    commit_text = commit_text[:1000] + "..."
                
                embed.add_field(
                    name=f"📝 更新內容 ({commits_count} 個新提交)",
                    value=f"```\n{commit_text}\n```",
                    inline=False
                )
                
                # 添加修改的檔案
                if update_details.get('files'):
                    files_text = '\n'.join([f"• {file}" for file in update_details['files'][:8]])
                    if len(update_details['files']) > 8:
                        files_text += f"\n... 還有 {len(update_details['files']) - 8} 個檔案"
                    
                    if len(files_text) > 1000:
                        files_text = files_text[:1000] + "..."
                        
                    embed.add_field(
                        name="📂 修改的檔案",
                        value=f"```\n{files_text}\n```",
                        inline=False
                    )
                
                # 添加統計資訊
                stats_text = update_details.get('stats', '')
                if stats_text and len(stats_text) < 1000:
                    embed.add_field(
                        name="📊 變更統計",
                        value=f"```\n{stats_text}\n```",
                        inline=False
                    )
                
                embed.set_footer(text="系統將自動重啟所有服務")
                
            elif notification_type == "complete":
                # 完成通知
                embed = discord.Embed(
                    title="✅ BOT 更新完成",
                    description="所有服務已成功更新並重啟！",
                    color=0x00FF00,  # 綠色
                    timestamp=datetime.now()
                )
                embed.set_footer(text="所有機器人現在運行最新版本")
            
            elif notification_type == "error":
                # 錯誤通知
                embed = discord.Embed(
                    title="❌ BOT 更新失敗",
                    description="更新過程中發生錯誤，請檢查日誌",
                    color=0xFF0000,  # 紅色
                    timestamp=datetime.now()
                )
            
            # 先嘗試發送 embed，如果失敗則發送普通訊息
            try:
                await channel.send(embed=embed)
                print(f"📢 {notification_type} Embed 通知已發送")
            except Exception as embed_error:
                print(f"⚠️ Embed 發送失敗，嘗試普通訊息: {embed_error}")
                # 發送純文字版本
                simple_message = f"🔄 **BOT 更新通知**\n"
                if notification_type == "start":
                    simple_message += f"正在更新 ({commits_count} 個新提交)..."
                elif notification_type == "complete":
                    simple_message += "✅ 更新完成！所有服務已重啟"
                elif notification_type == "error":
                    simple_message += "❌ 更新失敗，請檢查日誌"
                
                await channel.send(simple_message)
                print(f"📢 {notification_type} 簡單通知已發送")
                
        except Exception as e:
            print(f"❌ 發送通知過程中出錯: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("🔒 關閉通知 BOT 連線")
            await notification_bot.close()
    
    @notification_bot.event
    async def on_error(event, *args, **kwargs):
        print(f"❌ Discord BOT 事件錯誤 {event}: {args}")
    
    try:
        print("🚀 啟動通知 BOT...")
        if not TOKEN:
            print("❌ 找不到 DISCORD_BOT_TOKEN")
            return
        if not DISCORD_SYS_CHANNEL_ID:
            print("❌ 找不到 DISCORD_SYS_CHANNEL_ID")
            return
            
        await notification_bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Discord 通知 BOT 啟動失敗: {e}")
        import traceback
        traceback.print_exc()

def restart_systemd_services():
    """重啟 systemd 服務 (如果有配置的話)"""
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
    has_updates, commits_count = check_git_updates()
    if not has_updates:
        print("ℹ️ 沒有新的更新，程式結束")
        return
    
    print(f"📥 發現 {commits_count} 個新更新，開始更新流程...")
    
    # 獲取詳細更新資訊
    update_details = get_git_update_details()
    
    # 發送開始更新的詳細通知
    try:
        await send_update_notification(update_details, commits_count, "start")
        await asyncio.sleep(3)  # 等待通知發送完成
    except Exception as e:
        print(f"⚠️ 發送開始通知失敗: {e}")
    
    # 停止機器人進程
    if not stop_bot_processes():
        print("❌ 無法停止所有機器人進程，取消更新")
        try:
            await send_update_notification({}, 0, "error")
        except Exception as e:
            print(f"⚠️ 發送錯誤通知失敗: {e}")
        return
    
    # 拉取更新
    success, pull_result = pull_git_updates()
    if not success:
        print("❌ Git 更新失敗")
        try:
            await send_update_notification({}, 0, "error")
        except Exception as e:
            print(f"⚠️ 發送錯誤通知失敗: {e}")
        return
    
    # 重啟 systemd 服務 (如果配置了的話)
    restart_systemd_services()
    
    # 發送完成通知
    try:
        await send_update_notification({}, 0, "complete")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"⚠️ 發送完成通知失敗: {e}")
    
    print("✅ 更新流程完成！")
    print("ℹ️ systemd 將自動重啟機器人服務")

async def test_notification():
    """測試 Discord 通知功能"""
    print("🧪 測試 Discord 通知功能...")
    
    test_update_details = {
        "commits": "• 測試更新通知功能 (abc123) - Test User\n• 修復機器人重啟問題 (def456) - Test User",
        "files": ["bot.py", "update_script.py", "config.py"],
        "stats": "3 files changed, 25 insertions(+), 10 deletions(-)"
    }
    
    try:
        await send_update_notification(test_update_details, 2, "start")
        await asyncio.sleep(3)
        await send_update_notification({}, 0, "complete")
        print("✅ 測試通知發送完成")
    except Exception as e:
        print(f"❌ 測試通知失敗: {e}")

if __name__ == "__main__":
    import sys
    
    try:
        # 如果有 test 參數，執行測試
        if len(sys.argv) > 1 and sys.argv[1] == "test":
            asyncio.run(test_notification())
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 收到中斷信號，程式結束")
    except Exception as e:
        print(f"❌ 程式執行異常: {e}")
