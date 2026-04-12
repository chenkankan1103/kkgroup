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

# 先設置 logger
import logging
logger = logging.getLogger(__name__)

# 模塊導入時就輸出標記，確保能追蹤加載
import sys
print("[ANIME_TRACKER_MODULE] 🎬 開始導入 anime_tracker 模塊", flush=True)
sys.stdout.flush()

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import aiohttp
import sqlite3
import json
import re
import html
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import pytz  # 用於台灣時區轉換

# 台灣時區
TW_TZ = pytz.timezone('Asia/Taipei')

# 配置
ANIME_CHANNEL_ID = 1252204317453324333  # 動畫通知頻道
ANIME_DB_PATH = Path(__file__).resolve().parent.parent / "uibot_anime.db"  # 獨立的動畫追蹤數據庫，固定到專案根目錄
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # 秒

# 表名與欄位
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"
ANIME_DETAILS_TABLE = "anime_details"  # 永恆快取動畫詳細信息
ANIME_STATS_TABLE = "anime_statistics"  # 動畫統計數據（觀看人數、評分趨勢等）
EPISODE_STATS_TABLE = "episode_statistics"  # 每集統計數據


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
                
                # 3. 永恆動畫詳細信息快取（簡介、標籤、人氣度等）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_DETAILS_TABLE} (
                        animeSn INTEGER PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT,
                        tags TEXT,
                        popular INTEGER,
                        score REAL,
                        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 4. 動畫統計數據（跨集聚合）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_STATS_TABLE} (
                        animeSn INTEGER PRIMARY KEY,
                        anime_name TEXT NOT NULL,
                        total_episodes INTEGER DEFAULT 0,
                        avg_views REAL DEFAULT 0,
                        avg_score REAL DEFAULT 0,
                        total_views INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 5. 每集統計數據（用於趨勢分析）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {EPISODE_STATS_TABLE} (
                        videoSn INTEGER PRIMARY KEY,
                        animeSn INTEGER NOT NULL,
                        episode_num TEXT,
                        views INTEGER,
                        score REAL,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
                
                # 驗證所有表都被創建
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = {row[0] for row in cursor.fetchall()}
                required_tables = {
                    NOTIFIED_TABLE, BOOTSTRAP_FLAG_TABLE, ANIME_DETAILS_TABLE,
                    ANIME_STATS_TABLE, EPISODE_STATS_TABLE
                }
                missing_tables = required_tables - existing_tables
                
                if missing_tables:
                    logger.warning(f"⚠️ 缺失的表: {missing_tables}")
                    # 嘗試再次創建缺失的表
                    for table_name in missing_tables:
                        logger.warning(f"🔧 重新創建表: {table_name}")
                        if table_name == EPISODE_STATS_TABLE:
                            cursor.execute(f"""
                                CREATE TABLE IF NOT EXISTS {table_name} (
                                    videoSn INTEGER PRIMARY KEY,
                                    animeSn INTEGER NOT NULL,
                                    episode_num TEXT,
                                    views INTEGER,
                                    score REAL,
                                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                )
                            """)
                    conn.commit()
                
                logger.info(f"✅ Anime database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to init anime DB: {e}", exc_info=True)
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
    
    def get_anime_details(self, anime_sn: int) -> Optional[Dict]:
        """從快取獲取動畫詳細信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT title, content, tags, popular, score FROM {ANIME_DETAILS_TABLE}
                    WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row:
                    return {
                        "title": row[0],
                        "content": row[1],
                        "tags": json.loads(row[2]) if row[2] else [],
                        "popular": row[3],
                        "score": row[4]
                    }
                return None
        except Exception as e:
            logger.error(f"❌ Error getting anime details: {e}")
            return None
    
    def cache_anime_details(self, anime_sn: int, title: str, content: str, tags: List[str], popular: int, score: float):
        """快取動畫詳細信息到數據庫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_DETAILS_TABLE}
                    (animeSn, title, content, tags, popular, score, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    anime_sn,
                    title,
                    content,
                    json.dumps(tags, ensure_ascii=False),
                    popular,
                    score
                ))
                conn.commit()
                logger.info(f"✅ Cached anime details for animeSn={anime_sn}")
        except Exception as e:
            logger.error(f"❌ Error caching anime details: {e}")
    
    def record_episode_stats(self, video_sn: int, anime_sn: int, episode_num: str, views: int, score: float):
        """記錄每集的統計數據"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {EPISODE_STATS_TABLE}
                    (videoSn, animeSn, episode_num, views, score, recorded_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_sn, anime_sn, episode_num, views, score))
                conn.commit()
                logger.info(f"📊 Recorded stats for videoSn={video_sn}: views={views}, score={score}")
        except Exception as e:
            logger.error(f"❌ Error recording episode stats: {e}")
    
    def get_anime_statistics(self, anime_sn: int) -> Optional[Dict]:
        """獲取某部動畫的統計數據（直接從 episode_statistics 聚合）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 直接從 episode_statistics 聚合
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_episodes,
                        AVG(views) as avg_views,
                        AVG(score) as avg_score,
                        SUM(views) as total_views
                    FROM {EPISODE_STATS_TABLE} WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row and row[1] is not None:  # 檢查是否有數據
                    return {
                        "anime_name": "",  # 從 NOTIFIED_TABLE 獲取
                        "total_episodes": row[0],
                        "avg_views": row[1],
                        "avg_score": row[2],
                        "total_views": row[3] or 0
                    }
                return None
        except Exception as e:
            logger.error(f"❌ Error getting anime stats: {e}")
            return None
    
    def update_anime_statistics(self, anime_sn: int, anime_name: str):
        """更新動畫的聚合統計數據（從 episode_statistics 表計算）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 計算本動畫的統計
                cursor.execute(f"""
                    SELECT COUNT(*), AVG(views), AVG(score), SUM(views)
                    FROM {EPISODE_STATS_TABLE} WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                total_ep, avg_views, avg_score, total_views = row
                
                # 更新或插入統計表
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_STATS_TABLE}
                    (animeSn, anime_name, total_episodes, avg_views, avg_score, total_views, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (anime_sn, anime_name, total_ep or 0, avg_views or 0, avg_score or 0, total_views or 0))
                conn.commit()
                logger.info(f"📈 Updated stats for {anime_name}: {total_ep} eps, avg_views={avg_views:.0f}, avg_score={avg_score:.1f}")
        except Exception as e:
            logger.error(f"❌ Error updating anime statistics: {e}")
    
    def get_top_anime_by_views(self, limit: int = 10) -> List[Dict]:
        """獲取觀看次數最多的動畫排行（直接從 episode_statistics 聚合）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 直接從 episode_statistics 聚合，而不是等待 anime_statistics 更新
                cursor.execute(f"""
                    SELECT 
                        animeSn,
                        COUNT(*) as total_episodes,
                        SUM(views) as total_views,
                        AVG(views) as avg_views,
                        AVG(score) as avg_score
                    FROM {EPISODE_STATS_TABLE}
                    GROUP BY animeSn
                    ORDER BY total_views DESC LIMIT ?
                """, (limit,))
                
                results = []
                for row in cursor.fetchall():
                    anime_sn = row[0]
                    # 獲取動畫名稱
                    cursor.execute(f"""
                        SELECT anime_name FROM {NOTIFIED_TABLE} 
                        WHERE animeSn = ? LIMIT 1
                    """, (anime_sn,))
                    name_row = cursor.fetchone()
                    anime_name = name_row[0] if name_row else f"Anime #{anime_sn}"
                    
                    results.append({
                        "anime_sn": anime_sn,
                        "name": anime_name,
                        "total_views": row[2] or 0,
                        "avg_views": row[3] or 0,
                        "avg_score": row[4] or 0,
                        "total_episodes": row[1] or 0
                    })
                
                return results
        except Exception as e:
            logger.error(f"❌ Error getting top anime: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error during bootstrap: {e}")


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤主 Cog"""
    
    def __init__(self, bot: commands.Bot):
        import sys
        print("[ANIME_INIT_START] 🎬 AnimeTracker.__init__ 開始執行", flush=True)
        sys.stdout.flush()
        
        logger.info("=" * 50)
        logger.info("📺 [AnimeTracker.__init__] 開始初始化")
        self.bot = bot
        try:
            self.db = AnimeDatabase(ANIME_DB_PATH)
            logger.info(f"✅ [AnimeTracker.__init__] 數據庫已初始化: {ANIME_DB_PATH}")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.__init__] 數據庫初始化失敗: {e}", exc_info=True)
            raise
        
        self.task_started = False
        self.bootstrap_completed = False
        
        # 注：任務將在 before_loop 中由 Discord.py 自動啟動，不在 __init__ 中啟動
        logger.info("📺 [AnimeTracker.__init__] 任務將在 before_loop 中由框架自動啟動")
        
        logger.info("📺 [AnimeTracker.__init__] AnimeTracker Cog 初始化完成")
        logger.info(f"📺 Bot 已就緒? {bot.is_ready()}")
        logger.info(f"📺 頻道 ID: {ANIME_CHANNEL_ID}")
        logger.info(f"📺 數據庫路徑: {ANIME_DB_PATH}")
        print("[ANIME_INIT_COMPLETE] ✅ AnimeTracker.__init__ 執行完成", flush=True)
        sys.stdout.flush()
        logger.info("=" * 50)
    
    async def cog_load(self):
        """Cog 加載時啟動任務（Discord.py 支持此選項卡）"""
        logger.info("=" * 50)
        logger.info("🎬 [AnimeTracker.cog_load] cog_load() 被調用")
        try:
            logger.info("📺 [AnimeTracker.cog_load] 準備啟動任務...")
            logger.info(f"📺 [AnimeTracker.cog_load] 任務運行狀態: {self.check_new_anime.is_running()}")
            if not self.check_new_anime.is_running():
                logger.info("📺 [AnimeTracker.cog_load] 任務未運行，現在啟動...")
                self.check_new_anime.start()
                self.task_started = True
                logger.info("✅ [AnimeTracker.cog_load] check_new_anime 任務已啟動")
            else:
                logger.warning("⚠️ [AnimeTracker.cog_load] 任務已在運行中，跳過重複啟動")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.cog_load] 任務啟動失敗: {e}", exc_info=True)
        logger.info("=" * 50)
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        if self.check_new_anime.is_running():
            self.check_new_anime.cancel()
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """
        監聽反應事件 - 當用戶給動畫通知評分時獎勵 KK幣
        支持任何表情反應（正評或負評都可以）
        """
        # 不處理 bot 自己的反應
        if user.bot:
            return
        
        # 只處理來自動畫通知頻道的反應
        if reaction.message.channel.id != ANIME_CHANNEL_ID:
            return
        
        try:
            # 檢查 embed 是否包含評分提示（即是否為動畫通知）
            embeds = reaction.message.embeds
            if not embeds:
                return
            
            embed = embeds[0]
            # 檢查是否包含評分提示字段
            is_anime_message = any(
                field.name == "⭐ 點擊反應留下評價吧" 
                for field in embed.fields
            )
            
            if not is_anime_message:
                return
            
            logger.info(f"📺 [on_reaction_add] {user.name} 給動畫通知評分（反應：{reaction.emoji}）")
            
            # 導入 db_adapter 來更新 KK幣（需要確定實現方式）
            try:
                from db_adapter import set_user_field, get_user_field
                
                # 獲取當前 KK幣
                current_kkcoin = get_user_field(user.id, "kkcoin") or 0
                new_kkcoin = int(current_kkcoin) + 2000
                
                # 更新 KK幣
                set_user_field(user.id, "kkcoin", new_kkcoin)
                
                logger.info(f"✅ [on_reaction_add] {user.name} 獲得 2000 KK幣，現在共有 {new_kkcoin} KK幣")
                
                # 在該頻道發送 ephemeral message（僅使用者能看到）
                try:
                    reward_embed = discord.Embed(
                        title="⭐ 評分獎勵",
                        description="感謝你給動畫通知評分！",
                        color=discord.Color.gold()
                    )
                    reward_embed.add_field(
                        name="獲得獎勵",
                        value="💰 +2000 KK幣",
                        inline=False
                    )
                    reward_embed.add_field(
                        name="目前餘額",
                        value=f"💵 {new_kkcoin} KK幣",
                        inline=False
                    )
                    await reaction.message.channel.send(
                        embed=reward_embed,
                        ephemeral=True,
                        silent=True,
                        reference=reaction.message
                    )
                except discord.Forbidden:
                    logger.warning(f"⚠️ [on_reaction_add] 無法在頻道發送訊息給 {user.name}")
                
            except ImportError:
                logger.warning("⚠️ [on_reaction_add] db_adapter 未找到，無法獎勵 KK幣")
            except Exception as e:
                logger.error(f"❌ [on_reaction_add] 獎勵 KK幣失敗: {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"❌ [on_reaction_add] 處理反應失敗: {e}", exc_info=True)
    
    async def fetch_all_recent_anime_from_api(self) -> Optional[List[Dict]]:
        """
        從 Bahamut API 獲取所有最近的動畫集（不限於今天的）
        用於排行榜顯示
        
        Returns:
            所有最近的集列表，或 None 如果失敗
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
                    new_anime = data.get("data", {}).get("newAnime", {})
                    
                    # 組合所有日期的動畫
                    all_episodes = []
                    if isinstance(new_anime, dict):
                        # 'date' 鍵包含按日期分組的集
                        all_episodes.extend(new_anime.get("date", []))
                        # 'popular' 鍵包含最受歡迎的集
                        all_episodes.extend(new_anime.get("popular", []))
                    
                    # 去重（按 videoSn）
                    seen = set()
                    unique_episodes = []
                    for ep in all_episodes:
                        if isinstance(ep, dict):
                            video_sn = ep.get("videoSn")
                            if video_sn and video_sn not in seen:
                                seen.add(video_sn)
                                unique_episodes.append(ep)
                    
                    logger.info(f"🔍 [fetch_all_recent_anime_from_api] 獲得 {len(unique_episodes)} 部最近的動畫")
                    return unique_episodes
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
            return None

    async def fetch_new_anime_from_api(self) -> Optional[List[Dict]]:
        """
        從 Bahamut API 獲取今天更新的動畫集
        
        注意：API 返回的列表包含多個日期的動畫，我們只需要今天的
        
        Returns:
            今天的集列表，或 None 如果失敗
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
                    all_episodes = new_anime.get("date", []) if isinstance(new_anime, dict) else []
                    
                    # 篩選只取今天的動畫
                    today = datetime.now().strftime("%m/%d")
                    today_episodes = [
                        ep for ep in all_episodes 
                        if isinstance(ep, dict) and ep.get("upTime", "").startswith(today)
                    ]
                    
                    logger.info(f"🔍 API fetch: 獲得 {len(all_episodes)} 集，其中今天的 {len(today_episodes)} 集 (upTime: {today})")
                    return today_episodes
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
            return None

    def _episode_in_current_check_window(self, episode: Dict, now: datetime) -> bool:
        """
        檢查集是否在預期時間窗口內（僅用於現在）
        
        Args:
            episode: 集信息
            now: 當前時間
            
        Returns:
            True 如果該集應該被通知
        """
        up_date = episode.get("upTime", "").strip()
        up_time = episode.get("upTimeHours", "").strip()
        if not up_date or not up_time:
            return False

        try:
            episode_dt = datetime.strptime(f"{datetime.now().year}/{up_date} {up_time}", "%Y/%m/%d %H:%M")
        except ValueError:
            return False

        # 檢查集在今天且時間匹配（允許一些容差）
        # 由於現在用 schedule 驅動檢查，這裡只做基本驗證
        return episode_dt.date() == now.date()

    async def fetch_anime_web_details(self, anime_sn: str) -> Dict[str, Optional[object]]:
        """
        從動畫瘋網頁版的 animeRef 詳情頁抓取作品分類和簡介。
        """
        if not anime_sn:
            return {}

        detail_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    detail_url,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ Web detail page returned status {resp.status} for animeSn={anime_sn}")
                        return {}
                    html_text = await resp.text()

            genres = []
            summary = None

            tag_section = re.search(r'<span class="title">作品分類</span>\s*<ul class="tag-list">(.*?)</ul>', html_text, re.S)
            if tag_section:
                genres = re.findall(r'<li class="tag">(.*?)</li>', tag_section.group(1), re.S)
                genres = [html.unescape(tag.strip()) for tag in genres if tag.strip()]

            summary_section = re.search(r'<div class="data-intro">\s*<p>(.*?)</p>', html_text, re.S)
            if summary_section:
                raw_summary = summary_section.group(1)
                summary = html.unescape(re.sub(r'\s+', ' ', raw_summary)).strip()

            return {
                "genres": genres,
                "summary": summary,
                "detail_url": detail_url,
            }
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Web detail timeout ({API_TIMEOUT}s) for animeSn={anime_sn}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error fetching anime web details for animeSn={anime_sn}: {e}", exc_info=True)
            return {}

    async def fetch_anime_details_from_api(self, video_sn: int) -> Optional[Dict]:
        """
        從 Bahamut 手機 API 獲取動畫詳細信息（簡介、標籤、人氣度等）
        
        API endpoint: https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn}
        返回 anime 部分包含：content(簡介), tags(標籤), popular(人氣度), score(評分)
        
        Returns:
            詳細信息字典或 None
        """
        if not video_sn:
            logger.info(f"📺 [fetch_anime_details_from_api] video_sn 為空，跳過")
            return None
        
        api_url = f"https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn}"
        logger.info(f"📺 [fetch_anime_details_from_api] 開始調用 API: {api_url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                    headers={
                        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)"
                    }
                ) as resp:
                    logger.info(f"📺 [fetch_anime_details_from_api] 獲得响應，status={resp.status}")
                    if resp.status != 200:
                        logger.warning(f"⚠️ API detail returned status {resp.status} for videoSn={video_sn}")
                        return None
                    
                    data = await resp.json()
                    anime = data.get("data", {}).get("anime", {})
                    logger.info(f"📺 [fetch_anime_details_from_api] anime 字典鍵: {list(anime.keys()) if anime else '(empty)'}")
                    
                    if not anime:
                        logger.warning(f"⚠️ No anime data in API response for videoSn={video_sn}")
                        return None
                    
                    anime_sn = anime.get("anime_sn")
                    title = anime.get("title", "")
                    content = anime.get("content", "")
                    tags = anime.get("tags", [])
                    popular = anime.get("popular", 0)
                    score = anime.get("score", 0)
                    
                    logger.info(f"✅ [fetch_anime_details_from_api] animeSn={anime_sn}, title={title[:30]}, tags={tags}, popular={popular}, score={score}")
                    
                    # 快取到數據庫
                    if anime_sn:
                        self.db.cache_anime_details(anime_sn, title, content, tags, popular, score)
                        # 同時記錄統計數據（用於數據分析）
                        self.db.record_episode_stats(
                            video_sn=video_sn,
                            anime_sn=anime_sn,
                            episode_num=f"Ep. {anime.get('video_episode_number', '')}",
                            views=popular,
                            score=score
                        )
                    
                    return {
                        "anime_sn": anime_sn,
                        "title": title,
                        "content": content,
                        "tags": tags,
                        "popular": popular,
                        "score": score
                    }
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API detail timeout ({API_TIMEOUT}s) for videoSn={video_sn}")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime details from API for videoSn={video_sn}: {e}", exc_info=True)
            return None

    def _truncate_text(self, text: str, limit: int = 240) -> str:
        return text if len(text) <= limit else text[:limit].rstrip() + '...'

    async def generate_anime_embed(self, episode: Dict) -> discord.Embed:
        """
        生成單個集的 Discord Embed
        
        包含動畫簡介、標籤、人氣度等信息
        優先使用快取，未快取時調用 API 並存儲到永恆快取
        
        Args:
            episode: 集信息字典（包含 videoSn, animeSn 等）
        
        Returns:
            格式化的 discord.Embed
        """
        anime_name = episode.get("title", "Unknown")
        volume = episode.get("volume", "")
        cover_url = episode.get("cover", "")
        anime_sn = episode.get("animeSn", "")
        video_sn = episode.get("videoSn", "")
        
        # 構建動畫連結
        anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}" if anime_sn else "https://ani.gamer.com.tw"
        
        # 優先檢查快取，未快取則調用 API
        anime_details = None
        if anime_sn:
            logger.info(f"📺 [generate_anime_embed] 檢查快取 animeSn={anime_sn}")
            anime_details = self.db.get_anime_details(int(anime_sn))
            if anime_details:
                logger.info(f"📺 [generate_anime_embed] ✅ 快取命中 animeSn={anime_sn}")
            else:
                logger.info(f"📺 [generate_anime_embed] ⏸ 快取未命中 animeSn={anime_sn}")
        
        if not anime_details and video_sn:
            # 快取中沒有，調用 API 獲取並快取
            logger.info(f"📺 [generate_anime_embed] 準備調用 API videoSn={video_sn}")
            anime_details = await self.fetch_anime_details_from_api(int(video_sn))
            if anime_details:
                logger.info(f"📺 [generate_anime_embed] ✅ API 成功回傳數據")
            else:
                logger.info(f"📺 [generate_anime_embed] ❌ API 未返回數據")
        
        # 提取詳細信息
        content = anime_details.get("content", "") if anime_details else ""
        api_tags = anime_details.get("tags", []) if anime_details else []
        popular = anime_details.get("popular", 0) if anime_details else 0
        score = anime_details.get("score", 0) if anime_details else 0
        
        logger.info(f"📺 [generate_anime_embed] 提取的詳細信息: content_len={len(content)}, tags={api_tags}, popular={popular}, score={score}")
        
        # 構建標籤信息
        tag_parts = []
        
        # 優先使用 API 返回的標籤
        if api_tags:
            tag_parts.extend([f"#{tag}" for tag in api_tags[:6]])
        else:
            # 如果沒有 API 標籤，嘗試從網頁抓取（舊方式）
            web_details = await self.fetch_anime_web_details(str(anime_sn)) if anime_sn else {}
            genres = web_details.get("genres", [])
            if genres:
                tag_parts.extend([f"#{tag}" for tag in genres[:6]])
        
        # 添加亮點標籤（雙語、版本等）
        highlight_tag = episode.get("highlightTag", {})
        if not api_tags and highlight_tag.get("bilingual"):
            tag_parts.append("🗣️ 雙語")

        edition = highlight_tag.get("edition", "").strip()
        if edition:
            tag_parts.append(f"📺 {edition}")
        
        tags_str = " | ".join(tag_parts) if tag_parts else "無特殊標籤"
        
        # 構建描述，優先使用 API 返回的簡介
        if not content:
            web_details = await self.fetch_anime_web_details(str(anime_sn)) if anime_sn else {}
            content = web_details.get("summary", "")
        
        description_text = f"**集數：{volume}**"
        # 不再在 description 中添加簡介，改為只在 field 中顯示短版簡介
        
        # 人氣度和評分信息 - 增強展示
        popularity_text = f"👥 {popular:,}" if popular > 0 else "👥 N/A"
        score_text = f"⭐ {score:.1f}" if score > 0 else "⭐ N/A"
        
        # 嘗試獲取動畫統計信息（用於顯示平均數據）
        anime_stats = self.db.get_anime_statistics(int(anime_sn)) if anime_sn else None
        
        embed = discord.Embed(
            title=f"🎬 {anime_name}",
            description=description_text,
            url=anime_url,
            color=discord.Color.from_rgb(178, 108, 196),
            timestamp=datetime.utcnow()
        )
        
        if cover_url:
            embed.set_image(url=cover_url)
        
        # 添加詳細的人氣度與評分字段
        stats_lines = [
            f"**本集**: {popularity_text} 觀看 | {score_text} 評分"
        ]
        if anime_stats and anime_stats['total_episodes'] > 0:
            avg_views = anime_stats['avg_views']
            avg_score = anime_stats['avg_score']
            stats_lines.append(f"**本季均值**: 👥 {avg_views:,.0f} 觀看 | ⭐ {avg_score:.1f} 評分")
            stats_lines.append(f"**本季統計**: {anime_stats['total_episodes']} 集, 共 {anime_stats['total_views']:,} 觀看")
        
        embed.add_field(
            name="📊 觀看數據",
            value="\n".join(stats_lines),
            inline=False
        )
        
        embed.add_field(
            name="📌 標籤",
            value=tags_str,
            inline=False
        )
        
        if content:
            embed.add_field(
                name="📝 劇情簡介",
                value=self._truncate_text(content, 140),
                inline=False
            )
        
        embed.add_field(
            name="⭐ 點擊反應留下評價吧",
            value="不管點什麼表情都沒關係啦，正評負評都可以～\n評分成功會獲得 💰 2000 KK幣喔！",
            inline=False
        )
        
        embed.set_footer(text="動畫瘋新番通知")
        return embed
    
    async def generate_anime_view(self, episode: Dict) -> Optional[discord.ui.View]:
        """生成 Discord 按鈕視圖，包括動畫頁與本集連結。"""
        anime_sn = episode.get("animeSn")
        video_sn = episode.get("videoSn")
        view = discord.ui.View()
        
        if anime_sn:
            anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
            view.add_item(discord.ui.Button(label="前往動畫瘋新番頁", url=anime_url))
        
        if video_sn:
            video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}"
            view.add_item(discord.ui.Button(label="查看本集", url=video_url))
        
        return view if view.children else None
    
    @tasks.loop(minutes=1)
    async def check_new_anime(self):
        """
        根據日程表檢查新番，優化為只在預期時間附近檢查
        
        工作流程：
        1. 獲取 newAnimeSchedule（各星期的預期時刻表）
        2. 計算預期時刻（±10分鐘的窗口）
        3. 只有在預期時間窗口內且有集更新時，才發送通知
        4. 減少離峰時間每分鐘的檢查成本
        """
        # 使用台灣時區而不是 GCP VM 的美國時間
        now = datetime.now(TW_TZ)
        
        try:
            # 獲取日程表
            schedule = await self._get_anime_schedule()
            if not schedule:
                # 日程表為空，跳過
                return
            
            # 獲取當前時刻應該檢查的集合
            expected_check_times = self._get_expected_check_times(schedule, now)
            if not expected_check_times:
                # 沒有預期時刻，跳過
                return
            
            # 檢查當前時刻是否在預定時刻之後約 1 分鐘內
            current_time = now.time()
            in_check_window = False
            for check_time_str in expected_check_times:
                try:
                    check_time = datetime.strptime(check_time_str, "%H:%M").time()
                    scheduled_datetime = datetime.combine(now.date(), check_time)
                    current_datetime = datetime.combine(now.date(), current_time)
                    time_diff = (current_datetime - scheduled_datetime).total_seconds() / 60
                    if 0 <= time_diff <= 1.5:  # 預定時刻後 1 分鐘內
                        in_check_window = True
                        logger.info(f"📺 [check_new_anime] 在預定時刻 {check_time_str} 後的檢查窗口內，開始檢查新集")
                        break
                except:
                    continue
            
            if not in_check_window:
                # 尚未到預定時刻或已過 1 分鐘後，跳過
                return
            
            logger.info(f"📺 [check_new_anime] ========== 預期時刻附近檢查 ({now.strftime('%H:%M')}) ==========")
            
            # 取得頻道
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if not channel:
                logger.error(f"❌ [check_new_anime] 動畫頻道 {ANIME_CHANNEL_ID} 未找到")
                return
            
            # 獲取最新動畫數據
            logger.info("📺 [check_new_anime] 正在從 API 獲取動畫數據...")
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                logger.warning("⚠️ [check_new_anime] 無法從 API 獲取數據或沒有今日最新集")
                return
            
            logger.info(f"📺 [check_new_anime] 獲得 {len(episodes)} 集")
            
            # 檢查 Bootstrap 狀態
            bootstrap_status = self.db.is_bootstrap_completed()
            logger.info(f"📺 [check_new_anime] Bootstrap 狀態: {bootstrap_status}")
            
            if not bootstrap_status:
                # 首次運行：記錄所有現存集，不發送通知
                logger.info("🚀 [check_new_anime] 首次運行，執行 bootstrap...")
                self.db.bootstrap_add_all(episodes)
                self.db.mark_bootstrap_completed()
                self.bootstrap_completed = True
                
                embed = discord.Embed(
                    title="✅ 動畫追蹤已啟動",
                    description="已記錄現有集合。之後會通知新上架的集。",
                    color=discord.Color.green()
                )
                logger.info("📺 [check_new_anime] 發送 bootstrap 確認 embed")
                await channel.send(embed=embed, silent=True)
                logger.info("✅ [check_new_anime] Bootstrap 完成，embed 已發送")
                return
            
            # 正常運行：檢查新集
            new_episodes = []
            for ep in episodes:
                video_sn = ep.get("videoSn")
                if not video_sn or self.db.is_notified(video_sn):
                    continue
                # 簡化邏輯：只要不在 notified 表中就認為是新集
                new_episodes.append(ep)
            
            if not new_episodes:
                logger.info("⏭️ 沒有新集")
                return
            
            # 發送新集通知
            logger.info(f"🆕 發現 {len(new_episodes)} 個新集")
            for ep in new_episodes:
                try:
                    embed = await self.generate_anime_embed(ep)
                    view = await self.generate_anime_view(ep)
                    message = await channel.send(embed=embed, view=view, silent=True)

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
    
    async def _get_anime_schedule(self) -> dict:
        """從 API 獲取日程表 (newAnimeSchedule)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as response:
                    if response.status != 200:
                        logger.error(f"❌ API returned status {response.status}")
                        return {}
                    
                    data = await response.json()
                    schedule = data.get("data", {}).get("newAnimeSchedule", {})
                    return schedule
        except Exception as e:
            logger.error(f"❌ Error fetching schedule: {e}")
            return {}
    
    def _get_expected_check_times(self, schedule: dict, now: datetime) -> list:
        """
        計算出今天和明天的所有預期檢查時刻
        （用於檢查當前時間是否在預定時刻後約 1 分鐘內）
        
        Returns:
            預期檢查時刻列表，格式為 ["HH:MM", ...]
        """
        check_times = set()
        
        # 計算今天和明天的星期（1-7）
        weekday_today = (now.weekday() + 1) % 7
        if weekday_today == 0:
            weekday_today = 7  # Sunday is 7
        weekday_tomorrow = (weekday_today % 7) + 1
        
        # 從日程表中獲取時刻
        for weekday in [str(weekday_today), str(weekday_tomorrow)]:
            for anime_info in schedule.get(weekday, []):
                schedule_time = anime_info.get("scheduleTime", "")  # 格式: "22:00"
                if schedule_time:
                    try:
                        # 直接使用原始時刻（不再加 +1 分鐘）
                        check_times.add(schedule_time)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to parse schedule time '{schedule_time}': {e}")
        
        logger.debug(f"📺 預期更新時刻: {sorted(check_times)}")
        return sorted(list(check_times))
    
    @check_new_anime.before_loop
    async def before_check_new_anime(self):
        """在第一次循環前等待 bot 就緒並啟動任務"""
        logger.info("📺 [before_check_new_anime] 等待 bot 就緒...")
        print("[ANIME_BEFORE_LOOP] ⏳ before_loop 開始執行", flush=True)
        
        await self.bot.wait_until_ready()
        
        logger.info(f"✅ [before_check_new_anime] Bot 已就緒！")
        print("[ANIME_BEFORE_LOOP] ✅ Bot 就緒，開始檢查頻道", flush=True)
        logger.info(f"📺 [before_check_new_anime] Bot guilds 數量: {len(self.bot.guilds)}")
        logger.info(f"📺 [before_check_new_anime] 尋找目標頻道 {ANIME_CHANNEL_ID}...")
        
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if channel:
            logger.info(f"✅ [before_check_new_anime] 找到頻道: {channel.name} (Guild: {channel.guild.name})")
            print(f"[ANIME_BEFORE_LOOP] ✅ 找到頻道: {channel.name}", flush=True)
        else:
            logger.error(f"❌ [before_check_new_anime] 未找到頻道 {ANIME_CHANNEL_ID}")
            print(f"[ANIME_BEFORE_LOOP] ❌ 未找到頻道 {ANIME_CHANNEL_ID}", flush=True)
            # 列出所有頻道以供診斷
            for guild in self.bot.guilds:
                logger.info(f"📋 Guild: {guild.name}")
                for ch in guild.channels[:5]:  # 只列前 5 個
                    logger.info(f"   - {ch.name} (ID: {ch.id})")
        
        # 重要：確保任務已啟動
        if not self.check_new_anime.is_running():
            logger.info("🚀 [before_check_new_anime] 啟動 check_new_anime 任務...")
            print("[ANIME_BEFORE_LOOP] 🚀 即將啟動任務", flush=True)
            try:
                self.check_new_anime.start()
                self.task_started = True
                logger.info("✅ [before_check_new_anime] 任務已啟動！")
                print("[ANIME_BEFORE_LOOP] ✅ 任務已啟動", flush=True)
            except Exception as e:
                logger.error(f"❌ [before_check_new_anime] 啟動任務失敗: {e}", exc_info=True)
                print(f"[ANIME_BEFORE_LOOP_ERROR] ❌ {str(e)}", flush=True)
        else:
            logger.info("⚠️ [before_check_new_anime] 任務已在運行")

    @app_commands.command(name="anime_test", description="測試動畫通知 - 顯示最近的動畫集")
    async def anime_test(self, interaction: discord.Interaction):
        """測試指令：獲取最近的動畫數據並在當前頻道發送"""
        try:
            await interaction.response.defer()  # 延遲回應，因為可能需要時間
            
            logger.info(f"📺 [anime_test] 被 {interaction.user} 在頻道 {interaction.channel} 調用")
            
            # 獲取最新動畫數據
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                await interaction.followup.send("❌ 無法從 API 獲取動畫數據")
                logger.warning("📺 [anime_test] API 返回空結果")
                return
            
            logger.info(f"📺 [anime_test] 獲得 {len(episodes)} 集")
            
            # 生成並發送前 3 集的 embed
            sent_count = 0
            for ep in episodes[:3]:
                try:
                    embed = await self.generate_anime_embed(ep)
                    view = await self.generate_anime_view(ep)
                    message = await interaction.followup.send(embed=embed, view=view, silent=True)
                    
                    sent_count += 1
                    await asyncio.sleep(0.2)  # 避免限流
                except Exception as e:
                    logger.error(f"❌ [anime_test] 發送 embed 失敗: {e}")
            
            logger.info(f"✅ [anime_test] 成功發送 {sent_count} 個 embed")
            
        except Exception as e:
            logger.error(f"❌ [anime_test] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    
    @app_commands.command(name="anime_start", description="手動啟動自動推送任務")
    async def anime_start(self, interaction: discord.Interaction):
        """手動啟動 check_new_anime 任務"""
        try:
            await interaction.response.defer()
            
            task_running = self.check_new_anime.is_running()
            logger.info(f"📺 [anime_start] 當前任務狀態: {'運行中' if task_running else '未運行'}")
            
            if task_running:
                await interaction.followup.send("✅ 任務已在運行中")
            else:
                logger.info("📺 [anime_start] 嘗試啟動任務...")
                try:
                    self.check_new_anime.start()
                    self.task_started = True
                    await interaction.followup.send("✅ 任務已啟動！自動推送已開始")
                    logger.info("✅ [anime_start] 任務成功啟動")
                except Exception as e:
                    await interaction.followup.send(f"❌ 啟動失敗: {str(e)}")
                    logger.error(f"❌ [anime_start] 任務啟動失敗: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ [anime_start] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    
    @app_commands.command(name="anime_status", description="查看自動推送任務狀態")
    async def anime_status(self, interaction: discord.Interaction):
        """查看 check_new_anime 任務的狀態"""
        try:
            await interaction.response.defer()
            
            task_running = self.check_new_anime.is_running()
            bootstrap_done = self.db.is_bootstrap_completed()
            
            status_text = f"""
