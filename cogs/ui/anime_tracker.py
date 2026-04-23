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
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import pytz  # 用於台灣時區轉換
from urllib.parse import quote  # 用於生成 QuickChart URL
from shared.utils.view_registry import PersistentViewBase

# 台灣時區
TW_TZ = pytz.timezone('Asia/Taipei')

# 配置
ANIME_CHANNEL_ID = 1252204317453324333  # 動畫通知頻道
ANIME_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"  # 統一使用主數據庫，所有表在同一個 user_data.db 中
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # 秒

# 表名與欄位
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"
ANIME_DETAILS_TABLE = "anime_details"  # 永恆快取動畫詳細信息
ANIME_STATS_TABLE = "anime_statistics"  # 動畫統計數據（觀看人數、評分趨勢等）
EPISODE_STATS_TABLE = "episode_statistics"  # 每集統計數據
ANIME_MESSAGES_TABLE = "anime_messages"  # 消息 ID 追蹤（用於 bot 重啟時恢復 view）
ANIME_VOTES_TABLE = "anime_votes"  # 匿名投票結果
ANIME_REWARDS_TABLE = "anime_rewards"  # KK幣獎勵追踪（防止重複發放）


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
                
                # 5.5. 消息 ID 追蹤表（用於 bot 重啟時恢復 view）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_MESSAGES_TABLE} (
                        message_id INTEGER PRIMARY KEY,
                        videoSn INTEGER NOT NULL,
                        animeSn INTEGER NOT NULL,
                        anime_name TEXT NOT NULL,
                        channel_id INTEGER NOT NULL,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 6. 匿名投票結果表
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_VOTES_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        videoSn INTEGER NOT NULL,
                        animeSn INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        vote_type TEXT NOT NULL,
                        comment TEXT,
                        user_hash TEXT,
                        voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 7. KK幣獎勵追踪表
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_REWARDS_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        reward_type TEXT NOT NULL,
                        reward_amount INTEGER NOT NULL,
                        awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, message_id, reward_type)
                    )
                """)
                
                conn.commit()
                
                # 驗證所有表都被創建
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = {row[0] for row in cursor.fetchall()}
                required_tables = {
                    NOTIFIED_TABLE, BOOTSTRAP_FLAG_TABLE, ANIME_DETAILS_TABLE,
                    ANIME_STATS_TABLE, EPISODE_STATS_TABLE, ANIME_MESSAGES_TABLE
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
                
                # 確保表存在（防止表未創建的情況）
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
                
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {EPISODE_STATS_TABLE}
                    (videoSn, animeSn, episode_num, views, score, recorded_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_sn, anime_sn, episode_num, views, score))
                conn.commit()
                logger.info(f"📊 [record_episode_stats] videoSn={video_sn}, episode={episode_num}, views={views}")
        except Exception as e:
            logger.error(f"❌ Error recording episode stats: {e}", exc_info=True)
    
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
                    # 先從 anime_details 查詢名稱（最新數據），再從 anime_notified 查詢
                    anime_name = None
                    
                    cursor.execute(f"""
                        SELECT title FROM {ANIME_DETAILS_TABLE} 
                        WHERE animeSn = ? ORDER BY cached_at DESC LIMIT 1
                    """, (anime_sn,))
                    detail_row = cursor.fetchone()
                    if detail_row:
                        anime_name = detail_row[0]
                    
                    # 如果 anime_details 沒有，再從 anime_notified 查詢
                    if not anime_name:
                        cursor.execute(f"""
                            SELECT anime_name FROM {NOTIFIED_TABLE} 
                            WHERE animeSn = ? LIMIT 1
                        """, (anime_sn,))
                        notified_row = cursor.fetchone()
                        anime_name = notified_row[0] if notified_row else None
                    
                    # 最後還是沒有就用預設名稱
                    if not anime_name:
                        anime_name = f"Anime #{anime_sn}"
                    
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
    
    def get_multi_episode_anime_for_chart(self, limit: int = 10, min_episodes: int = 2) -> List[Dict]:
        """獲取有多集數據的動畫（用於多線坐標圖），按總觀看次數排序
        
        Returns:
            [{
                "anime_sn": int,
                "name": str,
                "cover_url": str,  # 新增：動畫封面 URL
                "short_name": str,  # 新增：動畫簡稱（前 2 個字符）
                "episodes": [{"num": str, "views": int}, ...],
                "total_views": int,
                "total_episodes": int
            }, ...]
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 確保表存在
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
                
                # 先獲取所有有多於 min_episodes 的動畫
                cursor.execute(f"""
                    SELECT 
                        animeSn,
                        COUNT(*) as total_episodes,
                        SUM(views) as total_views
                    FROM {EPISODE_STATS_TABLE}
                    GROUP BY animeSn
                    HAVING COUNT(*) >= ?
                    ORDER BY total_views DESC LIMIT ?
                """, (min_episodes, limit))
                
                results = []
                for row in cursor.fetchall():
                    anime_sn = row[0]
                    total_episodes = row[1]
                    total_views = row[2] or 0
                    
                    # 獲取動畫名稱和封面 URL
                    anime_name = None
                    cover_url = None
                    
                    cursor.execute(f"""
                        SELECT title FROM {ANIME_DETAILS_TABLE} 
                        WHERE animeSn = ? ORDER BY cached_at DESC LIMIT 1
                    """, (anime_sn,))
                    detail_row = cursor.fetchone()
                    if detail_row:
                        anime_name = detail_row[0]
                    
                    if not anime_name:
                        cursor.execute(f"""
                            SELECT anime_name, cover_url FROM {NOTIFIED_TABLE} 
                            WHERE animeSn = ? LIMIT 1
                        """, (anime_sn,))
                        notified_row = cursor.fetchone()
                        if notified_row:
                            anime_name = notified_row[0]
                            cover_url = notified_row[1] if len(notified_row) > 1 else None
                        else:
                            anime_name = f"Anime #{anime_sn}"
                    
                    # 如果還沒有 cover_url，嘗試從 NOTIFIED_TABLE 獲取
                    if not cover_url:
                        cursor.execute(f"""
                            SELECT cover_url FROM {NOTIFIED_TABLE} 
                            WHERE animeSn = ? ORDER BY notified_at DESC LIMIT 1
                        """, (anime_sn,))
                        cover_row = cursor.fetchone()
                        if cover_row and cover_row[0]:
                            cover_url = cover_row[0]
                    
                    # 生成動畫簡稱（前 2 個字符）
                    short_name = anime_name[:2] if len(anime_name) >= 2 else anime_name
                    
                    # 獲取該動畫的所有集集數據（按集數排序）
                    cursor.execute(f"""
                        SELECT episode_num, views FROM {EPISODE_STATS_TABLE}
                        WHERE animeSn = ?
                        ORDER BY episode_num ASC
                    """, (anime_sn,))
                    
                    episodes = []
                    for ep_row in cursor.fetchall():
                        ep_num = ep_row[0] or "?"
                        views = ep_row[1] or 0
                        episodes.append({"num": ep_num, "views": views})
                    
                    results.append({
                        "anime_sn": anime_sn,
                        "name": anime_name,
                        "cover_url": cover_url,
                        "short_name": short_name,
                        "episodes": episodes,
                        "total_views": total_views,
                        "total_episodes": total_episodes
                    })
                
                logger.info(f"📊 [get_multi_episode_anime_for_chart] 找到 {len(results)} 部有多集數據的動畫")
                return results
        except Exception as e:
            logger.error(f"❌ Error getting multi-episode anime for chart: {e}", exc_info=True)
            return []
    
    def record_vote(self, video_sn: int, anime_sn: int, message_id: int, vote_type: str, comment: str = None, user_hash: str = None):
        """記錄匿名投票"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT INTO {ANIME_VOTES_TABLE}
                    (videoSn, animeSn, message_id, vote_type, comment, user_hash, voted_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_sn, anime_sn, message_id, vote_type, comment, user_hash))
                conn.commit()
                logger.info(f"📊 [record_vote] 記錄投票: videoSn={video_sn}, vote_type={vote_type}")
        except Exception as e:
            logger.error(f"❌ Error recording vote: {e}", exc_info=True)
    
    def get_vote_stats(self, message_id: int) -> Dict:
        """獲取某條消息的投票統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT vote_type, COUNT(*) as count FROM {ANIME_VOTES_TABLE}
                    WHERE message_id = ?
                    GROUP BY vote_type
                    ORDER BY count DESC
                """, (message_id,))
                
                stats = {}
                for row in cursor.fetchall():
                    stats[row[0]] = row[1]
                
                return stats
        except Exception as e:
            logger.error(f"❌ Error getting vote stats: {e}")
            return {}
    
    def get_vote_comments(self, message_id: int, limit: int = 5) -> List[str]:
        """獲取某條消息的匿名評論"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT comment FROM {ANIME_VOTES_TABLE}
                    WHERE message_id = ? AND comment IS NOT NULL
                    ORDER BY voted_at DESC
                    LIMIT ?
                """, (message_id, limit))
                
                comments = [row[0] for row in cursor.fetchall() if row[0]]
                return comments
        except Exception as e:
            logger.error(f"❌ Error getting vote comments: {e}")
            return []
    
    def get_weekly_vote_stats(self) -> Dict[int, Dict]:
        """獲取本週的投票統計（按動畫分組）
        
        Returns:
            {
                animeSn: {
                    'anime_name': 'xxx',
                    'total_votes': 10,
                    'votes': {'masterpiece': 3, 'great': 2, ...},
                    'episodes': set([videoSn1, videoSn2, ...])
                },
                ...
            }
        """
        try:
            from datetime import datetime, timedelta
            
            # 計算本週一零時（台灣時區）
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())  # 週一
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 獲取本週的投票
                cursor.execute(f"""
                    SELECT animeSn, videoSn, vote_type, COUNT(*) as count
                    FROM {ANIME_VOTES_TABLE}
                    WHERE voted_at >= ?
                    GROUP BY animeSn, videoSn, vote_type
                    ORDER BY animeSn, count DESC
                """, (week_start.isoformat(),))
                
                # 組織數據
                stats = {}
                for anime_sn, video_sn, vote_type, count in cursor.fetchall():
                    if anime_sn not in stats:
                        stats[anime_sn] = {
                            'votes': {},
                            'episodes': set(),
                            'total_votes': 0
                        }
                    
                    stats[anime_sn]['votes'][vote_type] = stats[anime_sn]['votes'].get(vote_type, 0) + count
                    stats[anime_sn]['episodes'].add(video_sn)
                    stats[anime_sn]['total_votes'] += count
                
                # 補充動畫名稱
                for anime_sn in stats:
                    anime_details = self.get_anime_details(anime_sn)
                    if anime_details:
                        stats[anime_sn]['anime_name'] = anime_details.get('title', f'動畫 {anime_sn}')
                    else:
                        stats[anime_sn]['anime_name'] = f'動畫 {anime_sn}'
                
                return stats
        except Exception as e:
            logger.error(f"❌ Error getting weekly vote stats: {e}", exc_info=True)
            return {}
    
    def record_reward(self, user_id: int, message_id: int, reward_type: str, reward_amount: int) -> bool:
        """記錄 KK幣獎勵 - 防止重複發放"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT INTO {ANIME_REWARDS_TABLE}
                    (user_id, message_id, reward_type, reward_amount, awarded_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, message_id, reward_type, reward_amount))
                conn.commit()
                logger.info(f"💰 [record_reward] user_id={user_id}, message_id={message_id}, type={reward_type}, amount={reward_amount}")
                return True
        except sqlite3.IntegrityError:
            # 該用戶在該消息上已獲得過此類型的獎勵
            logger.info(f"⏭️ [record_reward] user_id={user_id} 已獲得過 {reward_type} 獎勵")
            return False
        except Exception as e:
            logger.error(f"❌ Error recording reward: {e}")
            return False
    
    def is_reward_already_given(self, user_id: int, message_id: int, reward_type: str) -> bool:
        """檢查是否已發放過獎勵"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_REWARDS_TABLE}
                    WHERE user_id = ? AND message_id = ? AND reward_type = ?
                """, (user_id, message_id, reward_type))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Error checking reward: {e}")
            return False
    
    def save_message_info(self, message_id: int, video_sn: int, anime_sn: int, anime_name: str, channel_id: int) -> bool:
        """保存消息 ID 以用於 bot 重啟時恢復 view"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_MESSAGES_TABLE}
                    (message_id, videoSn, animeSn, anime_name, channel_id, sent_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (message_id, video_sn, anime_sn, anime_name, channel_id))
                conn.commit()
                logger.info(f"💾 [save_message_info] message_id={message_id}, video_sn={video_sn}, anime_name={anime_name}")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving message info: {e}")
            return False
    
    def get_all_message_infos(self) -> List[Dict]:
        """獲取所有已保存的消息 ID，用於 bot 重啟時恢復"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT message_id, videoSn, animeSn, anime_name, channel_id 
                    FROM {ANIME_MESSAGES_TABLE}
                    ORDER BY sent_at DESC
                """)
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "message_id": row[0],
                        "video_sn": row[1],
                        "anime_sn": row[2],
                        "anime_name": row[3],
                        "channel_id": row[4]
                    })
                return results
        except Exception as e:
            logger.error(f"❌ Error getting message infos: {e}")
            return []


# ==================== 匿名投票 View 類 ====================

class AnimeVoteView(discord.ui.View):
    """動畫投票視圖 - 6 個投票按鈕 + 評論按鈕 (永久視圖)"""
    
    # 投票類型配置
    VOTE_TYPES = {
        "masterpiece": ("神作", "🟩"),     # 綠
        "great": ("佳作", "🟦"),          # 藍
        "darkhorse": ("黑馬", "🟪"),      # 紫
        "decent": ("普作/小品", "🟨"),    # 黃
        "controversial": ("爭議作", "🟧"), # 橙
        "disaster": ("雷作/糞作", "🟥"),   # 紅
    }
    
    def __init__(self, episode: Dict, anime_tracker: "AnimeTracker"):
        # 永久視圖設置：timeout=None 表示永不超時，persistent=True 表示重啟後依然有效
        super().__init__(timeout=None)
        self.episode = episode
        self.tracker = anime_tracker
        self.video_sn = episode.get("videoSn")
        self.anime_sn = episode.get("animeSn")
        self.message_id = None
        self.last_interaction_time = None  # 用於追蹤最後互動時間
        
        logger.info(f"📌 [AnimeVoteView.__init__] 開始創建視圖，video_sn={self.video_sn}")
        
        # 添加投票按鈕
        button_count = 0
        for vote_key, (vote_label, color_emoji) in self.VOTE_TYPES.items():
            # 根據投票類型選擇按鈕樣式
            button_style = discord.ButtonStyle.secondary  # 預設灰色
            if vote_key == "masterpiece":
                button_style = discord.ButtonStyle.success  # 綠色
            elif vote_key == "decent":
                button_style = discord.ButtonStyle.primary  # 藍色
            elif vote_key == "disaster":
                button_style = discord.ButtonStyle.danger  # 紅色
            
            button = discord.ui.Button(
                label=f"{color_emoji} {vote_label}",
                custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                style=button_style
            )
            button.callback = self._vote_callback
            self.add_item(button)
            button_count += 1
        
        logger.info(f"✅ [AnimeVoteView.__init__] 添加了 {button_count} 個投票按鈕")
        
        # 添加評論按鈕
        comment_button = discord.ui.Button(
            label="💬 留言",
            custom_id=f"anime_comment_{self.video_sn}",
            style=discord.ButtonStyle.success  # 綠色
        )
        comment_button.callback = self._comment_callback
        self.add_item(comment_button)
        
        logger.info(f"✅ [AnimeVoteView.__init__] 添加了評論按鈕，目前共有 {len(self.children)} 個項目")
    
    async def _vote_callback(self, interaction: discord.Interaction):
        """處理投票按鈕點擊 - 投票 +2000 KK幣（每個用戶每條消息只適用一次）"""
        try:
            logger.info(f"🎯 [_vote_callback] 用戶 {interaction.user.name}({interaction.user.id}) 點擊投票按鈕")
            logger.info(f"   custom_id={interaction.custom_id}, message_id={interaction.message.id}")
            
            # 記錄互動時間
            self.last_interaction_time = datetime.now(TW_TZ)
            
            # 解析投票類型
            vote_key = interaction.custom_id.replace(f"anime_vote_", "").rsplit("_", 1)[0]
            vote_label, _ = self.VOTE_TYPES.get(vote_key, ("未知", None))
            
            # 獲取用戶的匿名雜湊（用來防止同一用戶多次投票）
            user_hash = str(hash(interaction.user.id))[:10]
            
            # 記錄投票
            self.tracker.db.record_vote(
                video_sn=self.video_sn,
                anime_sn=self.anime_sn,
                message_id=interaction.message.id,
                vote_type=vote_key,
                user_hash=user_hash
            )
            
            logger.info(f"✅ [_vote_callback] 投票已記錄: {interaction.user.name} 投票了 {vote_label}")
            
            # 立即回應用戶
            logger.info(f"⏳ [_vote_callback] 準備 defer() 響應...")
            await interaction.response.defer()
            logger.info(f"✅ [_vote_callback] defer() 已執行")
            
            # === KK幣獎勵邏輯 (投票 +2000) ===
            reward_given = False
            try:
                from db_adapter import set_user_field, get_user_field
                
                # 檢查是否已發放過獎勵
                if not self.tracker.db.is_reward_already_given(interaction.user.id, interaction.message.id, "vote"):
                    # 獲取當前 KK幣
                    current_kkcoin = get_user_field(interaction.user.id, "kkcoin") or 0
                    new_kkcoin = int(current_kkcoin) + 2000
                    
                    # 更新 KK幣
                    set_user_field(interaction.user.id, "kkcoin", new_kkcoin)
                    
                    # 記錄獎勵發放
                    self.tracker.db.record_reward(
                        user_id=interaction.user.id,
                        message_id=interaction.message.id,
                        reward_type="vote",
                        reward_amount=2000
                    )
                    
                    logger.info(f"💰 [vote_callback] {interaction.user} 投票獲得 2000 KK幣，現在共有 {new_kkcoin} KK幣")
                    reward_given = True
                    
                    # 發送獎勵通知
                    try:
                        reward_embed = discord.Embed(
                            title="🎯 投票獎勵",
                            description="感謝你的投票！",
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
                        await interaction.followup.send(embed=reward_embed, ephemeral=True)
                    except:
                        pass
                else:
                    logger.info(f"⏭️ [vote_callback] {interaction.user} 已獲得過該消息的投票獎勵")
            except ImportError:
                logger.warning("⚠️ [vote_callback] db_adapter 未找到，無法獎勵 KK幣")
            except Exception as e:
                logger.error(f"❌ [vote_callback] 獎勵 KK幣失敗: {e}", exc_info=True)
            
            # 更新原始消息的 embed（添加統計信息）
            try:
                await self._update_message_stats(interaction.message)
                logger.info(f"✅ [vote_callback] {interaction.user} 的投票已記錄並更新消息統計")
            except Exception as update_error:
                logger.error(f"❌ [vote_callback] 更新消息統計失敗: {update_error}", exc_info=True)
        
        except Exception as e:
            logger.error(f"❌ [_vote_callback] 投票失敗: {e}", exc_info=True)
            try:
                await interaction.response.send_message(f"❌ 投票失敗: {str(e)[:50]}", ephemeral=True)
            except:
                pass
    
    async def _comment_callback(self, interaction: discord.Interaction):
        """處理評論按鈕點擊 - 彈出評論輸入框"""
        try:
            # 記錄互動時間
            self.last_interaction_time = datetime.now(TW_TZ)
            
            # 創建簡單的文本輸入模態框
            class CommentModal(discord.ui.Modal, title="留下匿名評論"):
                comment_input = discord.ui.TextInput(
                    label="評論內容",
                    placeholder="寫下你對這部動畫的看法...",
                    max_length=200,
                    required=False
                )
                
                async def on_submit(self, modal_interaction: discord.Interaction):
                    try:
                        comment = str(self.comment_input).strip()
                        if not comment:
                            await modal_interaction.response.send_message("評論不能為空", ephemeral=True)
                            return
                        
                        # 獲取用戶匿名雜湊
                        user_hash = str(hash(modal_interaction.user.id))[:10]
                        
                        # 記錄評論（vote_type 為空表示只是評論）
                        self.modal_tracker.db.record_vote(
                            video_sn=self.modal_video_sn,
                            anime_sn=self.modal_anime_sn,
                            message_id=modal_interaction.message.id,
                            vote_type="comment",
                            comment=comment,
                            user_hash=user_hash
                        )
                        
                        logger.info(f"💬 [comment] {modal_interaction.user} 留言: {comment[:30]}...")
                        
                        # === KK幣獎勵邏輯 (評論 +3000) ===
                        reward_message = "✅ 評論已保存！感謝你的意見"
                        try:
                            from db_adapter import set_user_field, get_user_field
                            
                            # 檢查是否已發放過獎勵
                            if not self.modal_tracker.db.is_reward_already_given(modal_interaction.user.id, modal_interaction.message.id, "comment"):
                                # 獲取當前 KK幣
                                current_kkcoin = get_user_field(modal_interaction.user.id, "kkcoin") or 0
                                new_kkcoin = int(current_kkcoin) + 3000
                                
                                # 更新 KK幣
                                set_user_field(modal_interaction.user.id, "kkcoin", new_kkcoin)
                                
                                # 記錄獎勵發放
                                self.modal_tracker.db.record_reward(
                                    user_id=modal_interaction.user.id,
                                    message_id=modal_interaction.message.id,
                                    reward_type="comment",
                                    reward_amount=3000
                                )
                                
                                logger.info(f"💰 [comment_submit] {modal_interaction.user} 評論獲得 3000 KK幣，現在共有 {new_kkcoin} KK幣")
                                reward_message = "✅ 評論已保存！\n💰 +3000 KK幣獎勵已發放"
                            else:
                                logger.info(f"⏭️ [comment_submit] {modal_interaction.user} 已獲得過該消息的評論獎勵")
                                reward_message = "✅ 評論已保存！"
                        except ImportError:
                            logger.warning("⚠️ [comment_submit] db_adapter 未找到，無法獎勵 KK幣")
                        except Exception as e:
                            logger.error(f"❌ [comment_submit] 獎勵 KK幣失敗: {e}", exc_info=True)
                        
                        await modal_interaction.response.send_message(reward_message, ephemeral=True)
                        
                        # 更新原始消息統計
                        try:
                            await self.modal_update_stats(modal_interaction.message)
                            logger.info(f"✅ [comment_submit] {modal_interaction.user} 的評論已保存並更新消息統計")
                        except Exception as update_error:
                            logger.error(f"❌ [comment_submit] 更新消息統計失敗: {update_error}", exc_info=True)
                    except Exception as e:
                        logger.error(f"❌ [comment_submit] 保存評論失敗: {e}", exc_info=True)
            
            # 將追蹤和更新函數保存到模態框實例
            modal = CommentModal()
            modal.modal_tracker = self.tracker
            modal.modal_video_sn = self.video_sn
            modal.modal_anime_sn = self.anime_sn
            modal.modal_update_stats = self._update_message_stats
            
            await interaction.response.send_modal(modal)
        
        except Exception as e:
            logger.error(f"❌ [_comment_callback] 評論失敗: {e}", exc_info=True)
    
    async def _update_message_stats(self, message: discord.Message):
        """更新消息中的投票統計"""
        try:
            logger.info(f"📝 [_update_message_stats] 開始更新消息 ID={message.id}, 頻道 ID={message.channel.id}")
            
            if not message.embeds:
                logger.warning(f"⚠️ [_update_message_stats] 消息沒有 embed, message_id={message.id}")
                return
            
            original_embed = message.embeds[0]
            logger.info(f"✅ [_update_message_stats] 找到 embed, 標題={original_embed.title}")
            
            # 獲取投票統計和評論
            stats = self.tracker.db.get_vote_stats(message.id)
            comments = self.tracker.db.get_vote_comments(message.id, limit=3)
            logger.info(f"📊 [_update_message_stats] 投票統計: {stats}, 評論數: {len(comments)}")
            
            # 建立統計內容
            stats_content = ""
            if stats and any(stats.values()):
                stat_lines = []
                for vote_key, (vote_label, color_block) in self.VOTE_TYPES.items():
                    count = stats.get(vote_key, 0)
                    if count > 0:
                        stat_lines.append(f"{color_block} {vote_label}: {count} 票")
                stats_content = "\n".join(stat_lines) if stat_lines else ""
            
            # 建立評論內容
            comments_content = ""
            if comments:
                comments_content = "\n".join([f"• {c}" for c in comments])
            
            # 使用 embeds 參數直接編輯，不修改 embed 物件本身
            # 先重新構建完整的 embed，避免 EmbedProxy 序列化問題
            new_embed = discord.Embed(
                title=original_embed.title,
                description=original_embed.description,
                color=original_embed.color,
                timestamp=original_embed.timestamp
            )
            
            # 複製原有的字段，除了統計和評論
            for field in original_embed.fields:
                if field.name not in ["📊 投票統計", "💬 匿名評論"]:
                    new_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            
            # 添加更新後的統計
            if stats_content:
                new_embed.add_field(name="📊 投票統計", value=stats_content, inline=False)
            
            # 添加更新後的評論
            if comments_content:
                new_embed.add_field(name="💬 匿名評論", value=comments_content, inline=False)
            
            # 複製 footer、author 等其他屬性
            if original_embed.footer:
                new_embed.set_footer(text=original_embed.footer.text, icon_url=original_embed.footer.icon_url)
            if original_embed.author:
                new_embed.set_author(name=original_embed.author.name, url=original_embed.author.url, icon_url=original_embed.author.icon_url)
            if original_embed.image:
                new_embed.set_image(url=original_embed.image.url)
            if original_embed.thumbnail:
                new_embed.set_thumbnail(url=original_embed.thumbnail.url)
            
            # 編輯消息
            logger.info(f"🔄 [_update_message_stats] 準備編輯消息 ID={message.id}")
            await message.edit(embed=new_embed)
            logger.info(f"✅ [_update_message_stats] 消息已成功編輯 ID={message.id}")
            
        except discord.Forbidden as e:
            logger.error(f"❌ [_update_message_stats] 權限不足（可能缺少 MANAGE_MESSAGES）: {e}", exc_info=True)
        except discord.NotFound as e:
            logger.error(f"❌ [_update_message_stats] 消息不存在或已被刪除: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ [_update_message_stats] 更新統計失敗: {e}", exc_info=True)


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
        self.scheduler = None  # APScheduler 實例（可選）
        
        # 跟踪動畫的檢查狀態（單一窗口檢查）
        # 格式: {"HH:MM": {"checked": bool, "found": bool, "start_time": datetime}}
        self.anime_retry_queue = {}
        
        # 週統計發送追蹤（防止重複發送）
        self.last_weekly_stats_sent = None  # 上次發送週統計的日期
        
        # 注：任務將在 cog_load 中由 @tasks.loop 自動啟動
        logger.info("📺 [AnimeTracker.__init__] 任務將在 cog_load 中由 @tasks.loop 啟動")
        
        logger.info("📺 [AnimeTracker.__init__] AnimeTracker Cog 初始化完成")
        logger.info(f"📺 Bot 已就緒? {bot.is_ready()}")
        logger.info(f"📺 頻道 ID: {ANIME_CHANNEL_ID}")
        logger.info(f"📺 數據庫路徑: {ANIME_DB_PATH}")
        print("[ANIME_INIT_COMPLETE] ✅ AnimeTracker.__init__ 執行完成", flush=True)
        sys.stdout.flush()
        logger.info("=" * 50)
    
    async def cog_load(self):
        """Cog 加載時啟動任務"""
        print("[COG_LOAD_START] 🎬 cog_load() 開始執行", flush=True)
        logger.info("=" * 50)
        logger.info("🎬 [AnimeTracker.cog_load] cog_load() 被調用")
        try:
            # 恢復舊消息的 view
            print("[COG_LOAD] 恢復舊消息 view 中...", flush=True)
            logger.info("🎬 [AnimeTracker.cog_load] 開始恢復舊消息 view")
            await self._restore_old_message_views()
            print("[COG_LOAD] ✅ 舊消息 view 恢復完成", flush=True)
            logger.info("✅ [AnimeTracker.cog_load] 舊消息 view 恢復完成")
            
            # 啟動動畫檢查任務
            print("[COG_LOAD] 檢查 check_new_anime 任務狀態", flush=True)
            if not self.check_new_anime.is_running():
                print("[COG_LOAD] ✅ 啟動 check_new_anime 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 check_new_anime 任務")
                self.check_new_anime.start()
                print("[COG_LOAD] ✅ check_new_anime 已啟動", flush=True)
                logger.info("✅ [AnimeTracker.cog_load] check_new_anime 已啟動")
            else:
                print("[COG_LOAD] ⚠️ check_new_anime 已在運行", flush=True)
            
            # 啟動週統計任務
            print("[COG_LOAD] 檢查 send_weekly_stats 任務狀態", flush=True)
            if not self.send_weekly_stats.is_running():
                print("[COG_LOAD] ✅ 啟動 send_weekly_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 send_weekly_stats 任務")
                self.send_weekly_stats.start()
                print("[COG_LOAD] ✅ send_weekly_stats 已啟動", flush=True)
                logger.info("✅ [AnimeTracker.cog_load] send_weekly_stats 已啟動")
            else:
                print("[COG_LOAD] ⚠️ send_weekly_stats 已在運行", flush=True)
            
            print("[COG_LOAD_END] ✅ cog_load() 執行完成", flush=True)
            logger.info("✅ [AnimeTracker.cog_load] cog_load() 執行完成")
        except Exception as e:
            print(f"[COG_LOAD_ERROR] ❌ 任務啟動失敗: {e}", flush=True)
            logger.error(f"❌ [AnimeTracker.cog_load] 任務啟動失敗: {e}", exc_info=True)
        logger.info("=" * 50)
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        logger.info("=" * 50)
        logger.info("🛑 [AnimeTracker.cog_unload] cog_unload() 被調用")
        try:
            if self.check_new_anime.is_running():
                self.check_new_anime.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] check_new_anime 已停止")
            
            if self.send_weekly_stats.is_running():
                self.send_weekly_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] send_weekly_stats 已停止")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.cog_unload] 任務停止失敗: {e}", exc_info=True)
        logger.info("=" * 50)
    
    async def _restore_old_message_views(self):
        """恢復舊消息的 view（用於 bot 重啟時）"""
        logger.info("=" * 50)
        logger.info("🔄 [_restore_old_message_views] 開始恢復舊消息 view...")
        
        try:
            # 等待 bot 就緒
            await self.bot.wait_until_ready()
            
            # 獲取所有已保存的消息信息
            message_infos = self.db.get_all_message_infos()
            if not message_infos:
                logger.info("ℹ️ [_restore_old_message_views] 沒有舊消息需要恢復")
                return
            
            logger.info(f"📋 [_restore_old_message_views] 發現 {len(message_infos)} 個需要恢復的舊消息")
            
            restored_count = 0
            for msg_info in message_infos:
                try:
                    message_id = msg_info["message_id"]
                    video_sn = msg_info["video_sn"]
                    anime_sn = msg_info["anime_sn"]
                    anime_name = msg_info["anime_name"]
                    channel_id = msg_info["channel_id"]
                    
                    # 獲取頻道
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"⚠️ [_restore_old_message_views] 找不到頻道 ID={channel_id}")
                        continue
                    
                    # 嘗試獲取舊消息
                    try:
                        message = await channel.fetch_message(message_id)
                    except discord.NotFound:
                        logger.warning(f"⚠️ [_restore_old_message_views] 消息不存在 ID={message_id}")
                        continue
                    except discord.Forbidden:
                        logger.warning(f"⚠️ [_restore_old_message_views] 無權限訪問消息 ID={message_id}")
                        continue
                    
                    # 為這條舊消息創建新的 view
                    episode_data = {
                        "videoSn": video_sn,
                        "animeSn": anime_sn,
                        "title": anime_name
                    }
                    view = await self.generate_anime_view(episode_data)
                    
                    if view is None:
                        logger.warning(f"⚠️ [_restore_old_message_views] 視圖生成失敗 (message_id={message_id})")
                        continue
                    
                    # 註冊視圖到 bot
                    self.bot.add_view(view)
                    logger.info(f"🔗 [_restore_old_message_views] 恢復消息 ID={message_id}, video_sn={video_sn}, anime_name={anime_name}")
                    
                    restored_count += 1
                    await asyncio.sleep(0.1)  # 避免 API 限流
                    
                except Exception as e:
                    logger.error(f"❌ [_restore_old_message_views] 恢復單條消息失敗: {e}")
                    continue
            
            logger.info(f"✅ [_restore_old_message_views] 成功恢復 {restored_count}/{len(message_infos)} 個舊消息 view")
        except Exception as e:
            logger.error(f"❌ [_restore_old_message_views] 恢復過程失敗: {e}", exc_info=True)
        finally:
            logger.info("=" * 50)
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        if hasattr(self, 'scheduler') and self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("✅ [AnimeTracker.cog_unload] Scheduler 已關閉")
    
    async def get_quickchart_short_url(self, chart_config: Dict) -> Optional[str]:
        """
        使用 QuickChart /chart/create API 生成短網址
        
        Args:
            chart_config: QuickChart 圖表配置字典
        
        Returns:
            短網址或 None
        """
        try:
            # 添加常用參數
            chart_config_with_params = {
                **chart_config,
                "bkg": "white",
                "w": 950 if chart_config.get("type") == "line" and len(chart_config.get("data", {}).get("datasets", [])) > 1 else 850,
                "h": 400 if chart_config.get("type") == "line" and len(chart_config.get("data", {}).get("datasets", [])) > 1 else 350
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://quickchart.io/chart/create",
                    json=chart_config_with_params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        short_url = data.get("url")
                        if short_url:
                            logger.info(f"📊 [get_quickchart_short_url] 成功生成短網址: {short_url[:50]}...")
                            return short_url
                        else:
                            logger.warning(f"⚠️ [get_quickchart_short_url] API 無返回 url: {data}")
                            return None
                    else:
                        text = await resp.text()
                        logger.warning(f"⚠️ [get_quickchart_short_url] API 返回 {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.warning(f"⚠️ [get_quickchart_short_url] 生成短網址失敗: {e}")
            return None
    
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
                    today = datetime.now(TW_TZ).strftime("%m/%d")
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
            episode_dt = datetime.strptime(f"{datetime.now(TW_TZ).year}/{up_date} {up_time}", "%Y/%m/%d %H:%M")
            # 將解析的時間設置為台灣時區
            episode_dt = TW_TZ.localize(episode_dt)
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
                    
                    # 詳細日誌：打印完整的 anime 字典（前 2000 字符）
                    anime_str = str(anime)[:2000] if anime else "(empty)"
                    logger.info(f"📺 [fetch_anime_details_from_api] 完整 anime 數據: {anime_str}")
                    
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
                    logger.info(f"✅ [fetch_anime_details_from_api] 提取的觀看數: popular={popular}, type={type(popular)}")
                    
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
        
        logger.info(f"📺 [generate_anime_embed] anime_details type: {type(anime_details)}")
        logger.info(f"📺 [generate_anime_embed] anime_details keys: {list(anime_details.keys()) if anime_details else '(None)'}")
        logger.info(f"📺 [generate_anime_embed] 提取的詳細信息: content_len={len(content)}, tags={api_tags}, popular={popular}, score={score}")
        logger.info(f"📺 [generate_anime_embed] 觀看數詳情: popular={popular}, type={type(popular)}, bool(popular)={bool(popular)}")
        
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
            timestamp=datetime.now(TW_TZ)
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
            name="🎯 匿名投票",
            value="選擇你認為本作的評價，或留下評論\n投票完全匿名，無法追蹤個人身份",
            inline=False
        )
        
        embed.add_field(
            name="🎁 獲得獎勵",
            value="💬 **投票**: +2000 KK幣\n📝 **評論**: +3000 KK幣\n每條消息僅限一次獎勵",
            inline=False
        )
        
        embed.set_footer(text="動畫瘋新番通知 | 使用下方按鈕進行匿名投票")
        return embed
    
    async def generate_anime_view(self, episode: Dict) -> Optional[discord.ui.View]:
        """生成 Discord 按鈕視圖，包括投票按鈕 + 動畫頁與本集連結。"""
        # 創建投票視圖
        logger.info(f"🔧 [generate_anime_view] 開始創建投票視圖")
        vote_view = AnimeVoteView(episode, self)
        logger.info(f"✅ [generate_anime_view] 投票視圖創建完成，按鈕數: {len(vote_view.children)}")
        
        # 添加原有的連結按鈕
        anime_sn = episode.get("animeSn")
        video_sn = episode.get("videoSn")
        
        if anime_sn:
            anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
            vote_view.add_item(discord.ui.Button(label="🔗 動畫頁", url=anime_url, style=discord.ButtonStyle.link))
            logger.info(f"✅ [generate_anime_view] 添加動畫頁按鈕")
        
        if video_sn:
            video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}"
            vote_view.add_item(discord.ui.Button(label="▶️ 觀看", url=video_url, style=discord.ButtonStyle.link))
            logger.info(f"✅ [generate_anime_view] 添加觀看按鈕")
        
        logger.info(f"📋 [generate_anime_view] 最終按鈕數: {len(vote_view.children)}")
        
        return vote_view if vote_view.children else None
    
    @tasks.loop(minutes=1)  # 臨時恢復：每分鐘檢查，但邏輯上只在特定分鐘點執行
    async def check_new_anime(self):
        """
        單一窗口檢查新番 - 在預定時刻 +3~+32 分鐘窗口檢查一次
        
        工作流程：
        1. 獲取 newAnimeSchedule 與預期檢查時刻
        2. 對於每個預期時刻，在 +3~+32 分鐘窗口進行檢查
        3. 每個預定時刻的動畫只會戳一次 API（效率優先）
        4. 每分鐘運行一次，在目標窗口內執行檢查
        """
        now = datetime.now(TW_TZ)
        
        try:
            # 獲取日程表
            schedule = await self._get_anime_schedule()
            if not schedule:
                return
            
            # 獲取今日的預期檢查時刻
            expected_times = self._get_expected_check_times(schedule, now)
            if not expected_times:
                return
            
            # 取得頻道
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if not channel:
                logger.error(f"❌ [check_new_anime] 動畫頻道 {ANIME_CHANNEL_ID} 未找到")
                return
            
            # 檢查 Bootstrap 狀態
            bootstrap_status = self.db.is_bootstrap_completed()
            if not bootstrap_status:
                # 首次運行：Bootstrap
                logger.info("🚀 [check_new_anime] 首次運行，執行 bootstrap...")
                episodes = await self.fetch_new_anime_from_api()
                if episodes:
                    self.db.bootstrap_add_all(episodes)
                self.db.mark_bootstrap_completed()
                self.bootstrap_completed = True
                logger.info("✅ [check_new_anime] Bootstrap 完成")
                return
            
            # 對於每個預期時刻，檢查是否在 +3~+5 分鐘窗口內
            for scheduled_time_str in expected_times:
                # 初始化追蹤狀態
                if scheduled_time_str not in self.anime_retry_queue:
                    self.anime_retry_queue[scheduled_time_str] = {
                        'found': False,    # 是否已找到新集
                        'start_time': now,
                        # checked_at_5, checked_at_10 等會在檢查時動態設置
                    }
                
                # 解析預定時刻
                try:
                    scheduled_time = datetime.strptime(scheduled_time_str, "%H:%M").time()
                    scheduled_dt = datetime.combine(now.date(), scheduled_time, tzinfo=TW_TZ)
                except:
                    continue
                
                # 計算時間差（分鐘）
                time_diff_min = (now - scheduled_dt).total_seconds() / 60
                
                # 在 +3~+32 分鐘窗口內，於固定的檢查分鐘點執行檢查
                # 檢查時間點：+5, +10, +15, +20, +25, +30（容差 ±1 分鐘）
                CHECK_INTERVALS = [5, 10, 15, 20, 25, 30]
                
                if 3 <= time_diff_min < 32:
                    state = self.anime_retry_queue[scheduled_time_str]
                    
                    # 如果已找到新集，就不再檢查
                    if state['found']:
                        continue
                    
                    # 檢查是否在某個檢查分鐘點附近（容差 ±0.5 分鐘 = ±30秒）
                    for check_minute in CHECK_INTERVALS:
                        check_key = f"checked_at_{check_minute}"
                        
                        # 如果該分鐘點還沒檢查過，且時間接近
                        if not state.get(check_key, False) and abs(time_diff_min - check_minute) < 0.5:
                            logger.info(f"📺 [check_new_anime] 在 +{check_minute} 分鐘檢查 {scheduled_time_str} ({now.strftime('%H:%M:%S')})")
                            
                            # 執行檢查
                            new_found = await self._check_and_send_anime(scheduled_time_str, channel)
                            
                            # 標記該分鐘點已檢查
                            state[check_key] = True
                            if new_found:
                                state['found'] = True
                                logger.info(f"✅ [check_new_anime] 找到新集，停止檢查時刻 {scheduled_time_str}")
                            break
                
                # 清理過期的數據（超過 12 小時）
                if time_diff_min > 720:
                    if scheduled_time_str in self.anime_retry_queue:
                        del self.anime_retry_queue[scheduled_time_str]
        
        except Exception as e:
            logger.error(f"❌ Error in check_new_anime: {e}", exc_info=True)
    
    @check_new_anime.before_loop
    async def before_check_new_anime(self):
        """等待 bot 就緒才開始檢查動畫"""
        await self.bot.wait_until_ready()
        logger.info("✅ [check_new_anime] Bot 已就緒，開始檢查新番")
    
    async def _check_and_send_anime(self, scheduled_time_str: str, channel) -> bool:
        """
        檢查新番集並發送通知（用於多窗口檢查）
        
        Args:
            scheduled_time_str: 預定時刻字符串，例如 "14:30"
            channel: Discord 頻道物件
            
        Returns:
            bool: 是否找到並發送了新集
        """
        try:
            # 獲取最新動畫數據
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                logger.warning(f"⚠️ [_check_and_send_anime] 無法從 API 獲取數據 (時刻: {scheduled_time_str})")
                return False
            
            # 檢查新集
            new_episodes = []
            for ep in episodes:
                video_sn = ep.get("videoSn")
                if video_sn and not self.db.is_notified(video_sn):
                    new_episodes.append(ep)
            
            if not new_episodes:
                logger.info(f"⏭️  [{scheduled_time_str}] 沒有新集")
                return False
            
            # 發送新集通知
            logger.info(f"🆕 [{scheduled_time_str}] 發現 {len(new_episodes)} 個新集，開始推播...")
            for ep in new_episodes:
                try:
                    embed = await self.generate_anime_embed(ep)
                    view = await self.generate_anime_view(ep)
                    
                    if view is None:
                        logger.warning(f"⚠️ [_check_and_send_anime] 視圖為 None，無法發送消息 (video_sn={ep.get('videoSn')})")
                        continue
                    
                    # 📌 關鍵：註冊永久視圖到 bot，否則按鈕點擊不會被識別
                    logger.info(f"🔗 [_check_and_send_anime] 註冊視圖到 bot (video_sn={ep.get('videoSn')})")
                    self.bot.add_view(view)
                    logger.info(f"✅ [_check_and_send_anime] 視圖已註冊")
                    
                    message = await channel.send(embed=embed, view=view, silent=True)
                    logger.info(f"✅ [_check_and_send_anime] 消息已發送 (message_id={message.id}, video_sn={ep.get('videoSn')})")
                    
                    # 💾 保存消息 ID 以用於 bot 重啟時恢復 view
                    self.db.save_message_info(
                        message_id=message.id,
                        video_sn=ep.get("videoSn"),
                        anime_sn=ep.get("animeSn"),
                        anime_name=ep.get("title", "Unknown"),
                        channel_id=channel.id
                    )
                    logger.info(f"💾 [_check_and_send_anime] 消息 ID 已保存到數據庫")
                    
                    # 記錄已通知
                    self.db.add_notified(
                        video_sn=ep.get("videoSn"),
                        anime_sn=ep.get("animeSn"),
                        anime_name=ep.get("title", "Unknown"),
                        volume=ep.get("volume", ""),
                        cover_url=ep.get("cover", "")
                    )
                    
                    # 避免 Discord 限流
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.error(f"❌ Error sending anime embed for {scheduled_time_str}: {e}")
                    await asyncio.sleep(1)
            
            # 標記為已找到
            self.anime_retry_queue[scheduled_time_str]['found'] = True
            logger.info(f"✅ [{scheduled_time_str}] 推播完成")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error in _check_and_send_anime: {e}", exc_info=True)
            return False
    
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
    

    
    @tasks.loop(hours=1)
    async def send_weekly_stats(self):
        """自動發送週統計 - 每週一 台灣時間 00:00 發送"""
        now = datetime.now(TW_TZ)
        
        try:
            # 檢查是否是週一且時間在午夜時刻（00:00-00:59）
            is_monday = now.weekday() == 0  # 0 = Monday
            is_send_time = now.hour == 0  # 台灣時間 00:00-00:59
            
            # 檢查是否已在本週發送過（防止重複）
            week_start = now - timedelta(days=now.weekday())
            week_start_date = week_start.date()
            
            if is_monday and is_send_time and self.last_weekly_stats_sent != week_start_date:
                logger.info(f"📊 [send_weekly_stats] 週一時間到，準備發送週統計...")
                
                # 獲取頻道
                channel = self.bot.get_channel(ANIME_CHANNEL_ID)
                if not channel:
                    logger.error(f"❌ [send_weekly_stats] 找不到頻道 {ANIME_CHANNEL_ID}")
                    return
                
                # 獲取週統計數據
                weekly_stats = self.db.get_weekly_vote_stats()
                
                if not weekly_stats:
                    logger.info("📊 [send_weekly_stats] 本週無投票數據")
                    self.last_weekly_stats_sent = week_start_date
                    return
                
                # 創建主統計 embed
                week_end = now
                week_start_str = week_start.strftime("%m/%d")
                week_end_str = week_end.strftime("%m/%d")
                
                embed = discord.Embed(
                    title="📊 本週動畫投票統計",
                    description=f"**統計週期**: {week_start_str} - {week_end_str}",
                    color=discord.Color.blue(),
                    timestamp=now
                )
                
                # 按投票總數排序
                sorted_animes = sorted(
                    weekly_stats.items(),
                    key=lambda x: x[1]['total_votes'],
                    reverse=True
                )
                
                # 添加各動畫的統計
                for rank, (anime_sn, stats) in enumerate(sorted_animes[:10], 1):  # 顯示前 10 部
                    anime_name = stats['anime_name']
                    total_votes = stats['total_votes']
                    votes_breakdown = stats['votes']
                    episode_count = len(stats['episodes'])
                    
                    # 構建投票明細
                    vote_type_names = {
                        'masterpiece': '🟢 神作',
                        'great': '⚫ 佳作',
                        'darkhorse': '⚫ 黑馬',
                        'decent': '🔵 普作',
                        'controversial': '⚫ 爭議作',
                        'disaster': '🔴 雷作'
                    }
                    
                    vote_details = []
                    for vote_type in sorted(votes_breakdown.keys(), 
                                           key=lambda x: votes_breakdown[x], reverse=True):
                        count = votes_breakdown[vote_type]
                        label = vote_type_names.get(vote_type, vote_type)
                        vote_details.append(f"{label}: {count}")
                    
                    details_str = " | ".join(vote_details) if vote_details else "無投票"
                    
                    embed.add_field(
                        name=f"#{rank} {anime_name}",
                        value=f"**投票總數**: {total_votes} | **涉及集數**: {episode_count}\n{details_str}",
                        inline=False
                    )
                
                # 添加總體統計
                total_all_votes = sum(stats['total_votes'] for stats in weekly_stats.values())
                unique_animes = len(weekly_stats)
                
                embed.set_footer(text=f"總計: {total_all_votes} 投票 | {unique_animes} 部作品")
                
                # 發送統計
                await channel.send(embed=embed)
                logger.info(f"✅ [send_weekly_stats] 週統計已發送: {unique_animes} 部作品, {total_all_votes} 投票")
                
                # 標記已發送
                self.last_weekly_stats_sent = week_start_date
        
        except Exception as e:
            logger.error(f"❌ [send_weekly_stats] 發送週統計失敗: {e}", exc_info=True)
    
    @send_weekly_stats.before_loop
    async def before_send_weekly_stats(self):
        """在第一次循環前等待 bot 就緒"""
        logger.info("📊 [before_send_weekly_stats] 等待 bot 就緒...")
        await self.bot.wait_until_ready()
        logger.info("✅ [before_send_weekly_stats] Bot 已就緒，週統計任務準備就緒")
        
        # 啟動任務
        if not self.send_weekly_stats.is_running():
            try:
                self.send_weekly_stats.start()
                logger.info("🚀 [before_send_weekly_stats] 週統計任務已啟動")
            except Exception as e:
                logger.error(f"❌ [before_send_weekly_stats] 啟動任務失敗: {e}", exc_info=True)

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
                    
                    if view is None:
                        logger.warning(f"⚠️ [anime_test] 視圖為 None，跳過消息 (video_sn={ep.get('videoSn')})")
                        continue
                    
                    # 📌 關鍵：註冊永久視圖到 bot，否則按鈕點擊不會被識別
                    logger.info(f"🔗 [anime_test] 註冊視圖到 bot (video_sn={ep.get('videoSn')})")
                    self.bot.add_view(view)
                    logger.info(f"✅ [anime_test] 視圖已註冊")
                    
                    message = await interaction.followup.send(embed=embed, view=view, silent=True)
                    logger.info(f"✅ [anime_test] 消息已發送 (message_id={message.id}, video_sn={ep.get('videoSn')})")
                    
                    # 💾 保存消息 ID 以用於 bot 重啟時恢復 view
                    self.db.save_message_info(
                        message_id=message.id,
                        video_sn=ep.get("videoSn"),
                        anime_sn=ep.get("animeSn"),
                        anime_name=ep.get("title", "Unknown"),
                        channel_id=interaction.channel_id
                    )
                    logger.info(f"💾 [anime_test] 消息 ID 已保存到數據庫")
                    
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
    
    @app_commands.command(name="anime_weekly", description="查看本週投票統計")
    async def anime_weekly(self, interaction: discord.Interaction):
        """顯示本週的動畫投票統計 embed"""
        try:
            await interaction.response.defer()
            
            # 獲取週統計數據
            weekly_stats = self.db.get_weekly_vote_stats()
            
            if not weekly_stats:
                await interaction.followup.send("📊 本週暫無投票數據")
                logger.info("📺 [anime_weekly] 本週無投票數據")
                return
            
            # 計算本週開始日期
            from datetime import datetime, timedelta
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%m/%d")
            week_end_str = now.strftime("%m/%d")
            
            # 創建主統計 embed
            embed = discord.Embed(
                title="📊 本週動畫投票統計",
                description=f"**統計週期**: {week_start_str} - {week_end_str}",
                color=discord.Color.blue(),
                timestamp=now
            )
            
            # 按投票總數排序
            sorted_animes = sorted(
                weekly_stats.items(),
                key=lambda x: x[1]['total_votes'],
                reverse=True
            )
            
            # 添加各動畫的統計
            for rank, (anime_sn, stats) in enumerate(sorted_animes[:10], 1):  # 顯示前 10 部
                anime_name = stats['anime_name']
                total_votes = stats['total_votes']
                votes_breakdown = stats['votes']
                episode_count = len(stats['episodes'])
                
                # 構建投票明細（按數量排序）
                vote_details = []
                vote_type_names = {
                    'masterpiece': '🟢 神作',
                    'great': '⚫ 佳作',
                    'darkhorse': '⚫ 黑馬',
                    'decent': '🔵 普作',
                    'controversial': '⚫ 爭議作',
                    'disaster': '🔴 雷作'
                }
                
                for vote_type in sorted(votes_breakdown.keys(), 
                                       key=lambda x: votes_breakdown[x], reverse=True):
                    count = votes_breakdown[vote_type]
                    label = vote_type_names.get(vote_type, vote_type)
                    vote_details.append(f"{label}: {count}")
                
                details_str = " | ".join(vote_details) if vote_details else "無投票"
                
                embed.add_field(
                    name=f"#{rank} {anime_name}",
                    value=f"**投票總數**: {total_votes} | **涉及集數**: {episode_count}\n{details_str}",
                    inline=False
                )
            
            # 添加總體統計
            total_all_votes = sum(stats['total_votes'] for stats in weekly_stats.values())
            unique_animes = len(weekly_stats)
            
            embed.set_footer(text=f"總計: {total_all_votes} 投票 | {unique_animes} 部作品")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"📊 [anime_weekly] 顯示週統計: {unique_animes} 部作品, {total_all_votes} 投票")
            
        except Exception as e:
            logger.error(f"❌ [anime_weekly] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    
    async def get_short_chart_url(self, chart_config: dict) -> str:
        """獲取 QuickChart 短 URL（解決 Discord 2048 字元限制）"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://quickchart.io/chart/create",
                    json={"chart": chart_config},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        url = data.get('url')
                        if url:
                            logger.info(f"✅ [get_short_chart_url] 取得短 URL: {url[:50]}...")
                            return url
                        else:
                            logger.warning(f"⚠️ [get_short_chart_url] API 返回無 url: {data}")
                            return None
                    else:
                        logger.warning(f"⚠️ [get_short_chart_url] 返回狀態 {resp.status}")
                        return None
        except Exception as e:
            logger.warning(f"⚠️ [get_short_chart_url] 請求失敗: {e}")
            return None
    
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
                                    logger.info(f"📺 [anime_ranking] 獲得動畫名稱: {anime_name} (animeSn={anime_sn})")
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
                        logger.info(f"📺 [anime_ranking] 排行動畫: {data['name']} (animeSn={anime_sn}, views={data['total_views']})")
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
            
            # 嘗試獲取有多集的動畫數據（用於多線圖）
            # 使用短 URL API 無視 URL 長度限制
            multi_anime = self.db.get_multi_episode_anime_for_chart(limit=10, min_episodes=1)
            logger.info(f"📺 [anime_ranking] 查詢 multi_anime 結果: {len(multi_anime) if multi_anime else 0} 部動畫")
            if multi_anime:
                for i, anime in enumerate(multi_anime[:3]):
                    logger.info(f"  📺 [{i+1}] {anime['name']}: {len(anime['episodes'])} 集, {anime['total_views']} 次觀看")
            
            embed = discord.Embed(
                title="🏆 本季動畫觀看排行榜",
                color=discord.Color.gold(),
                timestamp=datetime.now(TW_TZ)
            )
            
            # 如果有多集數據，生成多線趨勢圖；否則使用單線聚合圖
            if multi_anime and len(multi_anime) >= 1:
                # ===== 模式 A：多線趨勢圖（每部動畫一條線）=====
                embed.description = f"集數觀看趨勢 ({len(multi_anime)} 部動畫)"
                
                # 構建多線圖表
                datasets = []
                
                # 顏色數組（10 種顏色）
                colors = [
                    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
                    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#ABEBC6"
                ]
                
                # 找出所有集數編號（X 軸）
                all_episodes = set()
                for anime in multi_anime:
                    for ep in anime['episodes']:
                        all_episodes.add(ep['num'])
                
                episode_labels = sorted(list(all_episodes))
                
                # 為每部動畫建立一條線
                for idx, anime in enumerate(multi_anime):
                    name = anime['name'][:10]  # 最多 10 個字
                    color = colors[idx % len(colors)]
                    
                    # 建立該動畫的數據點（缺失集用 None）
                    ep_dict = {ep['num']: ep['views'] for ep in anime['episodes']}
                    data = [ep_dict.get(label) for label in episode_labels]
                    
                    datasets.append({
                        "label": name,
                        "data": data,
                        "borderColor": color,
                        "fill": False,
                        "showLine": True
                    })
                
                # 構建圖表配置（極速優化版）
                try:
                    chart_config = {
                        "type": "line",
                        "data": {
                            "labels": episode_labels,
                            "datasets": datasets
                        },
                        "options": {
                            "plugins": {
                                "legend": {"position": "top"}
                            }
                        }
                    }
                    
                    # 嘗試使用短 URL API，失敗則改用直接 URL
                    short_url = await self.get_short_chart_url(chart_config)
                    if short_url:
                        chart_url = short_url
                        logger.info(f"✅ [anime_ranking] 多線趨勢圖短 URL 已取得")
                    else:
                        # 改用直接 URL（只要長度不超過 2048）
                        config_json = json.dumps(chart_config, separators=(',', ':'), ensure_ascii=False)
                        encoded = quote(config_json)
                        chart_url = f"https://quickchart.io/chart?bkg=white&w=950&h=400&c={encoded}"
                        
                        logger.info(f"📺 [anime_ranking] 直接 URL 長度: {len(chart_url)}")
                        
                        if len(chart_url) > 2048:
                            logger.warning(f"⚠️ [anime_ranking] URL {len(chart_url)} 字元超過限制，改用文字顯示")
                            multi_anime = None  # 改用模式 B
                            chart_url = None
                    
                    # 直接使用圖表 URL
                    if chart_url:
                        embed.set_image(url=chart_url)
                        logger.info(f"✅ [anime_ranking] 多線趨勢圖已設置")
                    
                    # 添加參賽動畫排名信息
                    anime_ranking_info = []
                    for idx, anime in enumerate(multi_anime, 1):
                        rank_emoji = ["🥇", "🥈", "🥉"] + [f"{i}️⃣" for i in range(4, 11)]
                        emoji = rank_emoji[idx - 1] if idx <= 10 else "📌"
                        anime_ranking_info.append(
                            f"{emoji} **{anime['short_name']}** - {anime['total_views']:,} 次閱覽"
                        )
                    
                    # 分成兩個字段顯示（Top 5 和 6-10）
                    if len(anime_ranking_info) > 5:
                        embed.add_field(
                            name="🏅 Top 5 熱度排名",
                            value="\n".join(anime_ranking_info[:5]),
                            inline=True
                        )
                        embed.add_field(
                            name="🎖️ 6-10 熱度排名",
                            value="\n".join(anime_ranking_info[5:]),
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="📈 參賽動畫排名",
                            value="\n".join(anime_ranking_info),
                            inline=False
                        )
                except Exception as e:
                    logger.warning(f"⚠️ [anime_ranking] 生成多線圖失敗: {e}，改用文字顯示")
                    multi_anime = None  # 改用模式 B
            
            # === 模式 B：文字排行列表（當無多集數據或圖表生成失敗）===
            if not multi_anime or len(multi_anime) < 2:
                embed.description = f"前 {len(top_anime)} 名熱度排行"
                
                # 生成單線聚合圖
                anime_names = []
                anime_views = []
                for idx, anime in enumerate(top_anime, 1):
                    anime_name = anime.get('name', f"#{anime.get('anime_sn')}")
                    short_name = anime_name[:8] if len(anime_name) > 8 else anime_name
                    anime_names.append(f"#{idx} {short_name}")
                    anime_views.append(anime['total_views'])
                
                try:
                    chart_config = {
                        "type": "line",
                        "data": {
                            "labels": anime_names,
                            "datasets": [{
                                "data": anime_views,
                                "borderColor": "#FFD700",
                                "backgroundColor": "rgba(255,215,0,0.1)",
                                "borderWidth": 2,
                                "fill": True,
                                "tension": 0.3,
                                "pointRadius": 3,
                                "pointBackgroundColor": "#FFD700"
                            }]
                        },
                        "options": {
                            "scales": {
                                "y": {"ticks": {"font": {"size": 10}}},
                                "x": {"ticks": {"font": {"size": 8}}}
                            },
                            "plugins": {"legend": {"display": False}}
                        }
                    }
                    
                    # 直接使用 URL 編碼方式（確保圖片一定能顯示）
                    config_json = json.dumps(chart_config, separators=(',', ':'), ensure_ascii=False)
                    encoded = quote(config_json)
                    chart_url = f"https://quickchart.io/chart?bkg=white&w=850&h=350&c={encoded}"
                    
                    if len(chart_url) <= 2048:
                        embed.set_image(url=chart_url)
                        logger.info(f"📺 [anime_ranking] 單線聚合圖 URL 已設置 (長度: {len(chart_url)})")
                except Exception as e:
                    logger.warning(f"⚠️ [anime_ranking] 生成單線圖 URL 失敗: {e}")
                
                # 添加文字排行
                ranking_text = []
                for idx, anime in enumerate(top_anime, 1):
                    anime_name = anime.get('name', f'Anime #{anime.get("anime_sn", "?")}').strip()
                    line = f"#{idx} **{anime_name}** - {anime['total_views']:,} 次"
                    ranking_text.append(line)
                
                embed.description += "\n\n" + "\n".join(ranking_text)
            
            embed.set_footer(text="📊 集數觀看趨勢分析" if multi_anime and len(multi_anime) >= 1 else "📈 本季熱度聚合排行")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"📺 [anime_ranking] 顯示排行榜（模式: {'多線趨勢' if multi_anime and len(multi_anime) >= 1 else '聚合排行'}）")
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
    """Discord.py 2.0+ 加載方式 - cog_load() 會自動被調用"""
    print("[SETUP_START] 🎬 AnimeTracker setup() 開始", flush=True)
    await bot.add_cog(AnimeTracker(bot))
    logger.info("✅ AnimeTracker Cog 已加載（任務將在 cog_load() 中啟動）")
    print("[SETUP_END] 🎬 AnimeTracker setup() 完成 - cog_load() 將自動被調用", flush=True)
