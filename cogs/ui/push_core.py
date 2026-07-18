"""
Bahamut 動畫追蹤 - Push/Core 模組
負責通知發送、嵌入生成、視圖管理、訊息持久化
"""

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
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from zoneinfo import ZoneInfo  # Python 3.9+, 正確的時區處理
import time

logger = logging.getLogger(__name__)
from urllib.parse import quote
from shared.utils.view_registry import PersistentViewBase

# 台灣時區
TW_TZ = ZoneInfo('Asia/Taipei')

# 配置
ANIME_CHANNEL_ID = 1252204317453324333  # 動畫通知頻道
ANIME_DB_PATH = None  # 將在初始化時設置
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
    """資料庫管理類別 - 負責所有資料庫操作"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """初始化資料庫表格"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 已通知的動畫表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {NOTIFIED_TABLE} (
                    videoSn INTEGER PRIMARY KEY,
                    animeSn INTEGER,
                    animeName TEXT,
                    volume TEXT,
                    coverUrl TEXT,
                    notifiedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 啟動旗標表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {BOOTSTRAP_FLAG_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bootstrapCompleted INTEGER DEFAULT 0,
                    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 動畫詳細資訊快取表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_DETAILS_TABLE} (
                    animeSn INTEGER PRIMARY KEY,
                    name TEXT,
                    content TEXT,
                    coverUrl TEXT,
                    tags TEXT,  -- JSON 字串
                    viewCount INTEGER DEFAULT 0,
                    score REAL DEFAULT 0,
                    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 動畫統計表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_STATS_TABLE} (
                    animeSn INTEGER PRIMARY KEY,
                    name TEXT,
                    totalEpisodes INTEGER DEFAULT 0,
                    totalViews INTEGER DEFAULT 0,
                    avgViews REAL DEFAULT 0,
                    latestScore REAL DEFAULT 0,
                    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 集數統計表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {EPISODE_STATS_TABLE} (
                    videoSn INTEGER PRIMARY KEY,
                    animeSn INTEGER,
                    episodeNum TEXT,
                    views INTEGER,
                    score REAL DEFAULT 0,
                    recordedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 消息 ID 追蹤表（用於 bot 重啟時恢復 view）
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_MESSAGES_TABLE} (
                    messageId INTEGER PRIMARY KEY,
                    videoSn INTEGER,
                    animeSn INTEGER,
                    animeName TEXT,
                    channelId INTEGER,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 匿名投票結果表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_VOTES_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    videoSn INTEGER,
                    animeSn INTEGER,
                    animeName TEXT,
                    voteType TEXT,  -- 'masterpiece', 'great', 'good', 'average', 'bad'
                    userId TEXT,    -- 匿名用戶識別符（實際不存儲真實 ID）
                    votedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # KK幣獎勵追踪表（防止重複發放）
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_REWARDS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    messageId INTEGER,  -- 對應 anime_messages 表
                    rewardType TEXT,    -- 'vote' 或 'comment'
                    amount INTEGER,      -- KK幣金額
                    userId TEXT,        -- 匿名用戶識別符
                    rewardedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 每日時刻檢查歷史表（防止重複檢查，解決 Bot 重啟問題）
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_CHECK_HISTORY_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    weekStartDate TEXT,  -- YYYY-MM-DD 格式
                    dayOfWeek INTEGER,   -- 1=Monday, 7=Sunday
                    scheduledTime TEXT,   -- HH:MM 格式
                    checkedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 週表：每週一自動拉取的完整時程表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_WEEKLY_SCHEDULE_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    weekStartDate TEXT,  -- YYYY-MM-DD 格式 (週一日期)
                    dayOfWeek INTEGER,   -- 1=Monday, 7=Sunday
                    scheduledTime TEXT,   -- HH:MM 格式
                    animeData TEXT,       -- JSON 字串，存儲完整的動畫資料
                    pushed INTEGER DEFAULT 0,  -- 0=未推送, 1=已推送
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Schema migration: add missing columns to existing tables (must run before creating indexes)
            self._migrate_schema(cursor)

            # 創建索引以提高查詢性能 (in _migrate_schema 之後，確保欄位已存在)
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{NOTIFIED_TABLE}_videoSn ON {NOTIFIED_TABLE}(videoSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_DETAILS_TABLE}_animeSn ON {ANIME_DETAILS_TABLE}(animeSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{EPISODE_STATS_TABLE}_videoSn ON {EPISODE_STATS_TABLE}(videoSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_videoSn ON {ANIME_MESSAGES_TABLE}(videoSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_animeSn ON {ANIME_MESSAGES_TABLE}(animeSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_WEEKLY_SCHEDULE_TABLE}_weekStart ON {ANIME_WEEKLY_SCHEDULE_TABLE}(weekStartDate)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_WEEKLY_SCHEDULE_TABLE}_dayTime ON {ANIME_WEEKLY_SCHEDULE_TABLE}(dayOfWeek, scheduledTime)")

            conn.commit()

    def _migrate_schema(self, cursor):
        """Add missing columns to existing tables (schema migration)"""
        migrations = [
            # (table_name, column_name, column_definition)
            (NOTIFIED_TABLE, "videoSn", "INTEGER PRIMARY KEY"),
            (NOTIFIED_TABLE, "animeSn", "INTEGER"),
            (NOTIFIED_TABLE, "animeName", "TEXT"),
            (NOTIFIED_TABLE, "volume", "TEXT"),
            (NOTIFIED_TABLE, "coverUrl", "TEXT"),
            (NOTIFIED_TABLE, "notifiedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_MESSAGES_TABLE, "messageId", "INTEGER PRIMARY KEY"),
            (ANIME_MESSAGES_TABLE, "videoSn", "INTEGER"),
            (ANIME_MESSAGES_TABLE, "animeSn", "INTEGER"),
            (ANIME_MESSAGES_TABLE, "animeName", "TEXT"),
            (ANIME_MESSAGES_TABLE, "channelId", "INTEGER"),
            (ANIME_MESSAGES_TABLE, "createdAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (EPISODE_STATS_TABLE, "videoSn", "INTEGER PRIMARY KEY"),
            (EPISODE_STATS_TABLE, "animeSn", "INTEGER"),
            (EPISODE_STATS_TABLE, "episodeNum", "TEXT"),
            (EPISODE_STATS_TABLE, "views", "INTEGER"),
            (EPISODE_STATS_TABLE, "score", "REAL DEFAULT 0"),
            (EPISODE_STATS_TABLE, "recordedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_VOTES_TABLE, "id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            (ANIME_VOTES_TABLE, "videoSn", "INTEGER"),
            (ANIME_VOTES_TABLE, "animeSn", "INTEGER"),
            (ANIME_VOTES_TABLE, "animeName", "TEXT"),
            (ANIME_VOTES_TABLE, "voteType", "TEXT"),
            (ANIME_VOTES_TABLE, "userId", "TEXT"),
            (ANIME_VOTES_TABLE, "votedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_REWARDS_TABLE, "id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            (ANIME_REWARDS_TABLE, "messageId", "INTEGER"),
            (ANIME_REWARDS_TABLE, "rewardType", "TEXT"),
            (ANIME_REWARDS_TABLE, "amount", "INTEGER"),
            (ANIME_REWARDS_TABLE, "userId", "TEXT"),
            (ANIME_REWARDS_TABLE, "rewardedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_CHECK_HISTORY_TABLE, "id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            (ANIME_CHECK_HISTORY_TABLE, "weekStartDate", "TEXT"),
            (ANIME_CHECK_HISTORY_TABLE, "dayOfWeek", "INTEGER"),
            (ANIME_CHECK_HISTORY_TABLE, "scheduledTime", "TEXT"),
            (ANIME_CHECK_HISTORY_TABLE, "checkedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "weekStartDate", "TEXT"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "dayOfWeek", "INTEGER"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "scheduledTime", "TEXT"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "animeData", "TEXT"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "pushed", "INTEGER DEFAULT 0"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "createdAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (BOOTSTRAP_FLAG_TABLE, "id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            (BOOTSTRAP_FLAG_TABLE, "bootstrapCompleted", "INTEGER DEFAULT 0"),
            (BOOTSTRAP_FLAG_TABLE, "updatedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ]

        for table_name, column_name, column_def in migrations:
            try:
                # Check if column exists
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [row[1] for row in cursor.fetchall()]
                if column_name not in columns:
                    print(f"[Migration] Adding column {column_name} to {table_name}")
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            except Exception as e:
                print(f"[Migration] Warning: Could not add {column_name} to {table_name}: {e}")

    # ==================== 通知相關方法 ====================

    def is_notified(self, video_sn: int) -> bool:
        """檢查動畫集數是否已經通知過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {NOTIFIED_TABLE}
                    WHERE videoSn = ?
                """, (video_sn,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ [is_notified] Error checking video_sn {video_sn}: {e}", exc_info=True)
            return False

    def save_message_info(self, message_id: int, video_sn: int, anime_sn: int,
                         anime_name: str, channel_id: int) -> bool:
        """保存消息資訊"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_MESSAGES_TABLE}
                    (messageId, videoSn, animeSn, animeName, channelId)
                    VALUES (?, ?, ?, ?, ?)
                """, (message_id, video_sn, anime_sn, anime_name, channel_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [save_message_info] Error saving message_id {message_id}: {e}", exc_info=True)
            return False

    def add_notified(self, video_sn: int, anime_sn: int, anime_name: str,
                    volume: str = "", cover_url: str = "") -> bool:
        """記錄已通知的動畫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {NOTIFIED_TABLE}
                    (videoSn, animeSn, animeName, volume, coverUrl)
                    VALUES (?, ?, ?, ?, ?)
                """, (video_sn, anime_sn, anime_name, volume, cover_url))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [add_notified] Error adding video_sn {video_sn}: {e}", exc_info=True)
            return False

    def get_unviewed_messages(self) -> list:
        """獲取未設置視圖的消息（用於 bot 重啟時恢復）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT messageId, videoSn, animeSn, animeName, channelId
                    FROM {ANIME_MESSAGES_TABLE}
                """)
                rows = cursor.fetchall()
                return [{
                    'message_id': row[0],
                    'video_sn': row[1],
                    'anime_sn': row[2],
                    'anime_name': row[3],
                    'channel_id': row[4]
                } for row in rows]
        except Exception as e:
            logger.error(f"❌ [get_unviewed_messages] Error: {e}", exc_info=True)
            return []

    # ==================== 週表相關方法 ====================

    def save_weekly_schedule(self, week_start_date: str, schedule_data: list) -> bool:
        """保存週表數據"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 先清除舊的週資料（同一週開始日期）
                cursor.execute(f"""
                    DELETE FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE weekStartDate = ?
                """, (week_start_date,))

                # 插入新的週資料
                for item in schedule_data:
                    cursor.execute(f"""
                        INSERT INTO {ANIME_WEEKLY_SCHEDULE_TABLE}
                        (weekStartDate, dayOfWeek, scheduledTime, animeData)
                        VALUES (?, ?, ?, ?)
                    """, (
                        week_start_date,
                        item['day_of_week'],
                        item['scheduled_time'],
                        json.dumps(item['anime_data'])
                    ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [save_weekly_schedule] Error saving week {week_start_date}: {e}", exc_info=True)
            return False

    def get_today_schedule(self) -> list:
        """獲取今天的時程表（從週表中）"""
        try:
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())  # 取得本週一的日期
            day_of_week = (now.weekday() + 1) % 7 or 7  # 1=Mon, 7=Sun

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT scheduledTime, animeData, pushed FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE weekStartDate = ? AND dayOfWeek = ?
                    ORDER BY scheduledTime ASC
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
            logger.error(f"❌ [get_today_schedule] Error: {e}", exc_info=True)
            return []

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記某個時刻已推送過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                    SET pushed = 1
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                """, (week_start_date, day_of_week, scheduled_time))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ [mark_time_pushed] Error marking week_start={week_start_date} day={day_of_week} time={scheduled_time}: {e}", exc_info=True)
            return False

    # ==================== 動畫詳細資訊快取方法 ====================

    def cache_anime_details(self, anime_sn: int, name: str, content: str,
                           cover_url: str, tags: list, view_count: int, score: float) -> bool:
        """快取動畫詳細資訊"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_DETAILS_TABLE}
                    (animeSn, name, content, coverUrl, tags, viewCount, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (anime_sn, name, content, cover_url, json.dumps(tags), view_count, score))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error caching anime details: {e}")
            return False

    def get_anime_details(self, anime_sn: int) -> Optional[dict]:
        """獲取動畫詳細資訊"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT name, content, coverUrl, tags, viewCount, score
                    FROM {ANIME_DETAILS_TABLE}
                    WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'name': row[0],
                        'content': row[1],
                        'cover_url': row[2],
                        'tags': json.loads(row[3]) if row[3] else [],
                        'view_count': row[4],
                        'score': row[5]
                    }
                return None
        except Exception as e:
            print(f"Error getting anime details: {e}")
            return None

    # ==================== 集數統計方法 ====================

    def record_episode_stats(self, video_sn: int, anime_sn: int, episode_num: str,
                            views: int, score: float = 0) -> bool:
        """記錄 集數統計數據"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {EPISODE_STATS_TABLE}
                    (videoSn, animeSn, episodeNum, views, score)
                    VALUES (?, ?, ?, ?, ?)
                """, (video_sn, anime_sn, episode_num, views, score))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error recording episode stats: {e}")
            return False

    # ==================== 動畫統計方法 ====================

    def get_anime_statistics(self, anime_sn: int) -> Optional[dict]:
        """獲取動畫統計資訊"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT
                        COUNT(es.videoSn) as total_episodes,
                        SUM(es.views) as total_views,
                        AVG(es.views) as avg_views,
                        AVG(es.score) as avg_score
                    FROM {EPISODE_STATS_TABLE} es
                    WHERE es.animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row and row[0] > 0:  # 有至少一集
                    return {
                        'total_episodes': row[0],
                        'total_views': row[1] if row[1] is not None else 0,
                        'avg_views': row[2] if row[2] is not None else 0,
                        'avg_score': row[3] if row[3] is not None else 0
                    }
                return None
        except Exception as e:
            print(f"Error getting anime statistics: {e}")
            return None

    def get_top_anime_by_views(self, limit: int = 10,
                              start_time: Optional[datetime] = None,
                              end_time: Optional[datetime] = None) -> list:
        """依觀看數取得熱門動畫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 構建時間條件
                time_condition = ""
                params = []
                if start_time and end_time:
                    time_condition = " AND es.recordedAt BETWEEN ? AND ?"
                    params = [start_time.strftime("%Y-%m-%d %H:%M:%S"),
                             end_time.strftime("%Y-%m-%d %H:%M:%S")]

                query = f"""
                    SELECT
                        d.animeSn,
                        d.name,
                        SUM(es.views) as total_views,
                        COUNT(es.videoSn) as episode_count
                    FROM {EPISODE_STATS_TABLE} es
                    JOIN {ANIME_DETAILS_TABLE} d ON es.animeSn = d.animeSn
                    WHERE 1=1 {time_condition}
                    GROUP BY es.animeSn
                    ORDER BY total_views DESC
                    LIMIT ?
                """
                params.append(limit)
                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'anime_sn': row[0],
                        'name': row[1],
                        'total_views': row[2] if row[2] is not None else 0,
                        'total_episodes': row[3] if row[3] is not None else 0
                    })
                return results
        except Exception as e:
            print(f"Error getting top anime by views: {e}")
            return []

    def get_multi_episode_anime_for_chart(self, limit: int = 10, min_episodes: int = 2,
                                         start_time: Optional[datetime] = None,
                                         end_time: Optional[datetime] = None) -> list:
        """取得適合製作圖表的多集動畫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 構建時間條件
                time_condition = ""
                params = []
                if start_time and end_time:
                    time_condition = " AND es.recordedAt BETWEEN ? AND ?"
                    params = [start_time.strftime("%Y-%m-%d %H:%M:%S"),
                             end_time.strftime("%Y-%m-%d %H:%M:%S")]

                query = f"""
                    SELECT
                        d.animeSn,
                        d.name,
                        es.videoSn,
                        es.episodeNum,
                        es.views
                    FROM {EPISODE_STATS_TABLE} es
                    JOIN {ANIME_DETAILS_TABLE} d ON es.animeSn = d.animeSn
                    WHERE 1=1 {time_condition}
                    AND d.animeSn IN (
                        SELECT animeSn
                        FROM {EPISODE_STATS_TABLE}
                        GROUP BY animeSn
                        HAVING COUNT(*) >= ?
                    )
                    ORDER BY d.animeSn, es.videoSn
                """
                params.append(min_episodes)
                params.append(limit * 10)  # 限制返回的行數，避免過多
                cursor.execute(query, params)

                # 按動畫分組處理結果
                anime_dict = {}
                for row in cursor.fetchall():
                    anime_sn, name, video_sn, episode_num, views = row
                    if anime_sn not in anime_dict:
                        anime_dict[anime_sn] = {
                            'anime_sn': anime_sn,
                            'name': name,
                            'episodes': []
                        }
                    anime_dict[anime_sn]['episodes'].append({
                        'num': episode_num,
                        'views': views
                    })

                # 轉換為列表格式並限制數量
                results = list(anime_dict.values())[:limit]
                return results
        except Exception as e:
            print(f"Error getting multi episode anime for chart: {e}")
            return []


    def get_anime_details_by_videosn(self, video_sn: int) -> Optional[dict]:
        """根據 video_sn 取得動畫詳細資訊"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 先從 episode_stats 找到對應的 anime_sn
                cursor.execute(f"""
                    SELECT animeSn FROM {EPISODE_STATS_TABLE}
                    WHERE videoSn = ?
                """, (video_sn,))
                row = cursor.fetchone()
                if not row:
                    return None
                anime_sn = row[0]
                # 再取得動畫詳細資訊
                cursor.execute(f"""
                    SELECT name, content, coverUrl, tags, viewCount, score
                    FROM {ANIME_DETAILS_TABLE}
                    WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'name': row[0],
                        'content': row[1],
                        'cover_url': row[2],
                        'tags': json.loads(row[3]) if row[3] else [],
                        'view_count': row[4],
                        'score': row[5]
                    }
                return None
        except Exception as e:
            print(f"Error getting anime details by videosn: {e}")
            return None

    def is_reward_already_given(self, message_id: int, reward_type: str) -> bool:
        """檢查是否已經發放過指定類型的獎勵"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_REWARDS_TABLE}
                    WHERE messageId = ? AND rewardType = ?
                    LIMIT 1
                """, (message_id, reward_type))
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error checking reward status: {e}")
            return False

    def record_reward(self, message_id: int, reward_type: str, amount: int, user_id: str) -> bool:
        """記錄獎勵發放"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT INTO {ANIME_REWARDS_TABLE}
                    (messageId, rewardType, amount, userId)
                    VALUES (?, ?, ?, ?)
                """, (message_id, reward_type, amount, user_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [record_reward] Error recording reward: {e}", exc_info=True)
            return False


class AnimePushCore:
    """Bahamut 動畫追蹤 - Push/Core 核心功能"""

    def __init__(self, db_path: Path):
        global ANIME_DB_PATH
        ANIME_DB_PATH = db_path

        # 初始化資料庫實例，避免靜默失敗
        self.db = AnimeDatabase(db_path)
        self.bot = None

    def set_bot_and_db(self, bot, db):
        """設置 bot 和資料庫實例（可選覆蓋）"""
        self.bot = bot
        if db is not None:
            self.db = db

    # ==================== API 相關方法 ====================

    async def fetch_new_anime_from_api(self) -> List[Dict]:
        """從 API 獲取最近更新的動畫集數"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        logger.warning(f"❌ [fetch_new_anime_from_api] API returned status {resp.status}")
                        return None
                    data = await resp.json()

                    # API 回應結構: { "data": { "newAnime": { "date": [...], "popular": [...] }, ... } }
                    new_anime = data.get('data', {}).get('newAnime')
                    if not new_anime or 'date' not in new_anime:
                        logger.warning("⚠️ [fetch_new_anime_from_api] API response missing 'data.newAnime.date' key")
                        return None

                    return new_anime['date']
        except Exception as e:
            logger.error(f"❌ [fetch_new_anime_from_api] Failed to fetch new anime: {e}", exc_info=True)
            return None

    async def fetch_all_recent_anime_from_api(self) -> List[Dict]:
        """獲取所有最近更新的動畫（用於排行榜）"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        logger.warning(f"❌ [fetch_all_recent_anime_from_api] API returned status {resp.status}")
                        return None
                    data = await resp.json()

                    new_anime = data.get('data', {}).get('newAnime')
                    if not new_anime or 'date' not in new_anime:
                        logger.warning("⚠️ [fetch_all_recent_anime_from_api] API response missing 'data.newAnime.date' key")
                        return None

                    return new_anime['date']
        except Exception as e:
            logger.error(f"❌ [fetch_all_recent_anime_from_api] Failed to fetch recent anime: {e}", exc_info=True)
            return None

    async def fetch_anime_details_from_api(self, video_sn: int) -> Optional[Dict]:
        """從 API 獲取單集動畫詳細信息"""
        try:
            url = f"https://api.gamer.com.tw/mobile_app/anime/v2/video.php?vsn={video_sn}"
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"❌ [fetch_anime_details_from_api] API returned status {resp.status} for video_sn {video_sn}")
                        return None
                    data = await resp.json()
                    return data
        except Exception as e:
            logger.error(f"❌ [fetch_anime_details_from_api] Failed to fetch anime details for video_sn {video_sn}: {e}", exc_info=True)
            return None

    def _extract_view_count_from_episode(self, episode: Dict) -> int:
        """從 episode 資料中提取觀看數"""
        views = 0
        # 嘗試多個可能的欄位名
        for field in ['views', 'viewCount', 'playCount', 'popular']:
            if field in episode and isinstance(episode[field], (int, float)):
                views = int(episode[field])
                break
        return views

    def _get_weekday_name(self, weekday: int) -> str:
        """獲取星期名稱（1=星期一, 7=星期日）"""
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        if 1 <= weekday <= 7:
            return weekday_names[weekday - 1]
        return "未知"

    # ==================== 訊息發送相關方法 ====================

    async def generate_anime_embed(self, episode: Dict) -> Optional[discord.Embed]:
        """為動畫集數生成 Discord Embed"""
        try:
            video_sn = episode.get("videoSn")
            anime_sn = episode.get("animeSn")
            title = episode.get("title", "未知標題")
            volume = episode.get("volume", "")
            cover = episode.get("cover", "")

            # 組合標題
            if volume:
                    title_with_volume = f"{title} 第{volume}集"
            else:
                    title_with_volume = title

            # 建立 embed
            embed = discord.Embed(
                title=f"🆕 新番更新：{title_with_volume}",
                url=f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}",
                color=0x00bfff,
                timestamp=datetime.now(TW_TZ)
            )

            # 設置封面圖片
            if cover:
                embed.set_thumbnail(url=cover)

            # 添加動畫資訊
            embed.add_field(
                name="動畫名稱",
                value=title,
                inline=True
            )

            if volume:
                embed.add_field(
                    name="集數",
                    value=f"第{volume}集",
                    inline=True
                )

            embed.add_field(
                name="觀看連結",
                value=f"[點擊觀看](https://ani.gamer.com.tw/animeVideo.php?sn={video_sn})",
                inline=False
            )

            # 設置 footer
            embed.set_footer(
                text=f"動畫 ID: {anime_sn} | 集 ID: {video_sn}",
                icon_url="https://i.imgur.com/5JF6KXp.png"
            )

            return embed
        except Exception as e:
            logger.error(f"❌ [generate_anime_embed] Failed to generate embed for video_sn {episode.get('videoSn')}: {e}", exc_info=True)
            return None

    async def generate_anime_view(self, episode: Dict) -> Optional[discord.ui.View]:
        """為動畫集數生成 Discord View (包含投票按鈕和評論按鈕)"""
        try:
            # 這裡會返回 AnimeVoteView 實例
            # 但在這個模組中，我們需要引用 AnimeTracker 來創建視圖
            # 為了避免循環導入，我們返回 None，實際的視圖生成將在 AnimeTracker 中完成
            return None
        except Exception as e:
            logger.error(f"❌ [generate_anime_view] Failed to generate view: {e}", exc_info=True)
            return None

    async def send_anime_push(self, scheduled_time: str, channel_id: int) -> bool:
        """根�據時程表發送動畫推送

        關鍵修復：當 API 成功取得資料後，無論是否有新番可推送，都會標記該時刻為
        「已推送」。否則「無新番」時週表 pushed 欄位永遠為 0，會導致
        _periodic_catchup_check 每 5 分鐘無限重試同一時刻（呼叫 API、找不到新番、
        又未標記）。只有 API 失敗或頻道不存在時才不標記，以便稍後重試。
        """
        try:
            await self.bot.wait_until_ready()

            # 先檢查頻道是否存在（避免無頻道時仍呼叫 API 浪費配額）
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"⚠️ [send_anime_push] 頻道 {channel_id} 不存在，跳過 {scheduled_time}（不標記，稍後重試）")
                return False

            # 獲取最新動畫數據
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                # API 失敗 → 不標記，讓 _periodic_catchup_check 稍後重試
                logger.warning(f"⚠️ [send_anime_push] API 無回應或無資料，跳過 {scheduled_time}（不標記，稍後重試）")
                return False

            # API 成功：找出尚未通知的新集
            new_episodes = []
            for ep in episodes:
                video_sn = ep.get("videoSn")
                if video_sn and not self.db.is_notified(video_sn):
                    new_episodes.append(ep)

            if not new_episodes:
                logger.info(f"📭 [send_anime_push] {scheduled_time} 無新番需推送（所有集數已通知），仍會標記時刻已完成")

            sent_count = 0
            for episode in new_episodes:
                try:
                    video_sn = episode.get("videoSn")
                    anime_sn = episode.get("animeSn")
                    title = episode.get("title", "未知標題")

                    # 生成 embed
                    embed = await self.generate_anime_embed(episode)
                    if not embed:
                        continue

                    # 生成 view
                    view = await self.generate_anime_view(episode)

                    # 發送訊息
                    message = await channel.send(embed=embed, view=view)

                    # 保存消息資訊
                    self.db.save_message_info(
                        message.id, video_sn, anime_sn, title, channel_id
                    )

                    # 記錄為已通知
                    self.db.add_notified(video_sn, anime_sn, title)

                    # 向 bot 註冊永久視圖
                    if view:
                        self.bot.add_view(view, message_id=message.id)

                    sent_count += 1

                except Exception as e:
                    logger.error(f"❌ [send_anime_push] Error sending episode {episode.get('videoSn')}: {e}", exc_info=True)
                    continue

            # ✅ 關鍵修復：API 成功即標記該時刻為已推送（不論是否有新番），
            # 防止「無新番」時 pushed 永遠為 0 導致補推無限重試
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())
            day_of_week = (now.weekday() + 1) % 7 or 7
            marked = self.db.mark_time_pushed(
                week_start.strftime("%Y-%m-%d"),
                day_of_week,
                scheduled_time
            )
            if marked:
                logger.info(f"✅ [send_anime_push] 已標記 {scheduled_time} 為已推送（實際發送 {sent_count} 則新番）")
            else:
                logger.warning(f"⚠️ [send_anime_push] 標記 {scheduled_time} 失敗（週表可能無對應列：week_start={week_start.strftime('%Y-%m-%d')}, day={day_of_week}）")

            return sent_count > 0
        except Exception as e:
            logger.error(f"❌ [send_anime_push] Unexpected error: {e}", exc_info=True)
            return False