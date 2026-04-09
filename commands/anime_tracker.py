# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 自動通知新上架集數

功能：
- 定時檢查 Bahamut 首頁 API，獲取最近更新的動畫集數
- 追蹤已通知過的集數（videoSn），防止重複通知
- 初次啟動時執行 bootstrap，記錄當前所有集數，不發送通知
- 之後的每次檢查，只通知"新出現的集"（新 videoSn）
- 發送格式化 Discord Embed 到指定頻道

API：
- https://api.gamer.com.tw/mobile_app/anime/v3/index.php
- 返回 newAnime[]：最近更新的集列表
- 每個集包含：animeSn, videoSn, title, volume, cover, upTime 等

關鍵設計：
- 追蹤 videoSn（集的唯一識別符）而非 animeSn（動畫ID）
- 原因：同一個動畫可能有多個最近更新的集，每個有不同的 videoSn
- Bootstrap：首次運行記錄所有現存 videoSn，之後只通知新集
"""

import discord
from discord.ext import commands, tasks
import asyncio
import aiohttp
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# 配置
ANIME_CHANNEL_ID = 1490890263709745224  # 你的動畫通知頻道
ANIME_DB_PATH = Path("./uibot_anime.db")  # 獨立的動畫追蹤數據庫
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # 秒

# 表名與欄位
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"


class AnimeDatabase:
    """處理 Bahamut 動畫追蹤所需的數據庫操作"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """初始化數據庫表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. 已通知集列表（主要追蹤表）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {NOTIFIED_TABLE} (
                        videoSn INTEGER PRIMARY KEY,
                        animeSn INTEGER NOT NULL,
                        anime_name TEXT NOT NULL,
                        volume TEXT,
                        cover_url TEXT,
                        notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 2. Bootstrap 標誌（記錄是否完成初始化）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {BOOTSTRAP_FLAG_TABLE} (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        bootstrap_completed INTEGER DEFAULT 0,
                        completed_at TIMESTAMP
                    )
                """)
                
                conn.commit()
                logger.info(f"✅ Anime database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to init anime DB: {e}")
            raise
    
    def is_bootstrap_completed(self) -> bool:
        """檢查是否已完成 bootstrap（初始化）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT bootstrap_completed FROM {BOOTSTRAP_FLAG_TABLE} WHERE id = 1")
                result = cursor.fetchone()
                return result and result[0] == 1
        except Exception as e:
            logger.error(f"❌ Error checking bootstrap: {e}")
            return False
    
    def mark_bootstrap_completed(self):
        """標記 bootstrap 完成"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {BOOTSTRAP_FLAG_TABLE} (id, bootstrap_completed, completed_at)
                    VALUES (1, 1, CURRENT_TIMESTAMP)
                """)
                conn.commit()
                logger.info("✅ Bootstrap marked as completed")
        except Exception as e:
            logger.error(f"❌ Error marking bootstrap: {e}")
    
    def is_notified(self, video_sn: int) -> bool:
        """檢查集是否已通知過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT 1 FROM {NOTIFIED_TABLE} WHERE videoSn = ?", (video_sn,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Error checking notified status: {e}")
            return False
    
    def add_notified(self, video_sn: int, anime_sn: int, anime_name: str, volume: str, cover_url: str):
        """記錄已通知的集"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR IGNORE INTO {NOTIFIED_TABLE} 
                    (videoSn, animeSn, anime_name, volume, cover_url, notified_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_sn, anime_sn, anime_name, volume, cover_url))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Error adding notified record: {e}")
    
    def bootstrap_add_all(self, episodes: List[Dict]):
        """Bootstrap：一次性添加所有當前集合到數據庫，不發送通知"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for ep in episodes:
                    video_sn = ep.get("videoSn")
                    if video_sn and not self.is_notified(video_sn):
                        cursor.execute(f"""
                            INSERT OR IGNORE INTO {NOTIFIED_TABLE}
                            (videoSn, animeSn, anime_name, volume, cover_url, notified_at)
                            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (
                            video_sn,
                            ep.get("animeSn"),
                            ep.get("title", "Unknown"),
                            ep.get("volume", ""),
                            ep.get("cover", "")
                        ))
                conn.commit()
                logger.info(f"✅ Bootstrap: added {len(episodes)} episodes to notified list")
        except Exception as e:
            logger.error(f"❌ Error during bootstrap: {e}")


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤主 Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AnimeDatabase(ANIME_DB_PATH)
        self.task_started = False
        logger.info("🎬 AnimeTracker __init__ called")
    
    async def cog_load(self):
        """Cog 加載時啟動任務"""
        if not self.task_started:
            self.task_started = True
            logger.info("🎬 AnimeTracker cog_load called - starting task")
            self.check_new_anime.start()
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        logger.info("🎬 AnimeTracker cog_unload called")
        if self.task_started and self.check_new_anime.is_running():
            self.check_new_anime.cancel()
    
    async def fetch_new_anime_from_api(self) -> Optional[List[Dict]]:
        """
        從 Bahamut API 獲取最近更新的動畫集
        
        Returns:
            集列表，或 None 如果失敗
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    API_ENDPOINT,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    }
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ API returned status {resp.status}")
                        return None
                    
                    data = await resp.json()
                    # API 返回結構：{"data": {"newAnime": {"date": [...], "popular": [...]}}}
                    new_anime = data.get("data", {}).get("newAnime", {})
                    # newAnime 是字典，我們需要 'date' 鍵中的列表
                    episodes = new_anime.get("date", []) if isinstance(new_anime, dict) else []
                    logger.info(f"🔍 API fetch: got {len(episodes)} episodes from newAnime['date']")
                    return episodes
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
            return None
    
    def generate_anime_embed(self, episode: Dict) -> discord.Embed:
        """
        生成單個集的 Discord Embed
        
        Args:
            episode: 集信息字典
        
        Returns:
            格式化的 discord.Embed
        """
        anime_name = episode.get("title", "Unknown")
        volume = episode.get("volume", "")
        cover_url = episode.get("cover", "")
        
        embed = discord.Embed(
            title=f"🎬 {anime_name} 更新了！",
            description=f"**新集：{volume}**",
            color=discord.Color.from_rgb(178, 108, 196),  # Bahamut 紫色
            timestamp=datetime.utcnow()
        )
        
        if cover_url:
            embed.set_image(url=cover_url)
        
        # 添加追蹤信息
        embed.add_field(
            name="集識別符",
            value=f"`videoSn: {episode.get('videoSn', 'N/A')}`",
            inline=False
        )
        
        # 上傳時間
        up_time = episode.get("upTime", "")
        if up_time:
            embed.add_field(name="發佈時間", value=up_time, inline=True)
        
        embed.set_footer(text="Bahamut 動畫追蹤 | 自動通知新上架集")
        return embed
    
    @tasks.loop(seconds=30)  # 測試模式：每 30 秒檢查一次（正式環境改為 hours=1）
    async def check_new_anime(self):
        """主循環：定時檢查並通知新集"""
        logger.info("🎬 check_new_anime loop iteration started")
        try:
            # 取得頻道
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if not channel:
                logger.error(f"❌ Anime channel {ANIME_CHANNEL_ID} not found")
                return
            
            # 獲取最新動畫數據
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                logger.warning("⚠️ No episodes fetched from API")
                return
            
            # 檢查 Bootstrap 狀態
            if not self.db.is_bootstrap_completed():
                # 首次運行：記錄所有現存集，不發送通知
                logger.info("🚀 First run detected - performing bootstrap...")
                self.db.bootstrap_add_all(episodes)
                self.db.mark_bootstrap_completed()
                await channel.send(
                    embed=discord.Embed(
                        title="✅ 動畫追蹤已啟動",
                        description="已記錄現有集合。之後會通知新上架的集。",
                        color=discord.Color.green()
                    )
                )
                return
            
            # 正常運行：檢查新集
            new_episodes = []
            for ep in episodes:
                video_sn = ep.get("videoSn")
                if video_sn and not self.db.is_notified(video_sn):
                    new_episodes.append(ep)
            
            if not new_episodes:
                logger.info("⏭️ No new episodes found")
                return
            
            # 發送新集通知
            logger.info(f"🆕 Found {len(new_episodes)} new episodes")
            for ep in new_episodes:
                try:
                    embed = self.generate_anime_embed(ep)
                    await channel.send(embed=embed)
                    
                    # 記錄已通知
                    self.db.add_notified(
                        video_sn=ep.get("videoSn"),
                        anime_sn=ep.get("animeSn"),
                        anime_name=ep.get("title", "Unknown"),
                        volume=ep.get("volume", ""),
                        cover_url=ep.get("cover", "")
                    )
                    
                    # 避免 Discord 限流（200ms 間隔）
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.error(f"❌ Error sending embed: {e}")
                    await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"❌ Error in check_new_anime: {e}", exc_info=True)
    
    @check_new_anime.before_loop
    async def before_check_new_anime(self):
        """在第一次循環前等待 bot 就緒"""
        logger.info("🎬 AnimeTracker before_loop started")
        await self.bot.wait_until_ready()
        logger.info("🎬 AnimeTracker bot is ready! Starting main loop...")


async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式"""
    await bot.add_cog(AnimeTracker(bot))
    logger.info("✅ AnimeTracker Cog 已加載")