📊 **動畫推送系統狀態**

🔄 **循環任務**: {'✅ 運行中' if task_running else '❌ 未運行'}
🚀 **Bootstrap**: {'✅ 已完成' if bootstrap_done else '⏳ 未完成'}
💾 **數據庫**: {ANIME_DB_PATH}
📺 **目標頻道**: {ANIME_CHANNEL_ID}

若任務未運行，請使用 `/anime_start` 手動啟動
"""
            
            await interaction.followup.send(status_text)
            logger.info(f"📺 [anime_status] 任務狀態: {'運行中' if task_running else '未運行'}, Bootstrap: {'完成' if bootstrap_done else '未完成'}")
        except Exception as e:
            logger.error(f"❌ [anime_status] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    
    @app_commands.command(name="anime_ranking", description="查看本季動畫觀看排行榜")
    async def anime_ranking(self, interaction: discord.Interaction):
        """顯示本季動畫的觀看排行榜（實時從 API 獲取或從歷史數據統計）"""
        try:
            await interaction.response.defer()
            
            # 確保 episode_statistics 表存在（修復初始化問題）
            try:
                with sqlite3.connect(self.db.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS episode_statistics (
                            videoSn INTEGER PRIMARY KEY,
                            animeSn INTEGER NOT NULL,
                            episode_num TEXT,
                            views INTEGER,
                            score REAL,
                            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    logger.info("✅ [anime_ranking] 確保 episode_statistics 表存在")
            except Exception as e:
                logger.warning(f"⚠️ [anime_ranking] 表初始化失敗: {e}")
            
            # 先嘗試從数據庫取歷史統計數據
            top_anime = self.db.get_top_anime_by_views(limit=10)
            
            # 如果沒有歷史數據，則實時從 API 獲取最近的動畫
            if not top_anime:
                logger.info("📺 [anime_ranking] 數據庫無歷史數據，改為實時從 API 獲取")
                episodes = await self.fetch_all_recent_anime_from_api()
                
                if not episodes:
                    await interaction.followup.send("❌ 無法獲取動畫數據，請稍後再試")
                    logger.warning("📺 [anime_ranking] API 無數據")
                    return
                
                # 按觀看人數排序
                anime_list = {}
                for ep in episodes:
                    anime_sn = ep.get("animeSn")
                    if not anime_sn:
                        continue
                    
                    anime_name = ep.get("title", f"Anime #{anime_sn}")
                    views = 0
                    
                    # 為了獲取詳細的观看人数和正確的動畫名稱，调用 API
                    try:
                        video_sn = ep.get("videoSn")
                        if video_sn:
                            details = await self.fetch_anime_details_from_api(video_sn)
                            if details:
                                views = details.get("popular", 0)
                                # 使用 API 返回的正確動畫名稱
                                if details.get("title"):
                                    anime_name = details.get("title")
                    except Exception as e:
                        logger.warning(f"⚠️ 無法取得 videoSn={video_sn} 的詳細信息: {e}")
                    
                    # 聚合多集的数据
                    if anime_sn not in anime_list:
                        anime_list[anime_sn] = {
                            "name": anime_name,
                            "episodes": [],
                            "total_views": 0,
                            "total_episodes": 0,
                        }
                    
                    if views > 0:
                        anime_list[anime_sn]["episodes"].append(views)
                        anime_list[anime_sn]["total_views"] += views
                        anime_list[anime_sn]["total_episodes"] += 1
                
                # 轉換為排行格式並按總觀看數排序
                top_anime = []
                for anime_sn, data in anime_list.items():
                    if data["total_episodes"] > 0:
                        top_anime.append({
                            "anime_sn": anime_sn,
                            "name": data["name"],
                            "total_views": data["total_views"],
                            "total_episodes": data["total_episodes"]
                        })
                
                # 按總觀看數排序
                top_anime.sort(key=lambda x: x["total_views"], reverse=True)
                top_anime = top_anime[:10]
                
                if not top_anime:
                    await interaction.followup.send("📊 目前還沒有動畫數據，請稍後再試")
                    logger.info("📺 [anime_ranking] 無有效的動畫數據")
                    return
                
                logger.info(f"📺 [anime_ranking] 實時獲取了 {len(top_anime)} 部動畫的數據")
            
            # 生成排行榜 embed（條形圖顯示觀看數）
            embed = discord.Embed(
                title="🏆 本季動畫觀看排行榜",
                description=f"前 {len(top_anime)} 名熱度排行",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            # 找到最高觀看數用於條形圖縮放
            max_views = max(anime['total_views'] for anime in top_anime) if top_anime else 1
            bar_length = 20  # 條形圖長度
            
            ranking_text = []
            for idx, anime in enumerate(top_anime, 1):
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx:2d}"
                
                # 計算條形圖
                filled = int((anime['total_views'] / max_views) * bar_length)
                bar = "▰" * filled + "▱" * (bar_length - filled)
                
                # 組合排行資訊
                line = (
                    f"{medal} **{anime['name']}**\n"
                    f"{bar} {anime['total_views']:,} 次 | 📺 {anime['total_episodes']} 集"
                )
                ranking_text.append(line)
            
            # 將所有排行資訊作為 description 添加
            embed.description += "\n\n" + "\n\n".join(ranking_text)
            
            embed.set_footer(text="🔄 實時數據" if not self.db.get_top_anime_by_views(limit=1) else "📊 歷史統計")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"📺 [anime_ranking] 顯示前 {len(top_anime)} 部動畫的排行")
        except Exception as e:
            logger.error(f"❌ [anime_ranking] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    
    @app_commands.command(name="anime_stats", description="查看特定動畫的統計數據分析")
    async def anime_stats(self, interaction: discord.Interaction, anime_name: str):
        """查看某部動畫的詳細統計數據"""
        try:
            await interaction.response.defer()
            
            # 簡單的搜索：從數據庫中查找名稱相符的動畫
            # 這需要先更新系統，但我們可以返回提示
            await interaction.followup.send(
                "📊 **動畫統計分析功能**\n\n"
                "此功能用於查看特定動畫的詳細數據分析。\n\n"
                "目前支持的數據指標：\n"
                "• 👥 本季總觀看人數\n"
                "• ⭐ 平均評分趨勢\n"
                "• 📈 集數 vs 觀看人數趨勢\n"
                "• 🔢 排名變化\n\n"
                f"查詢動畫: **{anime_name}**\n"
                "更多統計功能開發中... 請使用 `/anime_ranking` 查看排行榜"
            )
            logger.info(f"📺 [anime_stats] 查詢動畫: {anime_name}")
        except Exception as e:
            logger.error(f"❌ [anime_stats] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    

async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式"""
    await bot.add_cog(AnimeTracker(bot))
    logger.info("✅ AnimeTracker Cog 已加載")
