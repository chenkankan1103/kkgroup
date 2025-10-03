#!/usr/bin/env python3
"""
自動更新通知腳本（不重啟 Bot）
功能：
1. 檢查 Git 更新
2. 發送詳細更新通知到 Discord
"""

import os
import sys
import subprocess
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))
GIT_DIR = "/home/e193752468/kkgroup"

if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN 未設定於 .env")

if not DISCORD_SYS_CHANNEL_ID:
    raise RuntimeError("❌ DISCORD_SYS_CHANNEL_ID 未設定於 .env")

# ------------------------------
# Git 操作
# ------------------------------
def check_git_updates():
    try:
        subprocess.run(["git", "fetch"], cwd=GIT_DIR, check=True)
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=GIT_DIR,
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
    try:
        commits = subprocess.check_output([
            "git", "log", "HEAD..origin/main",
            "--pretty=format:• %s (%h) - %an",
            "--max-count=5"
        ], cwd=GIT_DIR).decode("utf-8").strip()

        changed_files = subprocess.check_output([
            "git", "diff", "--name-only", "HEAD", "origin/main"
        ], cwd=GIT_DIR).decode("utf-8").strip()

        stats = subprocess.check_output([
            "git", "diff", "--stat", "HEAD", "origin/main"
        ], cwd=GIT_DIR).decode("utf-8").strip()

        return {
            "commits": commits if commits else "沒有具體 commit 資訊",
            "files": changed_files.split("\n") if changed_files else [],
            "stats": stats if stats else "沒有統計資訊"
        }
    except Exception as e:
        print(f"⚠️ 獲取更新詳情失敗: {e}")
        return {"commits": str(e), "files": [], "stats": ""}

def pull_git_updates():
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=GIT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except Exception as e:
        return False, str(e)

# ------------------------------
# Discord 發送
# ------------------------------
async def send_update_notification(update_details, commits_count):
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        try:
            channel = bot.get_channel(DISCORD_SYS_CHANNEL_ID)
            if not channel:
                channel = await bot.fetch_channel(DISCORD_SYS_CHANNEL_ID)

            embed = discord.Embed(
                title="🔄 BOT 更新通知",
                description=f"發現 {commits_count} 個新提交，已拉取最新程式碼",
                color=0xFFA500,
                timestamp=datetime.now()
            )

            commit_text = update_details.get("commits", "無 commit 資訊")
            if len(commit_text) > 1000:
                commit_text = commit_text[:1000] + "..."
            embed.add_field(name="📝 更新內容", value=f"```\n{commit_text}\n```", inline=False)

            if update_details.get("files"):
                files_text = "\n".join([f"• {f}" for f in update_details["files"][:8]])
                if len(update_details["files"]) > 8:
                    files_text += f"\n... 還有 {len(update_details['files']) - 8} 個檔案"
                embed.add_field(name="📂 修改檔案", value=f"```\n{files_text}\n```", inline=False)

            stats_text = update_details.get("stats", "")
            if stats_text:
                embed.add_field(name="📊 變更統計", value=f"```\n{stats_text}\n```", inline=False)

            await channel.send(embed=embed)
        except Exception as e:
            print(f"❌ 發送 Discord 通知失敗: {e}")
        finally:
            await bot.close()

    await bot.start(TOKEN)

# ------------------------------
# 主流程
# ------------------------------
async def main():
    print("🔍 檢查 Git 更新...")
    has_update, commits_count = check_git_updates()
    if not has_update:
        print("ℹ️ 沒有新更新")
        return

    print(f"📥 發現 {commits_count} 個更新，拉取中...")
    success, pull_result = pull_git_updates()
    if not success:
        print(f"❌ Git 拉取失敗: {pull_result}")
        return

    update_details = get_git_update_details()
    await send_update_notification(update_details, commits_count)
    print("✅ 更新通知完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ 程式異常: {e}")
        sys.exit(1)
