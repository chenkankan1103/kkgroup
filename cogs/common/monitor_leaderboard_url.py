#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 排行榜 URL 自動監控模塊
每小時自動檢查 Discord CDN URL 是否過期，並更新 config.json
零額外流量消耗 - 只檢查 URL，不重新上傳圖片
"""

import discord
from discord.ext import commands, tasks
import os
import json
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class LeaderboardURLMonitor(commands.Cog):
    """自動監控排行榜 Discord CDN URL 並更新到 config.json"""

    def __init__(self, bot):
        self.bot = bot
        self.rank_channel_id = int(os.getenv("KKCOIN_RANK_CHANNEL_ID", 0))
        self.rank_message_id = int(os.getenv("KKCOIN_RANK_MESSAGE_ID", 0))
        self.config_path = os.path.join(os.path.dirname(__file__), "..", "docs", "config.json")
        
        # 啟動監控任務
        self.monitor_url.start()
        print("✅ LeaderboardURLMonitor 已啟動（每小時檢查一次）")

    def cog_unload(self):
        """卸載時停止任務"""
        self.monitor_url.cancel()
        print("⏹️ LeaderboardURLMonitor 已停止")

    @tasks.loop(hours=1)
    async def monitor_url(self):
        """
        每小時檢查一次 Discord CDN URL
        流程：
        1. 從 Discord 訊息獲取最新附件 URL
        2. 與 config.json 中的 URL 比較
        3. 如果不同 → 自動更新
        4. 可選：提交到 Git
        """
        try:
            # 檢查必要參數
            if not self.rank_channel_id or not self.rank_message_id:
                print("⚠️ 缺少排行榜頻道 ID 或訊息 ID，跳過監控")
                return

            # 獲取頻道
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到排行榜頻道 {self.rank_channel_id}")
                return

            # 獲取訊息
            try:
                msg = await channel.fetch_message(self.rank_message_id)
            except discord.NotFound:
                print(f"❌ 找不到排行榜訊息 {self.rank_message_id}（可能已被刪除）")
                return

            # 檢查附件
            if not msg.attachments:
                print(f"⚠️ 訊息 {self.rank_message_id} 沒有附件")
                return

            current_url = msg.attachments[0].url
            print(f"\n📍 當前 Discord CDN URL: {current_url[:70]}...")

            # 檢查 config.json
            if not os.path.exists(self.config_path):
                print(f"⚠️ config.json 不存在: {self.config_path}")
                return

            # 讀取舊 URL
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            old_url = config.get("imageURL", "")

            # 比較 URL
            if old_url == current_url:
                print("✅ 排行榜圖片 URL 未變更，無需更新")
                return

            # URL 已變更或為空 - 執行更新
            print(f"🔄 排行榜圖片 URL 已變更，更新中...")
            if old_url:
                print(f"   舊: {old_url[:70]}...")
            print(f"   新: {current_url[:70]}...")

            # 更新 config.json
            config["imageURL"] = current_url
            config["lastUpdated"] = datetime.now().isoformat()

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            print(f"✅ config.json 已更新 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

            # 可選：自動提交到 Git
            if os.getenv("ENABLE_LEADERBOARD_GIT_COMMIT", "false").lower() == "true":
                await self._commit_to_git(current_url)

        except Exception as e:
            print(f"❌ 監控排行榜 URL 失敗: {e}")
            import traceback
            traceback.print_exc()

    async def _commit_to_git(self, new_url):
        """
        提交 config.json 變更到 Git
        需要在 .env 中設置 ENABLE_LEADERBOARD_GIT_COMMIT=true
        """
        try:
            # 檢查是否為 Git 倉庫
            if not os.path.exists(".git"):
                print("⚠️ 不是 Git 倉庫，跳過提交")
                return

            # 添加文件
            result = subprocess.run(
                ["git", "add", "docs/config.json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # 提交
            commit_msg = f"chore: 更新排行榜 CDN URL ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # 推送
            subprocess.run(
                ["git", "push"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            print(f"📤 已提交到 Git: {commit_msg}")

        except subprocess.TimeoutExpired:
            print("⚠️ Git 操作超時")
        except subprocess.CalledProcessError as e:
            # 如果沒有更改，git commit 會失敗，但這是正常的
            if "nothing to commit" in e.stderr or "nothing staged for commit" in e.stderr:
                print("ℹ️ 沒有新變更需要提交")
            else:
                print(f"⚠️ Git 操作失敗: {e.stderr}")
        except Exception as e:
            print(f"❌ Git 操作異常: {e}")

    @monitor_url.before_loop
    async def before_monitor(self):
        """等待 bot 準備完成"""
        await self.bot.wait_until_ready()
        print("🔍 排行榜 URL 監控已就緒，將每小時執行一次")

    @monitor_url.after_loop
    async def after_monitor(self):
        """任務結束時的清理"""
        if self.monitor_url.is_being_cancelled():
            print("⏹️ 排行榜 URL 監控已停止")


# ============================================================
# Cog 加載函數
# ============================================================


async def setup(bot):
    """將 Cog 加載到 Bot 中"""
    await bot.add_cog(LeaderboardURLMonitor(bot))
    print("✅ LeaderboardURLMonitor Cog 已加載")
