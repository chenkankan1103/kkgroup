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

    def _get_connection(self):
        """獲取配置好 WAL 模式的資料庫連接"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_database(self):
        """初始化資料庫表格"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 已通知的動畫表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {NOTIFIED_TABLE} (
                    videoSn INTEGER PRIMARY KEY,
                    animeSn INTEGER,
                    anime_name TEXT,
                    volume TEXT,
                    cover_url TEXT,
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
                    anime_name TEXT,
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
                    anime_name TEXT,
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
            (NOTIFIED_TABLE, "anime_name", "TEXT"),
            (NOTIFIED_TABLE, "volume", "TEXT"),
            (NOTIFIED_TABLE, "cover_url", "TEXT"),
            (NOTIFIED_TABLE, "notifiedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_MESSAGES_TABLE, "messageId", "INTEGER PRIMARY KEY"),
            (ANIME_MESSAGES_TABLE, "videoSn", "INTEGER"),
            (ANIME_MESSAGES_TABLE, "animeSn", "INTEGER"),
            (ANIME_MESSAGES_TABLE, "anime_name", "TEXT"),
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
            (ANIME_VOTES_TABLE, "anime_name", "TEXT"),
            (ANIME_VOTES_TABLE, "voteType", "TEXT"),
            (ANIME_VOTES_TABLE, "userId", "TEXT"),
            (ANIME_VOTES_TABLE, "messageId", "INTEGER"),
            (ANIME_VOTES_TABLE, "comment", "TEXT"),
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
                    logger.info(f"[Migration] Adding column {column_name} to {table_name}")
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            except Exception as e:
                logger.warning(f"[Migration] Could not add {column_name} to {table_name}: {e}")

    # ==================== 通知相關方法 ====================

    def is_notified(self, video_sn: int) -> bool:
        """檢查動畫集數是否已經通知過"""
        try:
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_MESSAGES_TABLE}
                    (messageId, videoSn, animeSn, anime_name, channelId)
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
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 使用新欄位名 (anime_name, cover_url) 配合 migration schema
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {NOTIFIED_TABLE}
                    (videoSn, animeSn, anime_name, volume, cover_url)
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
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT messageId, videoSn, animeSn, anime_name, channelId
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
        """保存週表數據 - 使用 UPSERT 保留已推送狀態 (pushed=1)

        關鍵修復：不再使用 DELETE+INSERT，改用逐筆檢查並更新/插入，
        以保留 pushed=1 的記錄（避免每天 22:00 重置導致重複推送）。

        新增：API 可能回傳重複 timeslot（同一天同一時間多筆），先去重再寫入。
        """
        try:
            # --- Pre-dedup: API 可能為同一天同一時間返回多筆，先按 (dayOfWeek, scheduledTime) 去重 ---
            # 策略：保留第一筆 (索引最小)，舊資料的 animeData 會被後續 UPSERT 邏輯覆蓋或保留
            seen = {}
            deduped = []
            for idx, item in enumerate(schedule_data):
                key = (item['day_of_week'], item['scheduled_time'])
                if key not in seen:
                    seen[key] = idx
                    deduped.append(item)
                else:
                    logger.warning(f"⚠️ [save_weekly_schedule] 週 {week_start_date} 發現重複時段: day={item['day_of_week']} {item['scheduled_time']}，忽略第 {idx+1} 筆 (保留第 {seen[key]+1} 筆)")
            if len(deduped) != len(schedule_data):
                logger.info(f"📋 [save_weekly_schedule] 週 {week_start_date} 去重: {len(schedule_data)} -> {len(deduped)} 筆")
            schedule_data = deduped
            # --- End pre-dedup ---

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 全量覆蓋：先刪除該 week_start_date 不在新 schedule_data 中的舊記錄
                # 這確保週表真正「全量覆蓋」，避免舊時段殘留導致孤兒記錄
                new_times = {(item['day_of_week'], item['scheduled_time']) for item in schedule_data}
                if new_times:
                    # SQLite 不支援 tuple IN，改用逐條檢查或動態構建 WHERE 條件
                    # 這裡用動態構建 WHERE 條件
                    conditions = []
                    params = [week_start_date]
                    for dow, st in new_times:
                        conditions.append("(dayOfWeek = ? AND scheduledTime = ?)")
                        params.extend([dow, st])
                    where_clause = " OR ".join(conditions)
                    cursor.execute(f"""
                        DELETE FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                        WHERE weekStartDate = ? 
                        AND NOT ({where_clause})
                    """, params)
                else:
                    # 如果新 schedule_data 為空，刪除該週所有記錄
                    cursor.execute(f"""
                        DELETE FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                        WHERE weekStartDate = ?
                    """, (week_start_date,))

                for item in schedule_data:
                    day_of_week = item['day_of_week']
                    scheduled_time = item['scheduled_time']
                    anime_data_json = json.dumps(item['anime_data'])

                    # 檢查是否已存在該時刻
                    cursor.execute(f"""
                        SELECT id, pushed FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                        WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                    """, (week_start_date, day_of_week, scheduled_time))
                    row = cursor.fetchone()

                    if row:
                        existing_id, existing_pushed = row
                        if existing_pushed == 1:
                            # 已推送：只更新 animeData，保留 pushed=1
                            cursor.execute(f"""
                                UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                                SET animeData = ?
                                WHERE id = ?
                            """, (anime_data_json, existing_id))
                        else:
                            # 未推送：更新 animeData，保留 pushed=0
                            cursor.execute(f"""
                                UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                                SET animeData = ?
                                WHERE id = ?
                            """, (anime_data_json, existing_id))
                    else:
                        # 新時刻：插入新記錄 (pushed=0)
                        cursor.execute(f"""
                            INSERT INTO {ANIME_WEEKLY_SCHEDULE_TABLE}
                            (weekStartDate, dayOfWeek, scheduledTime, animeData, pushed)
                            VALUES (?, ?, ?, ?, 0)
                        """, (week_start_date, day_of_week, scheduled_time, anime_data_json))

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

            with self._get_connection() as conn:
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
                        'pushed': bool(row[2]),
                        'day_of_week': day_of_week  # 加上 day_of_week 供後續使用
                    })
                return results
        except Exception as e:
            logger.error(f"❌ [get_today_schedule] Error: {e}", exc_info=True)
            return []

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記某個時刻已推送過"""
        try:
            with self._get_connection() as conn:
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

    def is_time_checked_today(self, scheduled_time: str, check_date=None) -> bool:
        """檢查今日是否已檢查過某個時段（防止重複檢查，解決 Bot 重啟問題）"""
        try:
            if check_date is None:
                check_date = datetime.now(TW_TZ).date()
            elif isinstance(check_date, datetime):
                check_date = check_date.date()
            
            week_start = check_date - timedelta(days=check_date.weekday())
            day_of_week = (check_date.weekday() + 1) % 7 or 7
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_CHECK_HISTORY_TABLE}
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                """, (week_start.strftime("%Y-%m-%d"), day_of_week, scheduled_time))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ [is_time_checked_today] Error: {e}", exc_info=True)
            return False

    def mark_time_checked(self, scheduled_time: str, check_date=None) -> bool:
        """標記時段已檢查（防止重複檢查，解決 Bot 重啟問題）"""
        try:
            if check_date is None:
                check_date = datetime.now(TW_TZ).date()
            elif isinstance(check_date, datetime):
                check_date = check_date.date()
            
            week_start = check_date - timedelta(days=check_date.weekday())
            day_of_week = (check_date.weekday() + 1) % 7 or 7
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR IGNORE INTO {ANIME_CHECK_HISTORY_TABLE}
                    (weekStartDate, dayOfWeek, scheduledTime)
                    VALUES (?, ?, ?)
                """, (week_start.strftime("%Y-%m-%d"), day_of_week, scheduled_time))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ [mark_time_checked] Error: {e}", exc_info=True)
            return False

    def get_schedule_video_sns(self, week_start_date: str, day_of_week: int,
                               scheduled_time: str) -> set:
        """從週表取得指定時段預期的 videoSn 集合

        用於 send_anime_push 過濾 API 回傳的新番，確保只推送屬於該時段的動畫，
        防止補推時把其他時段的動畫也推出去。

        注意：newAnimeSchedule API 回傳的資料只有 videoSn（沒有 animeSn），
        因此改用 videoSn 進行匹配。videoSn 是每集唯一識別碼，比 animeSn 更精確。

        Args:
            week_start_date: 週起始日期 "YYYY-MM-DD"
            day_of_week: 1=週一~7=週日
            scheduled_time: "HH:MM" 格式
        Returns:
            set[int]: 該時段預期的 videoSn 集合（可能為空）
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT animeData FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                """, (week_start_date, day_of_week, scheduled_time))
                rows = cursor.fetchall()
                video_sns = set()
                for row in rows:
                    try:
                        anime_data = json.loads(row[0])
                        video_sn = anime_data.get('videoSn')
                        if video_sn:
                            video_sns.add(int(video_sn))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                return video_sns
        except Exception as e:
            logger.error(f"❌ [get_schedule_video_sns] Error: {e}", exc_info=True)
            return set()

    def clean_orphaned_records(self, week_start_date: str = None) -> dict:
        """清理孤兒記錄：anime_messages、anime_notified 中對應已刪除週表時段的記錄

        當 22:00 刷新週表時，API 可能不再回傳某些舊時段，導致週表被 DELETE/重建後，
        但相關的 messages、notified 記錄仍留存。此方法清理這些孤兒記錄。

        Args:
            week_start_date: 指定週起始日期 (YYYY-MM-DD)，None 表示清理所有週
        Returns:
            dict: 刪除統計 {'messages': N, 'notified': N}
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                stats = {'messages': 0, 'notified': 0}

                # 1. 找出所有存在於週表中的 videoSn
                if week_start_date:
                    cursor.execute(f"""
                        SELECT DISTINCT json_extract(animeData, '$.videoSn') as videoSn
                        FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                        WHERE weekStartDate = ?
                    """, (week_start_date,))
                else:
                    cursor.execute(f"""
                        SELECT DISTINCT json_extract(animeData, '$.videoSn') as videoSn
                        FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    """)
                valid_video_sns = {str(row[0]) for row in cursor.fetchall() if row[0] is not None}

                if not valid_video_sns:
                    logger.info(f"ℹ️ [clean_orphaned_records] 週表為空，無有效 videoSn")
                    return stats

                # 2. 清理 anime_messages 中不在週表中的 videoSn
                placeholders = ','.join('?' * len(valid_video_sns))
                cursor.execute(f"""
                    DELETE FROM {ANIME_MESSAGES_TABLE}
                    WHERE videoSn NOT IN ({placeholders})
                """, tuple(valid_video_sns))
                stats['messages'] = cursor.rowcount

                # 3. 清理 anime_notified 中不在週表中的 videoSn
                cursor.execute(f"""
                    DELETE FROM {NOTIFIED_TABLE}
                    WHERE videoSn NOT IN ({placeholders})
                """, tuple(valid_video_sns))
                stats['notified'] = cursor.rowcount

                conn.commit()
                logger.info(f"🧹 [clean_orphaned_records] 清理完成: messages={stats['messages']}, notified={stats['notified']} (基於週表有效 videoSn: {len(valid_video_sns)} 個)")
                return stats
        except Exception as e:
            logger.error(f"❌ [clean_orphaned_records] Error: {e}", exc_info=True)
            return {'messages': 0, 'notified': 0, 'error': str(e)}

    # ==================== 動畫詳細資訊快取方法 ====================

    def cache_anime_details(self, anime_sn: int, name: str, content: str,
                           cover_url: str, tags: list, view_count: int, score: float) -> bool:
        """快取動畫詳細資訊"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_DETAILS_TABLE}
                    (animeSn, name, content, coverUrl, tags, viewCount, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (anime_sn, name, content, cover_url, json.dumps(tags), view_count, score))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [cache_anime_details] Error: {e}", exc_info=True)
            return False

    def get_anime_details(self, anime_sn: int) -> Optional[dict]:
        """獲取動畫詳細資訊"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT name, content, coverUrl, tags, viewCount, score
                    FROM {ANIME_DETAILS_TABLE}
                    WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'animeSn': anime_sn,
                        'title': row[0],  # alias for name
                        'name': row[0],   # keep original for backward compat
                        'content': row[1],
                        'cover_url': row[2],
                        'tags': json.loads(row[3]) if row[3] else [],
                        'view_count': row[4],
                        'score': row[5]
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_anime_details] Error getting anime details for anime_sn {anime_sn}: {e}", exc_info=True)
            return None

    # ==================== 集數統計方法 ====================

    def record_episode_stats(self, video_sn: int, anime_sn: int, episode_num: str,
                            views: int, score: float = 0) -> bool:
        """記錄 集數統計數據"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {EPISODE_STATS_TABLE}
                    (videoSn, animeSn, episodeNum, views, score)
                    VALUES (?, ?, ?, ?, ?)
                """, (video_sn, anime_sn, episode_num, views, score))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [record_episode_stats] Error: {e}", exc_info=True)
            return False

    # ==================== 動畫統計方法 ====================

    def get_top_anime_by_views(self, limit: int = 10,
                              start_time: Optional[datetime] = None,
                              end_time: Optional[datetime] = None) -> list:
        """依觀看數取得熱門動畫"""
        try:
            with self._get_connection() as conn:
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
            logger.error(f"❌ [get_top_anime_by_views] Error: {e}", exc_info=True)
            return []

    def get_multi_episode_anime_for_chart(self, limit: int = 10, min_episodes: int = 2,
                                         start_time: Optional[datetime] = None,
                                         end_time: Optional[datetime] = None) -> list:
        """取得適合製作圖表的多集動畫"""
        try:
            with self._get_connection() as conn:
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
            logger.error(f"❌ [get_multi_episode_anime_for_chart] Error: {e}", exc_info=True)
            return []


    def get_anime_details_by_videosn(self, video_sn: int) -> Optional[dict]:
        """根據 video_sn 取得動畫詳細資訊"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 先從 episode_stats 找到對應的 anime_sn
                cursor.execute(f"""
                    SELECT animeSn, episodeNum FROM {EPISODE_STATS_TABLE}
                    WHERE videoSn = ?
                """, (video_sn,))
                row = cursor.fetchone()
                if not row:
                    return None
                anime_sn, episode_num = row
                # 再取得動畫詳細資訊
                cursor.execute(f"""
                    SELECT name, content, coverUrl, tags, viewCount, score
                    FROM {ANIME_DETAILS_TABLE}
                    WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'videoSn': video_sn,
                        'animeSn': anime_sn,
                        'title': row[0],  # alias for name
                        'name': row[0],
                        'content': row[1],
                        'cover_url': row[2],
                        'tags': json.loads(row[3]) if row[3] else [],
                        'view_count': row[4],
                        'score': row[5],
                        'volume': episode_num or ''  # episode number from episode_stats
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_anime_details_by_videosn] Error for video_sn {video_sn}: {e}", exc_info=True)
            return None

    def get_anime_statistics(self, anime_sn: int) -> Optional[dict]:
        """獲取動畫統計數據（總觀看數、平均觀看數等）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT totalViews, avgViews, totalEpisodes, latestScore
                    FROM {ANIME_STATS_TABLE}
                    WHERE animeSn = ?
                """, (anime_sn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'total_views': row[0] if row[0] is not None else 0,
                        'avg_views': row[1] if row[1] is not None else 0.0,
                        'total_episodes': row[2] if row[2] is not None else 0,
                        'latest_score': row[3] if row[3] is not None else 0.0
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_anime_statistics] Error for anime_sn {anime_sn}: {e}", exc_info=True)
            return None

    def is_reward_already_given(self, message_id: int, reward_type: str) -> bool:
        """檢查是否已經發放過指定類型的獎勵"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_REWARDS_TABLE}
                    WHERE messageId = ? AND rewardType = ?
                    LIMIT 1
                """, (message_id, reward_type))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ [is_reward_already_given] Error checking reward status: {e}", exc_info=True)
            return False

    def record_reward(self, message_id: int, reward_type: str, amount: int, user_id: str) -> bool:
        """記錄獎勵發放"""
        try:
            with self._get_connection() as conn:
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

    def record_vote(self, video_sn: int, anime_sn: int, message_id: int,
                    vote_type: str, comment: str = None, user_hash: str = None) -> bool:
        """記錄匿名投票/評論

        Args:
            video_sn: 集數序號
            anime_sn: 動畫序號
            message_id: Discord 訊息 ID（用於關聯統計）
            vote_type: 投票類型 ('masterpiece', 'great', 'good', 'average', 'bad') 或 'comment'
            comment: 評論內容（可選）
            user_hash: 匿名用戶識別符
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT INTO {ANIME_VOTES_TABLE}
                    (videoSn, animeSn, anime_name, voteType, userId, messageId, comment)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (video_sn, anime_sn, "", vote_type, user_hash, message_id, comment))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [record_vote] Error recording vote: {e}", exc_info=True)
            return False

    def get_vote_stats(self, message_id: int) -> Dict[str, int]:
        """獲取指定訊息的投票統計（各類型票數）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT voteType, COUNT(*) as count
                    FROM {ANIME_VOTES_TABLE}
                    WHERE messageId = ? AND voteType != 'comment'
                    GROUP BY voteType
                """, (message_id,))
                return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"❌ [get_vote_stats] Error: {e}", exc_info=True)
            return {}

    def get_vote_comments(self, message_id: int, limit: int = 5) -> List[str]:
        """獲取指定訊息的評論列表"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT comment FROM {ANIME_VOTES_TABLE}
                    WHERE messageId = ? AND voteType = 'comment' AND comment IS NOT NULL
                    ORDER BY votedAt DESC LIMIT ?
                """, (message_id, limit))
                return [row[0] for row in cursor.fetchall() if row[0]]
        except Exception as e:
            logger.error(f"❌ [get_vote_comments] Error: {e}", exc_info=True)
            return []

    def get_weekly_vote_stats(self) -> Dict[int, Dict]:
        """獲取本週投票統計（按 animeSn 分組）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 取本週一 00:00 起的投票
                now = datetime.now(TW_TZ)
                week_start = (now - timedelta(days=now.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0)
                cursor.execute(f"""
                    SELECT animeSn, voteType, COUNT(*) as count
                    FROM {ANIME_VOTES_TABLE}
                    WHERE votedAt >= ? AND voteType != 'comment'
                    GROUP BY animeSn, voteType
                """, (week_start.strftime("%Y-%m-%d %H:%M:%S"),))
                stats: Dict[int, Dict] = {}
                for anime_sn, vote_type, count in cursor.fetchall():
                    if anime_sn not in stats:
                        stats[anime_sn] = {'total_votes': 0, 'votes': {}}
                    stats[anime_sn]['votes'][vote_type] = count
                    stats[anime_sn]['total_votes'] += count
                return stats
        except Exception as e:
            logger.error(f"❌ [get_weekly_vote_stats] Error: {e}", exc_info=True)
            return {}


class AnimePushCore:
    """Bahamut 動畫追蹤 - Push/Core 核心功能"""

    def __init__(self, db_path: Path):
        global ANIME_DB_PATH
        ANIME_DB_PATH = db_path

        # 初始化資料庫實例，避免靜默失敗
        self.db = AnimeDatabase(db_path)
        self.bot = None

        # View 生成工廠（由上層 AnimeTracker 設定）
        self._view_factory = None

        # API 速率限制：每次呼叫間隔至少 2 秒（<= 30 req/min），防止被巴哈姆特 BAN
        self._last_api_call = 0.0
        self._api_rate_limit_lock = asyncio.Lock()
        self._min_api_interval = 2.0  # seconds

        # 推送並發鎖：防止 dispatcher 和 catch-up 同時呼叫 send_anime_push
        # 造成同一時段重複推送或 race condition
        self._push_lock = asyncio.Lock()

    def set_bot_and_db(self, bot, db):
        """設置 bot 和資料庫實例（可選覆蓋）"""
        self.bot = bot
        if db is not None:
            self.db = db

    def set_view_factory(self, factory):
        """設定 View 生成工廠函數

        Args:
            factory: async function(episode: dict) -> discord.ui.View
        """
        self._view_factory = factory

    async def _rate_limit_api(self):
        """確保 API 呼叫間隔 >= 2 秒"""
        async with self._api_rate_limit_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_api_call
            if elapsed < self._min_api_interval:
                wait_time = self._min_api_interval - elapsed
                logger.debug(f"⏳ [_rate_limit_api] 等待 {wait_time:.2f} 秒以符合 API 速率限制")
                await asyncio.sleep(wait_time)
            self._last_api_call = asyncio.get_event_loop().time()

    # ==================== API 相關方法 ====================

    async def fetch_new_anime_from_api(self) -> List[Dict]:
        """從 API 獲取最近更新的動畫集數"""
        try:
            # 速率限制
            await self._rate_limit_api()

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
            # 速率限制
            await self._rate_limit_api()

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
            # 速率限制
            await self._rate_limit_api()

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
        """為動畫集數生成 Discord Embed

        修復 (2026-07-23):
        - 標題直接用 API 回傳值（API title 已含集數，不再重複加「第X集」）
        - 移除標籤欄位（API 無標籤資料）
        - 觀看數從 episode 直接提取（不再依賴第二個 API 呼叫）
        - 簡介從 episode 提取，無資料時不顯示（不再打 video.php 浪費配額）
        """
        try:
            video_sn = episode.get("videoSn")
            anime_sn = episode.get("animeSn")
            title = episode.get("title", "未知標題")
            cover = episode.get("cover", "")

            # 🔑 標題直接用 API 回傳值，不再附加「第X集」
            # Bahamut API 的 title 已包含集數資訊（如「咒術迴戰 第45集」）
            title_display = title

            # 🔑 觀看數：從 episode 直接提取（newAnime.date API 回應中的欄位）
            view_count = 0
            for field in ['popular', 'viewCount', 'views', 'playCount']:
                val = episode.get(field)
                if val is not None and isinstance(val, (int, float)) and val > 0:
                    view_count = int(val)
                    break

            # 🔑 簡介：從 episode 直接提取（若有），不再打第二個 API
            description_text = ""
            raw_content = episode.get('content', '') or episode.get('description', '') or ''
            if raw_content:
                description_text = self._truncate_text(str(raw_content), 300)

            # 評分
            score = episode.get('score', 0)
            try:
                score = float(score) if score else 0.0
            except (ValueError, TypeError):
                score = 0.0

            # 建立 embed
            embed = discord.Embed(
                title=f"🎬 {title_display}",
                description=description_text if description_text else None,
                url=f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}",
                color=discord.Color.from_rgb(178, 108, 196),  # 紫色主題
                timestamp=datetime.now(TW_TZ)
            )

            # 大圖在下方
            if cover:
                embed.set_image(url=cover)

            # 人氣數據（觀看數 + 評分）
            popularity_text = f"{view_count:,}" if view_count > 0 else "N/A"
            score_text = f"{score:.1f}" if score > 0 else "N/A"
            embed.add_field(
                name="📊 人氣數據",
                value=f"👥 觀看: {popularity_text} | ⭐ 評分: {score_text}",
                inline=False
            )

            # 投票說明
            embed.add_field(
                name="🎯 匿名投票",
                value="選擇你認為本作的評價，或留下評論\n投票完全匿名，無法追蹤個人身份",
                inline=False
            )

            # 獎勵說明
            embed.add_field(
                name="🎁 獲得獎勵",
                value="💬 **投票**: +2000 KK幣\n📝 **評論**: +3000 KK幣\n每條消息僅限一次獎勵",
                inline=False
            )

            embed.set_footer(text="動畫瘋新番通知 | 使用下方按鈕進行匿名投票")
            return embed
        except Exception as e:
            logger.error(f"❌ [generate_anime_embed] Failed to generate embed for "
                         f"video_sn {episode.get('videoSn')}: {e}", exc_info=True)
            return None

    def _truncate_text(self, text: str, max_length: int) -> str:
        """截斷文字到指定長度"""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    async def generate_anime_view(self, episode: Dict) -> Optional[discord.ui.View]:
        """為動畫集數生成 Discord View (使用外部工廠函數)"""
        try:
            if self._view_factory:
                return await self._view_factory(episode)
            logger.warning("⚠️ [generate_anime_view] No view factory set, returning None")
            return None
        except Exception as e:
            logger.error(f"❌ [generate_anime_view] Failed to generate view: {e}", exc_info=True)
            return None

    async def send_anime_push(self, scheduled_time: str, channel_id: int,
                             day_of_week: int = None,
                             week_start_date: str = None) -> bool:
        """根據時程表發送動畫推送（含時段匹配 + 並發鎖）

        核心修復 (2026-07-25)：
        1. 從週表取得該時段預期的 videoSn（而非 animeSn，因為 newAnimeSchedule API
           只提供 videoSn），只推送 videoSn 匹配的動畫
           → 防止補推時把其他時段的動畫也推出去
        2. 使用 _push_lock 防止 dispatcher 和 catch-up 同時推送
        3. API 成功即標記 pushed=1（不論是否有匹配新番），防止無限重試

        Args:
            scheduled_time: 預定時間，格式 "HH:MM"
            channel_id: Discord 頻道 ID
            day_of_week: 可選，1=週一~7=週日
            week_start_date: 可選，週起始日期 "YYYY-MM-DD"
        """
        # 使用並發鎖，防止 dispatcher 和 catch-up 同時推送同一時段
        async with self._push_lock:
            try:
                await self.bot.wait_until_ready()

                # 先計算 day_of_week 和 week_start_date（提前需要，用於查詢週表）
                now = datetime.now(TW_TZ)
                if day_of_week is None:
                    day_of_week = (now.weekday() + 1) % 7 or 7
                if week_start_date is None:
                    week_start_date = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")

                # 先檢查頻道是否存在
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logger.warning(f"⚠️ [send_anime_push] 頻道 {channel_id} 不存在，"
                                   f"跳過 {scheduled_time}（不標記，稍後重試）")
                    return False

                # 🔑 從週表取得該時段預期的 videoSn 集合
                # 注意：newAnimeSchedule API 只提供 videoSn，沒有 animeSn
                expected_video_sns = self.db.get_schedule_video_sns(
                    week_start_date, day_of_week, scheduled_time
                )
                if not expected_video_sns:
                    # 週表無此時間 → 可能是舊資料或 API 變更，標記 pushed 避免無限重試
                    logger.info(f"📭 [send_anime_push] {scheduled_time} 週表無對應 videoSn，"
                                f"標記 pushed 跳過（week_start={week_start_date}, day={day_of_week}）")
                    self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
                    return False

                logger.debug(f"🔍 [send_anime_push] {scheduled_time} 預期 videoSn: {expected_video_sns}")

                # 獲取最新動畫數據
                episodes = await self.fetch_new_anime_from_api()
                if not episodes:
                    # API 失敗 → 不標記，讓補推稍後重試
                    logger.warning(f"⚠️ [send_anime_push] API 無回應，"
                                   f"跳過 {scheduled_time}（不標記，稍後重試）")
                    return False

                # 🔑 關鍵過濾：只保留 videoSn 匹配該時段的 + 尚未通知的
                new_episodes = []
                for ep in episodes:
                    video_sn = ep.get("videoSn")
                    if not video_sn:
                        continue
                    try:
                        video_sn_int = int(video_sn)
                    except (ValueError, TypeError):
                        continue
                    # 必須 videoSn 匹配該時段，且尚未通知過
                    if video_sn_int in expected_video_sns and not self.db.is_notified(video_sn_int):
                        new_episodes.append(ep)
                    elif video_sn_int in expected_video_sns and self.db.is_notified(video_sn_int):
                        logger.debug(f"⏭️ [send_anime_push] videoSn={video_sn} 已通知過，跳過")
                    # videoSn 不匹配的 → 靜默跳過（不屬於這個時段）

                # 初始化 sent_count（在邏輯判斷前）
                sent_count = 0

                # 決定是否標記 pushed=1：
                # - 若有送出集數 → 標記
                # - 若無匹配集數但排程時間已過 > 30 分鐘 → 標記（避免無限重試）
                # - 若無匹配集數且剛到點（< 30 分鐘） → 不標記，留待重試
                if not new_episodes:
                    now = datetime.now(TW_TZ)
                    try:
                        sched_dt = datetime.strptime(scheduled_time, "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                        )
                        minutes_since_scheduled = (now - sched_dt).total_seconds() / 60
                    except Exception:
                        minutes_since_scheduled = 999

                    should_mark_pushed = sent_count > 0 or minutes_since_scheduled > 30

                    if not should_mark_pushed:
                        logger.info(f"⏳ [send_anime_push] {scheduled_time} 剛到點（{minutes_since_scheduled:.0f} 分鐘前）"
                                    f"API 尚無匹配集數（預期 {len(expected_video_sns)} 個 videoSn，"
                                    f"API 回傳 {len(episodes)} 集），暫不標記 pushed，稍後重試")
                        return False

                    logger.info(f"📭 [send_anime_push] {scheduled_time} 無匹配新番需推送"
                                f"（預期 {len(expected_video_sns)} 個 videoSn，"
                                f"API 回傳 {len(episodes)} 集，距排程 {minutes_since_scheduled:.0f} 分鐘），標記時刻已完成")
                else:
                    # 有匹配的新番要推送，送出後一定要標記
                    should_mark_pushed = True

                sent_count = 0
                for episode in new_episodes:
                    try:
                        video_sn = episode.get("videoSn")
                        anime_sn = episode.get("animeSn")
                        title = episode.get("title", "未知標題")

                        # 防禦性轉換
                        try:
                            video_sn = int(video_sn) if video_sn is not None else 0
                        except (ValueError, TypeError):
                            video_sn = 0
                        try:
                            anime_sn = int(anime_sn) if anime_sn is not None else 0
                        except (ValueError, TypeError):
                            anime_sn = 0

                        if not video_sn:
                            logger.warning(f"⚠️ [send_anime_push] Skip episode with "
                                           f"invalid video_sn: {episode}")
                            continue

                        embed = await self.generate_anime_embed(episode)
                        if not embed:
                            continue

                        view = await self.generate_anime_view(episode)

                        # 發送訊息（silent=True 靜音推送）
                        message = await channel.send(embed=embed, view=view, silent=True)

                        self.db.save_message_info(
                            message.id, video_sn, anime_sn, title, channel_id
                        )
                        self.db.add_notified(
                            video_sn, anime_sn,
                            episode.get("title", "未知標題"),
                            episode.get("volume", ""),
                            episode.get("cover", "")
                        )

                        if view:
                            self.bot.add_view(view, message_id=message.id)

                        sent_count += 1
                        logger.info(f"✅ [send_anime_push] 已推送: {title} "
                                    f"(videoSn={video_sn}, animeSn={anime_sn})")

                    except Exception as e:
                        logger.error(f"❌ [send_anime_push] Error sending episode "
                                     f"{episode.get('videoSn')}: {e}", exc_info=True)
                        continue

                # ✅ 只有在「已送出」或「排程時間已過超過 30 分鐘」才標記 pushed=1
                if should_mark_pushed:
                    marked = self.db.mark_time_pushed(
                        week_start_date, day_of_week, scheduled_time
                    )
                    if marked:
                        logger.info(f"✅ [send_anime_push] 已標記 {scheduled_time} 為已推送"
                                    f"（實際發送 {sent_count} 則，"
                                    f"預期 videoSn={expected_video_sns}）")
                    else:
                        logger.warning(f"⚠️ [send_anime_push] 標記 {scheduled_time} 失敗"
                                       f"（週表可能無對應列）")
                else:
                    logger.info(f"⏭️ [send_anime_push] {scheduled_time} 暫不標記 pushed，留待稍後重試")

                return sent_count > 0

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"❌ [send_anime_push] Unexpected error: {e}", exc_info=True)
                return False