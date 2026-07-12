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
ANIME_CHECK_HISTORY_TABLE = "anime_check_history"  # 每日時刻檢查歷史（防止重複檢查，解決 Bot 重啟問題）
ANIME_WEEKLY_SCHEDULE_TABLE = "anime_weekly_schedule"  # 週表：每週一自動拉取的完整時程表（減少 API 調用）


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
                
                # 8. 每日時刻檢查歷史（防止 Bot 重啟導致同一時刻被重複檢查）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_CHECK_HISTORY_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        check_date DATE NOT NULL,
                        scheduled_time TEXT NOT NULL,
                        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(check_date, scheduled_time)
                    )
                """)
                
                # 9. 週表：每週一自動拉取的完整一週時程表（減少 API 調用）
                # 修復：先檢查舊表是否有錯誤的 UNIQUE(week_start_date) 約束，若有則重建
                try:
                    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{ANIME_WEEKLY_SCHEDULE_TABLE}'")
                    existing_row = cursor.fetchone()
                    if existing_row and 'week_start_date DATE NOT NULL UNIQUE' in existing_row[0]:
                        logger.info(f"🔧 [init_db] 偵測到舊的 {ANIME_WEEKLY_SCHEDULE_TABLE} 錯誤結構（week_start_date UNIQUE），準備重建")
                        # 備份舊表
                        cursor.execute(f"DROP TABLE IF EXISTS {ANIME_WEEKLY_SCHEDULE_TABLE}_old")
                        cursor.execute(f"ALTER TABLE {ANIME_WEEKLY_SCHEDULE_TABLE} RENAME TO {ANIME_WEEKLY_SCHEDULE_TABLE}_old")
                        conn.commit()
                        logger.info(f"✅ [init_db] 舊表已備份為 {ANIME_WEEKLY_SCHEDULE_TABLE}_old")
                except Exception as migrate_err:
                    logger.warning(f"⚠️ [init_db] 週表遷移檢查失敗: {migrate_err}")

                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ANIME_WEEKLY_SCHEDULE_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_start_date DATE NOT NULL,
                        day_of_week INTEGER NOT NULL,
                        scheduled_time TEXT NOT NULL,
                        anime_sn INTEGER DEFAULT 0,
                        anime_data TEXT NOT NULL,
                        pushed BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(week_start_date, day_of_week, scheduled_time, anime_sn)
                    )
                """)
                
                conn.commit()
                
                # 驗證所有表都被創建
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = {row[0] for row in cursor.fetchall()}
                required_tables = {
                    NOTIFIED_TABLE, BOOTSTRAP_FLAG_TABLE, ANIME_DETAILS_TABLE,
                    ANIME_STATS_TABLE, EPISODE_STATS_TABLE, ANIME_MESSAGES_TABLE,
                    ANIME_CHECK_HISTORY_TABLE, ANIME_WEEKLY_SCHEDULE_TABLE
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
                # 確保表中至少有一行
                cursor.execute(f"INSERT OR IGNORE INTO {BOOTSTRAP_FLAG_TABLE} (id, bootstrap_completed) VALUES (1, 0)")
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
    
    def get_top_anime_by_views(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """獲取觀看次數最多的動畫排行（直接從 episode_statistics 聚合）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                where_clauses = []
                params = []

                if start_time:
                    where_clauses.append("recorded_at >= ?")
                    params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

                if end_time:
                    where_clauses.append("recorded_at < ?")
                    params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                # 直接從 episode_statistics 聚合，而不是等待 anime_statistics 更新
                cursor.execute(f"""
                    SELECT 
                        animeSn,
                        COUNT(*) as total_episodes,
                        SUM(views) as total_views,
                        AVG(views) as avg_views,
                        AVG(score) as avg_score
                    FROM {EPISODE_STATS_TABLE}
                    {where_sql}
                    GROUP BY animeSn
                    ORDER BY total_views DESC LIMIT ?
                """, (*params, limit))
                
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
    
    def get_multi_episode_anime_for_chart(
        self,
        limit: int = 10,
        min_episodes: int = 1,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """獲取有多集數據的動畫（用於多線坐標圖），按總觀看次數排序
        改進：降低 min_episodes 預設值為 1，讓更多動畫能納入統計
        
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
                where_clauses = []
                params = []

                if start_time:
                    where_clauses.append("recorded_at >= ?")
                    params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

                if end_time:
                    where_clauses.append("recorded_at < ?")
                    params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                
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
                    {where_sql}
                    GROUP BY animeSn
                    HAVING COUNT(*) >= ?
                    ORDER BY total_views DESC LIMIT ?
                """, (*params, min_episodes, limit))
                
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
                    episode_where = ["animeSn = ?"]
                    episode_params = [anime_sn]

                    if start_time:
                        episode_where.append("recorded_at >= ?")
                        episode_params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

                    if end_time:
                        episode_where.append("recorded_at < ?")
                        episode_params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

                    cursor.execute(f"""
                        SELECT episode_num, views FROM {EPISODE_STATS_TABLE}
                        WHERE {' AND '.join(episode_where)}
                        ORDER BY episode_num ASC
                    """, tuple(episode_params))
                    
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
    
    def is_time_checked_today(self, scheduled_time: str, check_date=None) -> bool:
        """檢查某個時刻在指定日期是否已檢查過（防止重複檢查）
        
        Args:
            scheduled_time: 預定時刻，格式 "HH:MM"
            check_date: 檢查日期，如果為 None 使用今天（台灣時區）
        
        Returns:
            bool: 如果已檢查過則返回 True，否則返回 False
        """
        try:
            if check_date is None:
                check_date = datetime.now(TW_TZ).date()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_CHECK_HISTORY_TABLE}
                    WHERE check_date = ? AND scheduled_time = ?
                """, (check_date, scheduled_time))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Error checking time history: {e}")
            return False
    
    def mark_time_checked(self, scheduled_time: str, check_date=None) -> bool:
        """標記某個時刻已檢查過（用於防止重複檢查）
        
        Args:
            scheduled_time: 預定時刻，格式 "HH:MM"
            check_date: 檢查日期，如果為 None 使用今天（台灣時區）
        
        Returns:
            bool: 如果成功標記則返回 True，否則返回 False
        """
        try:
            if check_date is None:
                check_date = datetime.now(TW_TZ).date()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR IGNORE INTO {ANIME_CHECK_HISTORY_TABLE}
                    (check_date, scheduled_time, checked_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (check_date, scheduled_time))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error marking time checked: {e}")
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
    
    def save_weekly_schedule(self, week_start_date: str, schedule_data: List[Dict]) -> bool:
        """儲存每週的完整時程表
        
        Args:
            week_start_date: 週一日期 (YYYY-MM-DD)
            schedule_data: 每日時程表 [{day_of_week: 1-7, scheduled_time: "HH:MM", anime_data: {...}}]
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                saved_count = 0
                for entry in schedule_data:
                    # 提取 animeSn 作為組合唯一鍵的一部分（允許同一時刻多部動畫）
                    anime_sn = entry['anime_data'].get('animeSn', 0) or 0
                    cursor.execute(f"""
                        INSERT OR REPLACE INTO {ANIME_WEEKLY_SCHEDULE_TABLE}
                        (week_start_date, day_of_week, scheduled_time, anime_sn, anime_data, pushed)
                        VALUES (?, ?, ?, ?, ?, 0)
                    """, (
                        week_start_date,
                        entry['day_of_week'],
                        entry['scheduled_time'],
                        anime_sn,
                        json.dumps(entry['anime_data'], ensure_ascii=False)
                    ))
                    saved_count += 1
                conn.commit()
                logger.info(f"✅ [save_weekly_schedule] 週表已保存: {week_start_date}, {saved_count} 筆")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving weekly schedule: {e}", exc_info=True)
            return False
    
    def get_today_schedule(self) -> List[Dict]:
        """獲取今天的時程表（從週表中）"""
        try:
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())  # 取得本週一的日期
            day_of_week = (now.weekday() + 1) % 7 or 7  # 1=Mon, 7=Sun
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT scheduled_time, anime_data, pushed FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE week_start_date = ? AND day_of_week = ?
                    ORDER BY scheduled_time ASC
                """, (week_start.strftime("%Y-%m-%d"), day_of_week))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'scheduled_time': row[0],
                        'anime_data': json.loads(row[1]),
                        'pushed': bool(row[2])
                    })
                return results
        except Exception as e:
            logger.error(f"❌ Error getting today schedule: {e}")
            return []
    
    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記某個時刻已推送過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                    SET pushed = 1
                    WHERE week_start_date = ? AND day_of_week = ? AND scheduled_time = ?
                """, (week_start_date, day_of_week, scheduled_time))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error marking time pushed: {e}")
            return False


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
            # 所有投票按鈕都用灰色
            button_style = discord.ButtonStyle.secondary  # 灰色
            
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
            style=discord.ButtonStyle.secondary  # 灰色
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
        # 單次推送最多處理的新集數量，避免阻塞事件循環
        self.MAX_NEW_EPISODES_PER_PUSH = 20

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
        import sys
        print("[COG_LOAD_START] 🎬 cog_load() 開始執行", flush=True)
        sys.stdout.flush()
        
        logger.info("=" * 50)
        logger.info("🎬 [AnimeTracker.cog_load] cog_load() 被調用")
        
        try:
            # 恢復舊消息的視圖 - 在 bot 重啟時重新註冊所有永久視圖
            print("[COG_LOAD] 嘗試恢復舊消息 view...", flush=True)
            await self._restore_old_message_views()
            print("[COG_LOAD] ✅ 舊消息 view 恢復完成", flush=True)
            
            # 如果週表為空，立即拉取（解決首次部署/非禮拜天重啟問題）
            print("[COG_LOAD] 檢查週表是否需要初始化...", flush=True)
            await self._init_weekly_schedule_if_empty()
            print("[COG_LOAD] ✅ 週表初始化檢查完成", flush=True)
            
            # 補推：若 bot 重啟前有未推送的動畫，啟動時補發
            print("[COG_LOAD] 檢查是否有錯過的動畫推送...", flush=True)
            await self._catchup_missed_pushes()
            print("[COG_LOAD] ✅ 補推檢查完成", flush=True)
            
            # 啟動週統計任務
            print("[COG_LOAD] 檢查 send_weekly_stats 任務狀態", flush=True)
            if not self.send_weekly_stats.is_running():
                print("[COG_LOAD] ✅ 啟動 send_weekly_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 send_weekly_stats 任務")
                try:
                    self.send_weekly_stats.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] send_weekly_stats 已啟動 (is_running={self.send_weekly_stats.is_running()})")
                    print("[COG_LOAD] ✅ send_weekly_stats 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 send_weekly_stats 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 send_weekly_stats 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 send_weekly_stats...")
                        self.send_weekly_stats.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，send_weekly_stats 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，send_weekly_stats 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] send_weekly_stats 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ send_weekly_stats 已在運行", flush=True)
            
            # 啟動週表刷新任務
            print("[COG_LOAD] 檢查 refresh_weekly_schedule 任務狀態", flush=True)
            if not self.refresh_weekly_schedule.is_running():
                print("[COG_LOAD] ✅ 啟動 refresh_weekly_schedule 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 任務")
                try:
                    self.refresh_weekly_schedule.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] refresh_weekly_schedule 已啟動 (is_running={self.refresh_weekly_schedule.is_running()})")
                    print("[COG_LOAD] ✅ refresh_weekly_schedule 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 refresh_weekly_schedule 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 refresh_weekly_schedule...")
                        self.refresh_weekly_schedule.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，refresh_weekly_schedule 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，refresh_weekly_schedule 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] refresh_weekly_schedule 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ refresh_weekly_schedule 已在運行", flush=True)
            
            # 啟動推送檢查任務（週表模式）
            print("[COG_LOAD] 檢查 check_scheduled_push 任務狀態", flush=True)
            if not self.check_scheduled_push.is_running():
                print("[COG_LOAD] ✅ 啟動 check_scheduled_push 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 check_scheduled_push 任務")
                try:
                    self.check_scheduled_push.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] check_scheduled_push 已啟動 (is_running={self.check_scheduled_push.is_running()})")
                    print("[COG_LOAD] ✅ check_scheduled_push 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 check_scheduled_push 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 check_scheduled_push 失敗: {start_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] check_scheduled_push 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ check_scheduled_push 已在運行", flush=True)

            # 啟動週期統計同步任務
            print("[COG_LOAD] 檢查 sync_episode_stats 任務狀態", flush=True)
            if not self.sync_episode_stats.is_running():
                print("[COG_LOAD] ✅ 啟動 sync_episode_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 sync_episode_stats 任務")
                try:
                    self.sync_episode_stats.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] sync_episode_stats 已啟動 (is_running={self.sync_episode_stats.is_running()})")
                    print("[COG_LOAD] ✅ sync_episode_stats 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 sync_episode_stats 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 sync_episode_stats 失敗: {start_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] sync_episode_stats 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ sync_episode_stats 已在運行", flush=True)

            print("[COG_LOAD_END] ✅ cog_load() 執行完成", flush=True)
            sys.stdout.flush()
            logger.info("✅ [AnimeTracker.cog_load] 任務啟動完成")
        
        except Exception as cog_load_error:
            import traceback
            error_msg = f"❌ [cog_load] 執行失敗: {cog_load_error}"
            print(f"[COG_LOAD_ERROR] {error_msg}", flush=True)
            print(f"[COG_LOAD_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
            logger.error(error_msg, exc_info=True)
            raise
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
            # ✅ check_new_anime 已移除
            
            if self.send_weekly_stats.is_running():
                self.send_weekly_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] send_weekly_stats 已停止")
            
            if self.refresh_weekly_schedule.is_running():
                self.refresh_weekly_schedule.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] refresh_weekly_schedule 已停止")
            
            if self.check_scheduled_push.is_running():
                self.check_scheduled_push.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] check_scheduled_push 已停止")

            if self.sync_episode_stats.is_running():
                self.sync_episode_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] sync_episode_stats 已停止")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.cog_unload] 任務停止失敗: {e}", exc_info=True)
        logger.info("=" * 50)
    
    async def _catchup_missed_pushes(self):
        """Bot 重啟時補推今天未發送的動畫（限 4 小時內）"""
        try:
            await self.bot.wait_until_ready()
            now = datetime.now(TW_TZ)
            today_schedule = self.db.get_today_schedule()
            if not today_schedule:
                return
            
            # 找出今天已過時刻但未推送的項目（2 分鐘前 ~ 4 小時前）
            missed = []
            for item in today_schedule:
                if item['pushed']:
                    continue
                try:
                    sched_dt = datetime.strptime(item['scheduled_time'], "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                    )
                    diff_min = (now - sched_dt).total_seconds() / 60
                    if 2 <= diff_min <= 240:  # 2 分鐘 ~ 4 小時前
                        missed.append(item)
                except Exception:
                    pass
            
            if not missed:
                return
            
            missed_times = sorted(set(item['scheduled_time'] for item in missed))
            logger.info(f"🔄 [_catchup_missed_pushes] 發現 {len(missed)} 筆未推送（{missed_times}），嘗試補推...")
            
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if not channel:
                logger.warning("⚠️ [_catchup_missed_pushes] 找不到推送頻道")
                return
            
            # 查詢 API 推送（一次即可，_check_and_send_anime 已做去重）
            earliest_time = missed_times[0]
            success = await self._check_and_send_anime(f"catchup/{earliest_time}", channel)
            
            # 無論成功與否，將所有過去時刻標記為已推送（避免無限重試）
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")
            day_of_week = (now.weekday() + 1) % 7 or 7
            for t in missed_times:
                self.db.mark_time_pushed(week_start_str, day_of_week, t)
            
            if success:
                logger.info(f"✅ [_catchup_missed_pushes] 補推成功，已標記 {missed_times}")
            else:
                logger.info(f"⏭️ [_catchup_missed_pushes] API 無新集或已推送過，已標記 {missed_times}")
        except Exception as e:
            logger.error(f"❌ [_catchup_missed_pushes] 失敗: {e}", exc_info=True)
    
    async def _init_weekly_schedule_if_empty(self):
        """如果本週的週表為空，立即從 API 拉取（解決首次部署/非禮拜天重啟問題）"""
        try:
            await self.bot.wait_until_ready()
            today_schedule = self.db.get_today_schedule()
            if today_schedule:
                logger.info(f"✅ [_init_weekly_schedule_if_empty] 週表已有 {len(today_schedule)} 筆，跳過")
                return
            
            logger.info("🔄 [_init_weekly_schedule_if_empty] 週表為空，立即從 API 拉取...")
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] 無法拉取時程表 API")
                return
            
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")
            
            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)
                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get('scheduleTime', '')
                        if scheduled_time:
                            schedule_data.append({
                                'day_of_week': day_of_week,
                                'scheduled_time': scheduled_time,
                                'anime_data': anime
                            })
            
            if schedule_data:
                self.db.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(f"✅ [_init_weekly_schedule_if_empty] 週表初始化完成: {len(schedule_data)} 筆")
            else:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] API 返回空時程表")
        except Exception as e:
            logger.error(f"❌ [_init_weekly_schedule_if_empty] 失敗: {e}", exc_info=True)
    
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
        """Cog 卸載時停止所有任務（只有這個定義生效，前一個同名 method 被此覆蓋）"""
        logger.info("=" * 50)
        logger.info("🛑 [AnimeTracker.cog_unload] cog_unload() 被調用")
        try:
            if self.send_weekly_stats.is_running():
                self.send_weekly_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] send_weekly_stats 已停止")

            if self.refresh_weekly_schedule.is_running():
                self.refresh_weekly_schedule.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] refresh_weekly_schedule 已停止")

            if self.check_scheduled_push.is_running():
                self.check_scheduled_push.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] check_scheduled_push 已停止")

            if self.sync_episode_stats.is_running():
                self.sync_episode_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] sync_episode_stats 已停止")

            # 清理舊版 scheduler（若有）
            if hasattr(self, 'scheduler') and self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                logger.info("✅ [AnimeTracker.cog_unload] Scheduler 已關閉")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.cog_unload] 任務停止失敗: {e}", exc_info=True)
        logger.info("=" * 50)
    
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
                    
                    # 篩選只取今天的動畫 - 支援多種 upTime 格式
                    today_dt = datetime.now(TW_TZ)
                    today_episodes = []
                    for ep in all_episodes:
                        if not isinstance(ep, dict):
                            continue
                        up = ep.get("upTime")
                        if not isinstance(up, str) or not up:
                            continue
                        matched = False
                        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d"):
                            try:
                                if fmt == "%m/%d":
                                    # 需補上年份
                                    parsed = datetime.strptime(f"{up}/{today_dt.year}", f"{fmt}/{today_dt.year}")
                                else:
                                    parsed = datetime.strptime(up, fmt)
                                if parsed.date() == today_dt.date():
                                    matched = True
                                    break
                            except ValueError:
                                continue
                        if matched:
                            today_episodes.append(ep)

                    logger.info(f"🔍 API fetch: 獲得 {len(all_episodes)} 集，其中今天的 {len(today_episodes)} 集")
                    return today_episodes
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
            return None

    def _extract_view_count_from_episode(self, episode: dict, default: int = 0) -> int:
        """
        直接從 index API (v3/index.php) 的 episode 物件中提取觀看/人氣數，
        不需額外調用 video.php。

        Bahamut API 的 `newAnime.popular` 陣列中的 episode 物件可能包含
        多個潛在的觀看數字段：popular, viewCount, counter, views, view_counter 等。

        Args:
            episode: index API 返回的單個 episode 字典
            default: 找不到時返回的預設值

        Returns:
            提取到的觀看數（int），否則返回 default
        """
        view_candidates = [
            "popular", "viewCount", "counter", "views",
            "view_counter", "page_views", "click", "playCount",
        ]
        for field in view_candidates:
            raw = episode.get(field)
            if raw is not None:
                try:
                    val = int(str(raw).replace(',', '').replace(',', ''))
                    if val > 0:
                        logger.info(f"📺 [_extract_view_count_from_episode] 從 field='{field}' 提取到觀看數: {val}")
                        return val
                    else:
                        logger.debug(f"📺 [_extract_view_count_from_episode] field='{field}' 值為 0，繼續嘗試其他字段")
                except (ValueError, TypeError):
                    continue

        # 若 episode 物件沒有直接的觀看數，但 structure 中有 highlightTag/meta 也可嘗試
        highlight = episode.get("highlightTag") or {}
        if isinstance(highlight, dict):
            for field in ["counter", "views", "popular"]:
                raw = highlight.get(field)
                if raw is not None:
                    try:
                        val = int(str(raw).replace(',', ''))
                        if val > 0:
                            logger.info(f"📺 [_extract_view_count_from_episode] 從 highlightTag.{field} 提取到觀看數: {val}")
                            return val
                    except (ValueError, TypeError):
                        continue

        logger.debug(f"📺 [_extract_view_count_from_episode] 無法從 episode(videoSn={episode.get('videoSn')}) 提取觀看數")
        return default

    async def _sync_episode_stats_from_api(self):
        """
        定時從 Bahamut index API 獲取最新的動畫列表，
        記錄 per-episode 統計數據到 episode_statistics 表，
        確保週排行有足夠的歷史數據。

        此方法獨立於新集通知流程，定期執行以累積數據。
        """
        try:
            episodes = await self.fetch_all_recent_anime_from_api()
            if not episodes:
                logger.warning("⚠️ [_sync_episode_stats_from_api] 無法獲取動畫數據")
                return

            recorded = 0
            for ep in episodes:
                video_sn = ep.get("videoSn")
                anime_sn = ep.get("animeSn")
                if not video_sn or not anime_sn:
                    continue

                # 提取觀看數
                views = self._extract_view_count_from_episode(ep)

                # 如果 index API 沒有觀看數，從 video.php 補充
                if views <= 0:
                    try:
                        details = await self.fetch_anime_details_from_api(video_sn)
                        if details:
                            views = details.get("popular", 0)
                    except Exception as e:
                        logger.warning(f"⚠️ [_sync_episode_stats_from_api] videoSn={video_sn} 詳情獲取失敗: {e}")
                        continue

                anime_name = ep.get("title", f"Anime #{anime_sn}")
                episode_num = ep.get("volume", "")

                # 記錄統計（INSERT OR REPLACE，以 videoSn 為主鍵）
                self.db.record_episode_stats(
                    video_sn=video_sn,
                    anime_sn=anime_sn,
                    episode_num=episode_num,
                    views=views,
                    score=0  # index API 不包含評分，預設 0
                )

                # 也快取 anime details（名稱等）
                if anime_sn:
                    existing = self.db.get_anime_details(int(anime_sn))
                    if not existing:
                        self.db.cache_anime_details(
                            int(anime_sn),
                            anime_name,
                            "",
                            [],
                            views,
                            0
                        )

                recorded += 1
                await asyncio.sleep(0.05)  # 避免限流

            logger.info(f"✅ [_sync_episode_stats_from_api] 完成，記錄了 {recorded}/{len(episodes)} 筆統計數據")

        except Exception as e:
            logger.error(f"❌ [_sync_episode_stats_from_api] 執行失敗: {e}", exc_info=True)

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
                    score = anime.get("score", 0)

                    # 嘗試多個可能的觀看數/人氣字段名（Bahamut API 可能使用不同名稱）
                    # 常見的 Bahamut 觀看次數字段：popular, viewCount, counter, views, view_counter, page_views
                    view_count = (
                        anime.get("popular", 0)
                        or anime.get("viewCount", 0)
                        or anime.get("counter", 0)
                        or anime.get("views", 0)
                        or anime.get("view_counter", 0)
                        or anime.get("page_views", 0)
                        or 0
                    )
                    # 確保是整數
                    if not isinstance(view_count, (int, float)):
                        try:
                            view_count = int(str(view_count).replace(',', ''))
                        except (ValueError, TypeError):
                            view_count = 0
                    view_count = int(view_count)

                    logger.info(f"✅ [fetch_anime_details_from_api] animeSn={anime_sn}, title={title[:30] if title else '(空)'}, tags={tags}, view_count={view_count}, score={score}")
                    logger.info(f"✅ [fetch_anime_details_from_api] 提取的觀看數: view_count={view_count}, type={type(view_count)}, anime.popular={anime.get('popular', 'N/A')}, anime.get('viewCount', 'N/A'), 全部鍵={list(anime.keys())}")

                    # 快取到數據庫
                    if anime_sn:
                        self.db.cache_anime_details(anime_sn, title, content, tags, view_count, score)
                        # 同時記錄統計數據（用於數據分析）
                        self.db.record_episode_stats(
                            video_sn=video_sn,
                            anime_sn=anime_sn,
                            episode_num=f"Ep. {anime.get('video_episode_number', '')}",
                            views=view_count,
                            score=score
                        )

                    return {
                        "anime_sn": anime_sn,
                        "title": title,
                        "content": content,
                        "tags": tags,
                        "popular": view_count,
                        "score": score,
                        "raw_keys": list(anime.keys()),  # 傳回原始鍵列表供調試
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
        
        # 人氣度和評分信息 - 改為以平均觀看人數為主
        # 嘗試獲取動畫統計信息（用於顯示平均數據）
        anime_stats = self.db.get_anime_statistics(int(anime_sn)) if anime_sn else None

        popularity_text = f"👥 {popular:,}" if popular else "👥 N/A"
        avg_views_text = (
            f"👥 {anime_stats['avg_views']:,.0f}" if anime_stats and anime_stats.get('avg_views') else "👥 N/A"
        )
        score_text = f"⭐ {score:.1f}" if score > 0 else "⭐ N/A"
        
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
        # 注意：popular 為系列人氣累計值（Bahamut API anime.popular），非單集獨立觀看數
        stats_lines = [
            f"**系列人氣**: {popularity_text} | {score_text} 評分"
        ]
        if anime_stats and anime_stats['total_episodes'] > 0:
            avg_views = anime_stats['avg_views']
            avg_score = anime_stats['avg_score']
            stats_lines.append(f"**本季均值**: 👥 {avg_views:,.0f} 人氣 | ⭐ {avg_score:.1f} 評分")
            stats_lines.append(f"**本季統計**: {anime_stats['total_episodes']} 集累積記錄")
        
        embed.add_field(
            name="📊 人氣數據",
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
    
    # ✅ check_new_anime 任務已刪除（2026-05-04）
    # 原因：新的週表系統 (refresh_weekly_schedule + check_scheduled_push) 已取代
    # 改進：API 呼叫從 288/天 → 1/週，節省 99.65% 流量
    
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
                try:
                    video_sn = ep.get("videoSn")
                    if video_sn and not self.db.is_notified(video_sn):
                        new_episodes.append(ep)
                except Exception as check_err:
                    logger.error(f"❌ [_check_and_send_anime] 檢查集 {ep.get('videoSn')} 時異常: {check_err}", exc_info=True)
                    continue
            
            if not new_episodes:
                logger.info(f"⏭️  [{scheduled_time_str}] 沒有新集")
                return False
            
            # 發送新集通知
            logger.info(f"🆕 [{scheduled_time_str}] 發現 {len(new_episodes)} 個新集，開始推播...")
            sent_count = 0
            
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
                    try:
                        self.db.save_message_info(
                            message_id=message.id,
                            video_sn=ep.get("videoSn"),
                            anime_sn=ep.get("animeSn"),
                            anime_name=ep.get("title", "Unknown"),
                            channel_id=channel.id
                        )
                        logger.info(f"💾 [_check_and_send_anime] 消息 ID 已保存到數據庫")
                    except Exception as db_save_err:
                        logger.error(f"❌ [_check_and_send_anime] 保存消息 ID 失敗: {db_save_err}", exc_info=True)
                        # 不中斷流程，消息已發送，只是記錄失敗
                    
                    # 記錄已通知
                    try:
                        self.db.add_notified(
                            video_sn=ep.get("videoSn"),
                            anime_sn=ep.get("animeSn"),
                            anime_name=ep.get("title", "Unknown"),
                            volume=ep.get("volume", ""),
                            cover_url=ep.get("cover", "")
                        )
                    except Exception as db_notify_err:
                        logger.error(f"❌ [_check_and_send_anime] 記錄已通知失敗: {db_notify_err}", exc_info=True)
                        # 不中斷流程，消息已發送，只是記錄失敗
                    
                    sent_count += 1
                    # 避免 Discord 限流
                    await asyncio.sleep(0.2)
                    
                except Exception as send_err:
                    logger.error(f"❌ [_check_and_send_anime] 發送集異常 (video_sn={ep.get('videoSn')}): {send_err}", exc_info=True)
                    await asyncio.sleep(1)
                    continue  # 繼續發送其他集
            
            logger.info(f"✅ [{scheduled_time_str}] 推播完成 (發送 {sent_count}/{len(new_episodes)} 集)")
            return sent_count > 0
        
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
        """取得今天和明天的所有預期檢查時刻
        
        修復: 移除 1 小時過濾，改用日期過濾，防止凌晨時同日時刻被篩除
        例如: 凌晨 03:59 時 01:00 不應被過濾
        """
        check_times = []
        weekday_today = (now.weekday() + 1) % 7 or 7
        weekday_tomorrow = (weekday_today % 7) + 1
        
        for day_offset, weekday in [(0, str(weekday_today)), (1, str(weekday_tomorrow))]:
            target_date = (now + timedelta(days=day_offset)).date()
            for anime_info in schedule.get(weekday, []):
                schedule_time = anime_info.get("scheduleTime", "")
                if schedule_time:
                    try:
                        scheduled_time = datetime.strptime(schedule_time, "%H:%M").time()
                        scheduled_dt = datetime.combine(target_date, scheduled_time, tzinfo=TW_TZ)
                        # ✅ 改用日期過濾：超過 1 天的時刻才篩除，同日所有時刻都保留
                        # 這防止凌晨時早晨時刻被篩除（例如: 凌晨 03:59 時 01:00 不應被篩除）
                        if scheduled_dt.date() >= (now - timedelta(days=1)).date():
                            check_times.append(scheduled_dt)
                    except:
                        pass
        
        return sorted(check_times)
    

    
    @tasks.loop(hours=1)
    async def send_weekly_stats(self):
        """自動發送週統計 - 每週天 台灣時間 23:00 發送"""
        now = datetime.now(TW_TZ)
        
        try:
            # 檢查是否是禮拜天且時間在晚上 23:00-23:59
            is_sunday = now.weekday() == 6  # 6 = Sunday
            is_send_time = now.hour == 23  # 台灣時間 23:00-23:59
            
            # 檢查是否已在本週發送過（防止重複）
            week_start = now - timedelta(days=now.weekday())
            week_start_date = week_start.date()
            
            if is_sunday and is_send_time and self.last_weekly_stats_sent != week_start_date:
                logger.info(f"📊 [send_weekly_stats] 禮拜天時間到，準備發送週統計...")
                
                # 獲取頻道
                channel = self.bot.get_channel(ANIME_CHANNEL_ID)
                if not channel:
                    logger.error(f"❌ [send_weekly_stats] 找不到頻道 {ANIME_CHANNEL_ID}")
                    return
                
                week_start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
                week_end_dt = week_start_dt + timedelta(days=7)
                week_end = week_end_dt - timedelta(seconds=1)
                week_start_str = week_start_dt.strftime("%m/%d")
                week_end_str = week_end.strftime("%m/%d")

                # 獲取週統計數據
                weekly_stats = self.db.get_weekly_vote_stats()

                if weekly_stats:
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

                    # 發送投票統計
                    await channel.send(embed=embed)
                    logger.info(f"✅ [send_weekly_stats] 週投票統計已發送: {unique_animes} 部作品, {total_all_votes} 投票")
                else:
                    logger.info("📊 [send_weekly_stats] 本週無投票數據，僅發送觀看排行")
                
                # 發送觀看量趨勢折線圖（改進：按集數累計顯示）
                try:
                    ranking_embed = await self.generate_ranking_embed(
                        start_time=week_start_dt,
                        end_time=week_end_dt,
                        period_label="本週"
                    )
                    if ranking_embed:
                        await channel.send(embed=ranking_embed)
                        logger.info("✅ [send_weekly_stats] 集數累計觀看趨勢圖已發送")
                    else:
                        logger.info("⚠️ [send_weekly_stats] 無足夠集數數據生成趨勢圖，跳過")
                except Exception as chart_err:
                    logger.warning(f"⚠️ [send_weekly_stats] 趨勢圖生成失敗（不影響投票統計）: {chart_err}")
                
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
    
    @send_weekly_stats.error
    async def send_weekly_stats_error(self, error):
        """處理 send_weekly_stats 任務的異常"""
        logger.error(f"❌ [send_weekly_stats] 任務異常: {error}", exc_info=True)
        logger.warning(f"⚠️ [send_weekly_stats] 嘗試重啟任務...")
        
        # 短暫延遲後重新啟動任務
        try:
            await asyncio.sleep(5)
            if not self.send_weekly_stats.is_running():
                logger.info(f"🔄 [send_weekly_stats] 重新啟動任務...")
                self.send_weekly_stats.restart()
                logger.info(f"✅ [send_weekly_stats] 任務已重新啟動")
        except Exception as restart_error:
            logger.error(f"❌ [send_weekly_stats] 重啟失敗: {restart_error}", exc_info=True)

    @tasks.loop(hours=6)
    async def sync_episode_stats(self):
        """
        每 6 小時從 Bahamut index API 同步一次 episode 統計數據，
        確保 episode_statistics 表有足夠的觀看數歷史資料，
        讓週日排行功能能正確顯示觀看人數成長。

        獨立於新集通知流程，避免"只有發通知才有統計"的問題。
        """
        try:
            now = datetime.now(TW_TZ)
            # 避開凌晨時段（2-5點 API 可能維護中）和整點高峰
            skip_hours = {2, 3, 4, 5}
            if now.hour in skip_hours:
                logger.debug(f"⏭️ [sync_episode_stats] 跳過維護時段（{now.hour}:00）")
                return

            logger.info(f"🔄 [sync_episode_stats] 開始同步 episode 統計數據...")
            await self._sync_episode_stats_from_api()
            logger.info(f"✅ [sync_episode_stats] 同步完成")

        except Exception as e:
            logger.error(f"❌ [sync_episode_stats] 同步失敗: {e}", exc_info=True)

    @sync_episode_stats.before_loop
    async def before_sync_episode_stats(self):
        """等待 bot 就緒"""
        logger.info("📊 [before_sync_episode_stats] 等待 bot 就緒...")
        await self.bot.wait_until_ready()
        logger.info("✅ [before_sync_episode_stats] 統計同步任務準備就緒")

    @sync_episode_stats.error
    async def sync_episode_stats_error(self, error):
        """處理任務異常"""
        logger.error(f"❌ [sync_episode_stats] 任務異常: {error}", exc_info=True)

    @tasks.loop(hours=24)
    async def refresh_weekly_schedule(self):
        """禮拜天晚上 10 點自動拉取完整週表 - 優化 API 調用（288/天 → 1/週）"""
        now = datetime.now(TW_TZ)
        
        try:
            # 檢查是否是禮拜天晚上 22:00
            is_sunday = now.weekday() == 6  # 6 = Sunday
            is_refresh_time = now.hour == 22  # 台灣時間 22:00-22:59
            
            if not (is_sunday and is_refresh_time):
                # 非禮拜天或非晚上 10 點，跳過
                logger.debug(f"⏭️ [refresh_weekly_schedule] 跳過（非禮拜天晚上 10 點）")
                return
            
            logger.info("🔄 [refresh_weekly_schedule] 開始拉取本週時程表...")
            
            # 拉取完整一週的時程表
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [refresh_weekly_schedule] 無法拉取時程表")
                return
            
            # 構建下週的完整時程（在禮拜天晚上為下週一開始的那週）
            # Bug fix: 禮拜天時 now.weekday()=6，若用 now - 6 days = 上週一
            # 但我們應存為「下週一」，因為 get_today_schedule() 在週一查詢時
            # 會用「本週一」作為 week_start，所以需要提前存好下週的資料
            week_start = now - timedelta(days=now.weekday()) + timedelta(weeks=1)
            week_start_str = week_start.strftime("%Y-%m-%d")
            logger.info(f"📅 [refresh_weekly_schedule] 將保存為下週起始: {week_start_str}")
            
            schedule_data = []
            for day_offset in range(7):
                target_date = week_start + timedelta(days=day_offset)
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)
                
                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get('scheduleTime', '')
                        if scheduled_time:
                            schedule_data.append({
                                'day_of_week': day_of_week,
                                'scheduled_time': scheduled_time,
                                'anime_data': anime
                            })
            
            # 保存到數據庫
            if schedule_data:
                self.db.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(f"✅ [refresh_weekly_schedule] 本週時程表已保存 ({len(schedule_data)} 個時刻)")
            else:
                logger.warning("⚠️ [refresh_weekly_schedule] 時程表為空")
        
        except Exception as e:
            logger.error(f"❌ [refresh_weekly_schedule] 失敗: {e}", exc_info=True)
    
    @refresh_weekly_schedule.before_loop
    async def before_refresh_weekly_schedule(self):
        """等待 bot 就緒"""
        logger.info("📅 [before_refresh_weekly_schedule] 等待 bot 就緒...")
        await self.bot.wait_until_ready()
        logger.info("✅ [before_refresh_weekly_schedule] 週表刷新任務準備就緒")
    
    @refresh_weekly_schedule.error
    async def refresh_weekly_schedule_error(self, error):
        """處理任務異常"""
        logger.error(f"❌ [refresh_weekly_schedule] 任務異常: {error}", exc_info=True)
    
    @tasks.loop(minutes=30)
    async def check_scheduled_push(self):
        """每分鐘檢查是否有預定推送時刻 - 供週表系統使用"""
        now = datetime.now(TW_TZ)
        current_time = now.strftime("%H:%M")
        
        try:
            # 獲取今天的時程表
            today_schedule = self.db.get_today_schedule()
            if not today_schedule:
                # 週表為空時的回退機制：每整點嘗試直接查詢 API
                if now.minute == 0:
                    logger.info(f"⚠️ [check_scheduled_push] 週表為空，整點回退模式查詢 API ({current_time})")
                    channel = self.bot.get_channel(ANIME_CHANNEL_ID)
                    if channel:
                        await self._check_and_send_anime(current_time, channel)
                return
            
            # 尋找符合現在時刻的項目（尚未推送的）
            # 同時支援補推機制：30 分鐘內的未推送項目（防止 bot 重啟錯過時刻）
            catchup_minutes = 30
            matching = []
            for item in today_schedule:
                if item['pushed']:
                    continue
                scheduled = item['scheduled_time']
                try:
                    sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                    )
                    diff = (now - sched_dt).total_seconds()
                    # 精確時刻 OR 在 catchup 窗口內（剛過去 0~15 分鐘）
                    if 0 <= diff < catchup_minutes * 60:
                        matching.append(item)
                except Exception:
                    pass
            
            if matching:
                # 只取最早那個時刻的推送（避免補推時一次推很多）
                earliest_time = min(item['scheduled_time'] for item in matching)
                logger.info(f"📺 [check_scheduled_push] 推送時刻: {earliest_time}（現在 {current_time}，共 {len(matching)} 部）")
                await self.send_anime_push(earliest_time, ANIME_CHANNEL_ID)
        
        except Exception as e:
            logger.error(f"❌ [check_scheduled_push] 失敗: {e}", exc_info=True)
    
    @check_scheduled_push.before_loop
    async def before_check_scheduled_push(self):
        """等待 bot 就緒"""
        await self.bot.wait_until_ready()
    
    @check_scheduled_push.error
    async def check_scheduled_push_error(self, error):
        """處理任務異常"""
        logger.error(f"❌ [check_scheduled_push] 任務異常: {error}", exc_info=True)

    # ✅ anime_test 指令已刪除 - 邏輯改為自動推送
    
    # ✅ anime_weekly 指令已刪除 - 邏輯已轉換為 generate_weekly_stats_embed() 供自動推送使用
    
    async def send_anime_push(self, scheduled_time: str, channel_id: int = ANIME_CHANNEL_ID):
        """在預定時刻推送動畫通知 - 查詢真實 API 確認已上架集
        
        Args:
            scheduled_time: 預定時刻，格式 "HH:MM"
            channel_id: Discord 頻道 ID
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"❌ [send_anime_push] 頻道 {channel_id} 未找到")
                return
            
            logger.info(f"📺 [send_anime_push] 時刻 {scheduled_time} 觸發，查詢 API 確認已上架集...")
            
            # 使用 _check_and_send_anime 查詢真實 API（包含正確的 videoSn，支援去重）
            success = await self._check_and_send_anime(scheduled_time, channel)
            
            if success:
                # 標記週表中該時刻已推送
                now = datetime.now(TW_TZ)
                week_start = now - timedelta(days=now.weekday())
                day_of_week = (now.weekday() + 1) % 7 or 7
                self.db.mark_time_pushed(
                    week_start.strftime("%Y-%m-%d"),
                    day_of_week,
                    scheduled_time
                )
                logger.info(f"✅ [send_anime_push] 時刻 {scheduled_time} 推送完成，週表已標記")
            else:
                logger.info(f"⏭️ [send_anime_push] 時刻 {scheduled_time} 無新集（可能尚未上架或已推送過）")
        
        except Exception as e:
            logger.error(f"❌ [send_anime_push] 執行失敗: {e}", exc_info=True)
    
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
    
    async def generate_ranking_embed(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        period_label: str = "本季"
    ) -> discord.Embed:
        """生成動畫觀看排行榜 embed（供自動推送使用）"""
        try:
            
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
                    logger.info("✅ [generate_ranking_embed] 確保 episode_statistics 表存在")
            except Exception as e:
                logger.warning(f"⚠️ [generate_ranking_embed] 表初始化失敗: {e}")
            
            # 先嘗試從数據庫取歷史統計數據
            top_anime = self.db.get_top_anime_by_views(
                limit=10,
                start_time=start_time,
                end_time=end_time
            )

            # 修復：如果 DB 沒有數據（不論是否有時間篩選），都試從 API 獲取
            # 原先的條件 `if not top_anime and not start_time and not end_time` 會導致
            # 當 send_weekly_stats 傳入 start_time/end_time 時，API 回退永遠不會被觸發
            if not top_anime:
                logger.info(f"📺 [generate_ranking_embed] 數據庫無歷史數據{'（含時間篩選）' if start_time or end_time else ''}，改為實時從 API 獲取")
                episodes = await self.fetch_all_recent_anime_from_api()

                if not episodes:
                    logger.warning("📺 [generate_ranking_embed] 無法獲取動畫數據")
                    return None

                # 按觀看人數排序
                anime_list = {}
                for ep in episodes:
                    anime_sn = ep.get("animeSn")
                    if not anime_sn:
                        continue

                    anime_name = ep.get("title", f"Anime #{anime_sn}")
                    views = 0

                    # 優先從 index API 直接提取觀看數（省去額外 API 調用）
                    views = self._extract_view_count_from_episode(ep)

                    # 如果 index API 沒有觀看數，調用 video.php 獲取詳細數據
                    if views <= 0:
                        try:
                            video_sn = ep.get("videoSn")
                            if video_sn:
                                details = await self.fetch_anime_details_from_api(video_sn)
                                if details:
                                    views = details.get("popular", 0)
                                    # 使用 API 返回的正確動畫名稱
                                    if details.get("title"):
                                        anime_name = details.get("title")
                                        logger.info(f"📺 [generate_ranking_embed] 獲得動畫名稱: {anime_name} (animeSn={anime_sn})")
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
                    else:
                        # 即使 views=0 也統計集數（但用 0 計算總觀看數）
                        anime_list[anime_sn]["episodes"].append(views)
                        anime_list[anime_sn]["total_episodes"] += 1

                # 轉換為排行格式並按總觀看數排序
                top_anime = []
                for anime_sn, data in anime_list.items():
                    if data["total_episodes"] > 0:
                        logger.info(f"📺 [generate_ranking_embed] 排行動畫: {data['name']} (animeSn={anime_sn}, views={data['total_views']})")
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
                    logger.info("📺 [generate_ranking_embed] 無有效的動畫數據")
                    return None

                logger.info(f"📺 [generate_ranking_embed] 實時獲取了 {len(top_anime)} 部動畫的數據")
            
            # 嘗試獲取有多集的動畫數據（用於多線圖）
            # 改進：增加 limit 到 15，降低 min_episodes 到 1，讓更多動畫納入統計
            multi_anime = self.db.get_multi_episode_anime_for_chart(
                limit=10,
                min_episodes=1,
                start_time=start_time,
                end_time=end_time
            )
            logger.info(f"📺 [generate_ranking_embed] 查詢 multi_anime 結果: {len(multi_anime) if multi_anime else 0} 部動畫")
            if multi_anime:
                for i, anime in enumerate(multi_anime[:5]):  # 顯示前 5 部的詳細資訊
                    logger.info(f"  📺 [{i+1}] {anime['name']}: {len(anime['episodes'])} 集, {anime['total_views']} 次觀看")

            ranked_chart_anime = []
            if multi_anime:
                multi_anime_by_sn = {anime['anime_sn']: anime for anime in multi_anime}
                ranked_chart_anime = [
                    multi_anime_by_sn[anime['anime_sn']]
                    for anime in top_anime
                    if anime['anime_sn'] in multi_anime_by_sn
                ]
            
            embed = discord.Embed(
                title=f"🏆 {period_label}動畫觀看排行",
                color=discord.Color.gold(),
                timestamp=datetime.now(TW_TZ)
            )

            period_text = None
            if start_time and end_time:
                period_text = f"{start_time.strftime('%m/%d')} - {(end_time - timedelta(seconds=1)).strftime('%m/%d')}"

            rank_emojis = ["🥇", "🥈", "🥉"]
            ranking_lines = []
            for idx, anime in enumerate(top_anime, 1):
                anime_name = anime.get('name', f"Anime #{anime.get('anime_sn', '?')}").strip()
                display_name = anime_name if len(anime_name) <= 22 else f"{anime_name[:22]}..."
                rank_prefix = rank_emojis[idx - 1] if idx <= len(rank_emojis) else f"#{idx}"
                ranking_lines.append(
                    f"{rank_prefix} **{display_name}** - {anime['total_views']:,} 次 | {anime['total_episodes']} 集"
                )

            ranking_summary = "\n".join(ranking_lines) if ranking_lines else "本期尚無足夠觀看數據"
            
            # 如果有多集數據，生成多線趨勢圖；否則使用單線聚合圖
            if ranked_chart_anime and len(ranked_chart_anime) >= 2:
                # ===== 模式 A：多線趨勢圖（每部動畫一條線）=====
                if period_text:
                    embed.description = f"**統計週期**: {period_text}\n依總觀看數排名，折線圖只顯示實際上榜作品的集數累計趨勢"
                else:
                    embed.description = "依總觀看數排名，折線圖只顯示實際上榜作品的集數累計趨勢"
                
                # 構建多線圖表
                datasets = []
                
                # 顏色數組（10 種顏色）
                colors = [
                    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
                    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#ABEBC6"
                ]
                
                # 找出所有集數編號（X 軸）- 改進標準化處理
                all_episodes = set()
                for anime in ranked_chart_anime:
                    for ep in anime['episodes']:
                        ep_num = ep['num']
                        # 標準化集數格式：提取數字部分
                        if isinstance(ep_num, str):
                            # 提取數字（如 "第1集" -> 1, "EP.1" -> 1）
                            import re
                            numbers = re.findall(r'\d+', ep_num)
                            if numbers:
                                ep_num = int(numbers[0])
                            else:
                                continue
                        elif isinstance(ep_num, (int, float)):
                            ep_num = int(ep_num)
                        else:
                            continue
                        
                        all_episodes.add(ep_num)
                
                # 排序並生成標籤（使用更清楚的集數格式）
                episode_labels = [f"第{ep}集" for ep in sorted(list(all_episodes))]
                
                # 為每部動畫建立一條線
                for idx, anime in enumerate(ranked_chart_anime):
                    name = anime['name'][:12]  # 增加到 12 個字以便識別
                    color = colors[idx % len(colors)]
                    
                    # 建立該動畫的數據點（缺失集用 None）- 配合新標籤格式
                    ep_dict = {}
                    for ep in anime['episodes']:
                        # 標準化集數格式以匹配 episode_labels ("第X集")
                        ep_num = ep['num']
                        if isinstance(ep_num, str):
                            import re
                            numbers = re.findall(r'\d+', ep_num)
                            if numbers:
                                ep_num = f"第{int(numbers[0])}集"
                            else:
                                continue
                        elif isinstance(ep_num, (int, float)):
                            ep_num = f"第{int(ep_num)}集"
                        else:
                            continue
                        
                        ep_dict[ep_num] = ep['views']
                    
                    data = [ep_dict.get(label) for label in episode_labels]
                    
                    # 改進：處理累計觀看數（如果需要顯示累計趨勢）
                    cumulative_data = []
                    cumulative_sum = 0
                    for views in data:
                        if views is not None:
                            cumulative_sum += views
                        cumulative_data.append(cumulative_sum if cumulative_sum > 0 else None)
                    
                    datasets.append({
                        "label": name,
                        "data": cumulative_data,  # 使用累計數據顯示成長趨勢
                        "borderColor": color,
                        "fill": False,
                        "showLine": True,
                        "tension": 0.1  # 添加輕微的曲線效果
                    })
                
                # 構建圖表配置（改進版 - 適合集數累計觀看數顯示）
                try:
                    chart_config = {
                        "type": "line",
                        "data": {
                            "labels": episode_labels,
                            "datasets": datasets
                        },
                        "options": {
                            "responsive": True,
                            "plugins": {
                                "legend": {"position": "top"},
                                "title": {
                                    "display": True,
                                    "text": "動畫集數累計觀看數趨勢"
                                }
                            },
                            "scales": {
                                "x": {
                                    "title": {
                                        "display": True,
                                        "text": "集數"
                                    }
                                },
                                "y": {
                                    "title": {
                                        "display": True,
                                        "text": "累計觀看數"
                                    },
                                    "beginAtZero": True
                                }
                            }
                        }
                    }
                    
                    # 嘗試使用短 URL API，失敗則改用直接 URL
                    short_url = await self.get_short_chart_url(chart_config)
                    if short_url:
                        chart_url = short_url
                        logger.info(f"✅ [generate_ranking_embed] 多線趨勢圖短 URL 已取得")
                    else:
                        # 改用直接 URL（只要長度不超過 2048）
                        config_json = json.dumps(chart_config, separators=(',', ':'), ensure_ascii=False)
                        encoded = quote(config_json)
                        chart_url = f"https://quickchart.io/chart?bkg=white&w=950&h=400&c={encoded}"
                        
                        logger.info(f"📺 [generate_ranking_embed] 直接 URL 長度: {len(chart_url)}")
                        
                        if len(chart_url) > 2048:
                            logger.warning(f"⚠️ [generate_ranking_embed] URL {len(chart_url)} 字元超過限制，改用文字顯示")
                            ranked_chart_anime = []  # 改用模式 B
                            chart_url = None
                    
                    # 直接使用圖表 URL
                    if chart_url:
                        embed.set_image(url=chart_url)
                        logger.info(f"✅ [generate_ranking_embed] 多線趨勢圖已設置")
                    
                    embed.add_field(
                        name="📋 排行名單",
                        value=ranking_summary,
                        inline=False
                    )
                except Exception as e:
                    logger.warning(f"⚠️ [generate_ranking_embed] 生成多線圖失敗: {e}，改用文字顯示")
                    ranked_chart_anime = []  # 改用模式 B
            
            # === 模式 B：文字排行列表（當無多集數據或圖表生成失敗）===
            if not ranked_chart_anime or len(ranked_chart_anime) < 2:
                if period_text:
                    embed.description = f"**統計週期**: {period_text}\n前 {len(top_anime)} 名觀看排行"
                else:
                    embed.description = f"前 {len(top_anime)} 名觀看排行"
                
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
                        logger.info(f"📺 [generate_ranking_embed] 單線聚合圖 URL 已設置 (長度: {len(chart_url)})")
                except Exception as e:
                    logger.warning(f"⚠️ [generate_ranking_embed] 生成單線圖 URL 失敗: {e}")
                
                embed.add_field(
                    name="📋 排行名單",
                    value=ranking_summary,
                    inline=False
                )
            
            embed.set_footer(text="📊 排行與集數觀看趨勢" if ranked_chart_anime and len(ranked_chart_anime) >= 2 else "📈 觀看排行")
            
            logger.info(f"📺 [generate_ranking_embed] 排行榜已生成（模式: {'多線趨勢' if ranked_chart_anime and len(ranked_chart_anime) >= 2 else '聚合排行'}）")
            return embed
        except Exception as e:
            logger.error(f"❌ [generate_ranking_embed] 生成失敗: {e}", exc_info=True)
            return None
    
    # ✅ anime_stats 指令已刪除 - 邏輯改為自動推送
    

async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式 - cog_load() 會自動被調用"""
    import sys
    print("[SETUP_START] 🎬 AnimeTracker setup() 開始", flush=True)
    sys.stdout.flush()
    
    try:
        cog = AnimeTracker(bot)
        await bot.add_cog(cog)
        logger.info("✅ AnimeTracker Cog 已加載（任務將在 cog_load() 中啟動）")
        print("[SETUP_END] 🎬 AnimeTracker setup() 完成 - cog_load() 將自動被調用", flush=True)
        sys.stdout.flush()
    except Exception as setup_err:
        import traceback
        error_msg = f"❌ [setup] AnimeTracker setup() 失敗: {setup_err}"
        print(f"[SETUP_ERROR] {error_msg}", flush=True)
        print(f"[SETUP_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
        logger.error(error_msg, exc_info=True)
        raise
