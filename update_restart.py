#!/usr/bin/env python3
"""
自動更新和重啟腳本
功能：
1. 檢查並拉取 git 更新
2. 通過 systemd 重啟服務
3. 發送更新通知到 Discord
4. 適配 crontab 定時執行
"""

import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path

# 設定工作目錄和環境變數
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = Path("/home/e193752468/kkgroup")
ENV_FILE = PROJECT_DIR / ".env"

# 載入環境變數
load_dotenv(ENV_FILE)
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID")

# systemd 服務名稱
SYSTEMD_SERVICES = ["bot.service", "shopbot.service", "uibot.service"]

def log(message):
    """帶時間戳記的日誌輸出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()  # 確保 crontab 能看到輸出

def check_git_updates():
    """檢查是否有新的 git 更新"""
    try:
        log("🔍 檢查 Git 更新...")
        
        # 先 fetch 遠端更新
        subprocess.run(
            ["git", "fetch"],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True
        )
        
        # 比較本地和遠端的差異
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        
        commits_behind = int(result.stdout.strip())
        
        if commits_behind > 0:
            log(f"📥 發現 {commits_behind} 個新提交")
            return True, commits_behind
        else:
            log("✅ 已是最新版本，無需更新")
            return False, 0
            
    except subprocess.CalledProcessError as e:
        log(f"❌ Git 檢查失敗: {e}")
        return False, 0
    except Exception as e:
        log(f"❌ 檢查更新時發生錯誤: {e}")
        return False, 0

def get_git_update_details():
    """獲取詳細的 Git 更新資訊"""
    try:
        # 獲取最新的 commit (最多5個)
        commits_result = subprocess.run(
            ["git", "log", "HEAD..origin/main", 
             "--pretty=format:• %s (%h) - %an", 
             "--max-count=5"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True
        )
        commits = commits_result.stdout.strip()
        
        # 獲取更新的檔案列表
        files_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "origin/main"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True
        )
        changed_files = files_result.stdout.strip().split('\n') if files_result.stdout.strip() else []
        
        # 獲取統計資訊
        stats_result = subprocess.run(
            ["git", "diff", "--stat", "HEAD", "origin/main"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True
        )
        stats = stats_result.stdout.strip()
        
        return {
            "commits": commits if commits else "無 commit 資訊",
            "files": changed_files,
            "stats": stats if stats else "無統計資訊"
        }
    except Exception as e:
        log(f"⚠️ 獲取更新詳情失敗: {e}")
        return {
            "commits": "無法取得 commit 資訊",
            "files": [],
            "stats": "無法取得統計資訊"
        }

def pull_git_updates():
    """拉取 git 更新（保留本地 user_data.db）"""
    try:
        log("📥 準備拉取 Git 更新...")
        
        db_file = PROJECT_DIR / "user_data.db"
        db_backup = PROJECT_DIR / "user_data.db.update_backup"
        
        # 1️⃣ 備份本地 user_data.db（最重要！）
        if db_file.exists():
            log("💾 備份本地 user_data.db...")
            import shutil
            shutil.copy2(db_file, db_backup)
            log(f"✅ 已備份到 {db_backup.name}")
        
        # 2️⃣ 清潔未追蹤的文件（除了 venv 和 character_images）
        log("🧹 清潔工作目錄...")
        try:
            subprocess.run(
                ["git", "clean", "-fd", "-e", "venv", "-e", "character_images"],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=30
            )
            log("✅ 已清潔未追蹤文件")
        except Exception as e:
            log(f"⚠️ 清潔文件時出錯（繼續）: {e}")
        
        # 3️⃣ 強制重置本地修改到 origin/main
        log("🔄 強制重置到 origin/main...")
        try:
            result = subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )
            log("✅ 已強制重置")
        except subprocess.CalledProcessError as e:
            log(f"❌ 強制重置失敗: {e.stderr}")
            return False, f"重置失敗: {e.stderr}"
        
        # 4️⃣ 恢復本地 user_data.db（覆蓋 GitHub 上的舊版本）
        if db_backup.exists():
            log("📂 恢復本地 user_data.db...")
            import shutil
            shutil.copy2(db_backup, db_file)
            log(f"✅ 已恢復本地數據庫")
            
            # 清理備份
            db_backup.unlink()
        
        log("✅ Git 更新完成（保留了本地數據庫）")
        return True, "更新成功並保留本地 user_data.db"
        
    except subprocess.CalledProcessError as e:
        log(f"❌ Git 操作失敗: {e.stderr}")
        return False, str(e)
    except Exception as e:
        log(f"❌ Git 更新過程發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)

def restart_systemd_services():
    """重啟所有 systemd 服務"""
    log("🔄 開始重啟服務...")
    
    success_count = 0
    failed_services = []
    
    for service in SYSTEMD_SERVICES:
        try:
            # 使用 sudo systemctl restart (如果需要密碼，需要在 sudoers 中設定 NOPASSWD)
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                log(f"✅ 服務 {service} 重啟成功")
                success_count += 1
            else:
                log(f"❌ 服務 {service} 重啟失敗: {result.stderr}")
                failed_services.append(service)
                
        except subprocess.TimeoutExpired:
            log(f"⏱️ 服務 {service} 重啟超時")
            failed_services.append(service)
        except Exception as e:
            log(f"❌ 重啟服務 {service} 時發生錯誤: {e}")
            failed_services.append(service)
    
    return success_count == len(SYSTEMD_SERVICES), failed_services

async def send_discord_notification(update_details, commits_count, notification_type="update"):
    """發送 Discord 通知"""
    if not TOKEN or not DISCORD_SYS_CHANNEL_ID:
        log("⚠️ 缺少 Discord 配置，跳過通知")
        return
    
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    @bot.event
    async def on_ready():
        try:
            channel_id = int(DISCORD_SYS_CHANNEL_ID)
            channel = bot.get_channel(channel_id)
            
            if not channel:
                channel = await bot.fetch_channel(channel_id)
            
            # 建立 Embed
            if notification_type == "update":
                embed = discord.Embed(
                    title="🔄 機器人自動更新完成",
                    description=f"發現 {commits_count} 個新提交，已完成更新和重啟",
                    color=0x00FF00,
                    timestamp=datetime.now()
                )
                
                # 添加 commit 資訊
                commits_text = update_details.get('commits', '無')[:1000]
                embed.add_field(
                    name="📝 更新內容",
                    value=f"```\n{commits_text}\n```",
                    inline=False
                )
                
                # 添加修改的檔案
                files = update_details.get('files', [])
                if files:
                    files_text = '\n'.join([f"• {f}" for f in files[:10]])
                    if len(files) > 10:
                        files_text += f"\n... 還有 {len(files) - 10} 個檔案"
                    embed.add_field(
                        name=f"📂 修改的檔案 ({len(files)} 個)",
                        value=f"```\n{files_text}\n```",
                        inline=False
                    )
                
                embed.set_footer(text="✅ 所有服務已重啟")
                
            elif notification_type == "error":
                embed = discord.Embed(
                    title="❌ 機器人更新失敗",
                    description="更新過程中發生錯誤",
                    color=0xFF0000,
                    timestamp=datetime.now()
                )
                embed.add_field(
                    name="錯誤訊息",
                    value=update_details.get('error', '未知錯誤'),
                    inline=False
                )
            
            await channel.send(embed=embed)
            log("📢 Discord 通知已發送")
            
        except Exception as e:
            log(f"❌ 發送 Discord 通知失敗: {e}")
        finally:
            await bot.close()
    
    try:
        await asyncio.wait_for(bot.start(TOKEN), timeout=15)
    except asyncio.TimeoutError:
        log("⏱️ Discord 通知超時")
    except Exception as e:
        log(f"❌ Discord Bot 啟動失敗: {e}")

async def main():
    """主要執行流程"""
    log("=" * 60)
    log("🚀 開始執行自動更新檢查")
    log("=" * 60)
    
    # 1. 檢查是否有更新
    has_updates, commits_count = check_git_updates()
    if not has_updates:
        log("✅ 無需更新，程式結束")
        return
    
    # 2. 獲取更新詳情
    update_details = get_git_update_details()
    
    # 3. 拉取更新
    success, result = pull_git_updates()
    if not success:
        log("❌ 更新失敗，程式結束")
        await send_discord_notification(
            {"error": result}, 
            0, 
            "error"
        )
        return
    
    # 4. 重啟服務
    restart_success, failed_services = restart_systemd_services()
    
    if not restart_success:
        log(f"⚠️ 部分服務重啟失敗: {', '.join(failed_services)}")
        update_details['error'] = f"失敗的服務: {', '.join(failed_services)}"
        await send_discord_notification(update_details, commits_count, "error")
    else:
        log("✅ 所有服務重啟成功")
        # 5. 發送成功通知
        await send_discord_notification(update_details, commits_count, "update")
    
    log("=" * 60)
    log("✅ 自動更新流程完成")
    log("=" * 60)

if __name__ == "__main__":
    try:
        # 設定環境變數 (crontab 需要)
        os.environ.setdefault('PATH', '/usr/local/bin:/usr/bin:/bin')
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        log("\n🛑 收到中斷信號，程式結束")
        sys.exit(0)
    except Exception as e:
        log(f"❌ 程式執行異常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
