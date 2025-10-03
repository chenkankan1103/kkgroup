#!/usr/bin/env python3
"""
自動更新通知腳本（Crontab 執行）
功能：
1. 檢查 Git 更新
2. 拉取最新程式碼
3. 發送詳細更新通知到 Discord
4. 透過 Discord Webhook 觸發熱重載（避免重複）
"""

import os
import sys
import subprocess
import asyncio
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import discord
from discord.ext import commands

# 載入環境變數
load_dotenv()

# 配置
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))
GIT_DIR = os.getenv("GIT_DIR", "/home/e193752468/kkgroup")
RELOAD_TRIGGER_FILE = os.path.join(GIT_DIR, ".reload_trigger")

# 驗證配置
if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN 未設定於 .env")
if not DISCORD_SYS_CHANNEL_ID:
    raise RuntimeError("❌ DISCORD_SYS_CHANNEL_ID 未設定於 .env")

# ============================================================
# Git 操作函數
# ============================================================
def check_git_updates():
    """檢查是否有新的 Git 更新"""
    try:
        # 更新遠端資訊
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=GIT_DIR,
            check=True,
            capture_output=True
        )
        
        # 檢查落後的 commit 數量
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        
        commits_behind = int(result.stdout.strip())
        return commits_behind > 0, commits_behind
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 檢查更新失敗: {e.stderr if e.stderr else str(e)}")
        return False, 0
    except Exception as e:
        print(f"❌ 檢查更新異常: {e}")
        return False, 0

def get_git_update_details():
    """獲取詳細的更新資訊"""
    try:
        # 取得 commit 歷史（最多 10 個）
        commits_result = subprocess.run(
            [
                "git", "log", "HEAD..origin/main",
                "--pretty=format:• %s (%h) - %an, %ar",
                "--max-count=10"
            ],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        commits = commits_result.stdout.strip()
        
        # 取得變更的檔案列表
        files_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "origin/main"],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = files_result.stdout.strip().split("\n") if files_result.stdout.strip() else []
        
        # 取得變更統計
        stats_result = subprocess.run(
            ["git", "diff", "--stat", "HEAD", "origin/main"],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        stats = stats_result.stdout.strip()
        
        # 分析變更的檔案類型
        py_files = [f for f in changed_files if f.endswith('.py')]
        config_files = [f for f in changed_files if f.endswith(('.env', '.json', '.yaml', '.yml'))]
        other_files = [f for f in changed_files if f not in py_files and f not in config_files]
        
        return {
            "commits": commits if commits else "沒有具體 commit 資訊",
            "files": changed_files,
            "py_files": py_files,
            "config_files": config_files,
            "other_files": other_files,
            "stats": stats if stats else "沒有統計資訊",
            "needs_reload": len(py_files) > 0  # 只有 Python 檔案變更才需要重載
        }
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️ 獲取更新詳情失敗: {e.stderr if e.stderr else str(e)}")
        return {
            "commits": "無法獲取 commit 資訊",
            "files": [],
            "py_files": [],
            "config_files": [],
            "other_files": [],
            "stats": "",
            "needs_reload": False
        }
    except Exception as e:
        print(f"⚠️ 獲取更新詳情異常: {e}")
        return {
            "commits": str(e),
            "files": [],
            "py_files": [],
            "config_files": [],
            "other_files": [],
            "stats": "",
            "needs_reload": False
        }

def pull_git_updates():
    """執行 Git Pull"""
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
        
    except subprocess.CalledProcessError as e:
        return False, e.stderr if e.stderr else str(e)
    except Exception as e:
        return False, str(e)

def create_reload_trigger(update_info):
    """創建重載觸發檔案（讓 Bot 知道需要重載）"""
    try:
        trigger_data = {
            "timestamp": datetime.now().isoformat(),
            "needs_reload": update_info.get("needs_reload", False),
            "py_files": update_info.get("py_files", []),
            "processed": False
        }
        
        with open(RELOAD_TRIGGER_FILE, 'w', encoding='utf-8') as f:
            json.dump(trigger_data, f, indent=2)
        
        print(f"✅ 已創建重載觸發檔案: {RELOAD_TRIGGER_FILE}")
        return True
        
    except Exception as e:
        print(f"❌ 創建觸發檔案失敗: {e}")
        return False

# ============================================================
# Discord 通知函數
# ============================================================
async def send_update_notification(update_details, commits_count):
    """發送更新通知到 Discord"""
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        try:
            channel = bot.get_channel(DISCORD_SYS_CHANNEL_ID)
            if not channel:
                channel = await bot.fetch_channel(DISCORD_SYS_CHANNEL_ID)

            # 建立主要通知 Embed
            embed = discord.Embed(
                title="🔄 BOT 更新通知",
                description=f"發現 **{commits_count}** 個新提交，已拉取最新程式碼",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )

            # 添加 commit 資訊
            commit_text = update_details.get("commits", "無 commit 資訊")
            if len(commit_text) > 1000:
                commit_text = commit_text[:1000] + "\n..."
            embed.add_field(
                name="📝 更新內容",
                value=f"```\n{commit_text}\n```",
                inline=False
            )

            # 添加檔案變更資訊（分類顯示）
            py_files = update_details.get("py_files", [])
            config_files = update_details.get("config_files", [])
            other_files = update_details.get("other_files", [])
            
            if py_files:
                py_text = "\n".join([f"• {f}" for f in py_files[:8]])
                if len(py_files) > 8:
                    py_text += f"\n... 還有 {len(py_files) - 8} 個檔案"
                embed.add_field(
                    name="🐍 Python 檔案",
                    value=f"```\n{py_text}\n```",
                    inline=False
                )
            
            if config_files:
                config_text = "\n".join([f"• {f}" for f in config_files[:5]])
                if len(config_files) > 5:
                    config_text += f"\n... 還有 {len(config_files) - 5} 個檔案"
                embed.add_field(
                    name="⚙️ 配置檔案",
                    value=f"```\n{config_text}\n```",
                    inline=False
                )
            
            if other_files:
                other_text = "\n".join([f"• {f}" for f in other_files[:5]])
                if len(other_files) > 5:
                    other_text += f"\n... 還有 {len(other_files) - 5} 個檔案"
                embed.add_field(
                    name="📄 其他檔案",
                    value=f"```\n{other_text}\n```",
                    inline=False
                )

            # 添加統計資訊
            stats_text = update_details.get("stats", "")
            if stats_text:
                # 限制長度
                if len(stats_text) > 800:
                    lines = stats_text.split('\n')
                    stats_text = '\n'.join(lines[:15]) + "\n... (省略更多)"
                embed.add_field(
                    name="📊 變更統計",
                    value=f"```diff\n{stats_text}\n```",
                    inline=False
                )

            # 添加重載狀態
            if update_details.get("needs_reload", False):
                embed.add_field(
                    name="🔄 重載狀態",
                    value="✅ 已觸發自動重載（等待 Bot 處理）",
                    inline=False
                )
            else:
                embed.add_field(
                    name="ℹ️ 重載狀態",
                    value="⏭️ 無需重載（僅非程式碼檔案變更）",
                    inline=False
                )

            # 添加時間戳記
            embed.set_footer(text="自動更新腳本")

            await channel.send(embed=embed)
            print("✅ Discord 通知已發送")
            
        except discord.errors.Forbidden:
            print("❌ 權限不足：Bot 無法發送訊息到指定頻道")
        except discord.errors.NotFound:
            print(f"❌ 找不到頻道 ID: {DISCORD_SYS_CHANNEL_ID}")
        except Exception as e:
            print(f"❌ 發送 Discord 通知失敗: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await bot.close()

    try:
        await bot.start(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ Discord Token 無效")
    except Exception as e:
        print(f"❌ Discord Bot 啟動失敗: {e}")

# ============================================================
# 主流程
# ============================================================
async def main():
    """主要執行流程"""
    print("=" * 60)
    print(f"🕐 執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 檢查更新
    print("🔍 檢查 Git 更新...")
    has_update, commits_count = check_git_updates()
    
    if not has_update:
        print("ℹ️  沒有新更新")
        print("=" * 60)
        return

    print(f"📥 發現 {commits_count} 個更新")
    
    # 2. 獲取更新詳情
    print("📋 獲取更新詳情...")
    update_details = get_git_update_details()
    
    # 3. 拉取更新
    print("⬇️  拉取最新程式碼...")
    success, pull_result = pull_git_updates()
    
    if not success:
        print(f"❌ Git 拉取失敗: {pull_result}")
        print("=" * 60)
        return
    
    print("✅ 程式碼已更新")
    
    # 4. 創建重載觸發（如果需要）
    if update_details.get("needs_reload", False):
        print("🔄 創建重載觸發...")
        create_reload_trigger(update_details)
    else:
        print("ℹ️  無需重載（僅配置或文件變更）")
    
    # 5. 發送 Discord 通知
    print("📨 發送 Discord 通知...")
    await send_update_notification(update_details, commits_count)
    
    print("=" * 60)
    print("✅ 自動更新流程完成")
    print("=" * 60)

# ============================================================
# 程式入口
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(main())
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n⚠️ 使用者中斷")
        sys.exit(130)
    except Exception as e:
        print(f"❌ 程式異常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
