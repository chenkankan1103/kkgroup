import discord
import aiohttp
import json
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Set
from zoneinfo import ZoneInfo

# ==================== Constants ====================
from pathlib import Path

TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # seconds

# Database path - 統一使用主數據庫
ANIME_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"

# Table names
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"
ANIME_DETAILS_TABLE = "anime_details"
ANIME_STATS_TABLE = "anime_statistics"
EPISODE_STATS_TABLE = "episode_statistics"
ANIME_MESSAGES_TABLE = "anime_messages"
ANIME_VOTES_TABLE = "anime_votes"
ANIME_REWARDS_TABLE = "anime_rewards"
ANIME_CHECK_HISTORY_TABLE = "anime_check_history"
ANIME_WEEKLY_SCHEDULE_TABLE = "anime_weekly_schedule"

logger = logging.getLogger(__name__)


# ==================== Helper Functions ====================
def get_week_start_date(now: Optional[datetime] = None, api_week: bool = False) -> str:
    """計算週起始日期 (YYYY-MM-DD) - 週一為起始日

    兩種模式：
    - 行事曆週 (api_week=False, 預設): 給定日期所屬的週 (週一~週日)
    - API 週 (api_week=True): 遵循 newAnimeSchedule API 語義
      - 週一~週六：回傳本週一 (API 回傳本週時程)
      - 週日：回傳下週一 (API 回傳下週時程)
    """
    if now is None:
        now = datetime.now(TW_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TW_TZ)

    if api_week and now.weekday() == 6:  # 週日且用 API 週：回傳下週一
        week_start = now + timedelta(days=1)
    else:
        # 行事曆週：週一~週日皆回傳本週一
        week_start = now - timedelta(days=now.weekday())
    return week_start.strftime("%Y-%m-%d")


def find_unpushed_items(
    today_schedule: list, now: Optional[datetime] = None, future_only: bool = False
) -> list:
    """從今日時程表中找出未推送的項目"""
    if now is None:
        now = datetime.now(TW_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TW_TZ)

    matching = []
    for item in today_schedule:
        if item.get("pushed"):
            continue
        scheduled = item.get("scheduled_time", "")
        try:
            sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
            )
            diff = (now - sched_dt).total_seconds()
            if future_only:
                if diff < 0:  # 時間尚未到達
                    matching.append(item)
            else:
                if diff >= 0:  # 已過或當前時刻
                    matching.append(item)
        except Exception:
            pass

    return sorted(matching, key=lambda x: x.get("scheduled_time", ""))


# ==================== AnimeDatabase (Unchanged - Works Well) ====================
class AnimeDatabase:
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
                    tags TEXT,
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

            # 消息 ID 追蹤表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_MESSAGES_TABLE} (
                    messageId INTEGER PRIMARY KEY,
                    videoSn INTEGER,
                    animeSn INTEGER,
                    anime_name TEXT,
                    animeName_old TEXT,
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
                    video_sn INTEGER,
                    anime_sn INTEGER,
                    anime_name TEXT,
                    voteType TEXT,
                    vote_type TEXT,
                    userId TEXT,
                    user_hash TEXT,
                    messageId INTEGER,
                    message_id INTEGER,
                    comment TEXT,
                    votedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # KK幣獎勵追踪表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_REWARDS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    messageId INTEGER,
                    message_id INTEGER,
                    rewardType TEXT,
                    reward_type TEXT,
                    reward_amount INTEGER,
                    amount INTEGER,
                    userId TEXT,
                    user_id TEXT,
                    awardedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rewarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 每日時刻檢查歷史表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_CHECK_HISTORY_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    weekStartDate TEXT,
                    dayOfWeek INTEGER,
                    scheduledTime TEXT,
                    checkedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 週表：每週一自動拉取的完整時程表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {ANIME_WEEKLY_SCHEDULE_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    weekStartDate TEXT,
                    dayOfWeek INTEGER,
                    scheduledTime TEXT,
                    videoSn INTEGER,
                    animeData TEXT,
                    pushed INTEGER DEFAULT 0,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(weekStartDate, dayOfWeek, scheduledTime, videoSn)
                )
            """)

            # Schema migration
            self._migrate_schema(cursor)

            # 創建索引
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{NOTIFIED_TABLE}_videoSn ON {NOTIFIED_TABLE}(videoSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_DETAILS_TABLE}_animeSn ON {ANIME_DETAILS_TABLE}(animeSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{EPISODE_STATS_TABLE}_videoSn ON {EPISODE_STATS_TABLE}(videoSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_videoSn ON {ANIME_MESSAGES_TABLE}(videoSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_animeSn ON {ANIME_MESSAGES_TABLE}(animeSn)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_WEEKLY_SCHEDULE_TABLE}_weekStart ON {ANIME_WEEKLY_SCHEDULE_TABLE}(weekStartDate)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_WEEKLY_SCHEDULE_TABLE}_dayTime ON {ANIME_WEEKLY_SCHEDULE_TABLE}(dayOfWeek, scheduledTime)")

    def _migrate_schema(self, cursor):
        """Add missing columns to existing tables (schema migration)"""
        migrations = [
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
            (ANIME_MESSAGES_TABLE, "animeName_old", "TEXT"),
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
            (ANIME_VOTES_TABLE, "video_sn", "INTEGER"),
            (ANIME_VOTES_TABLE, "anime_sn", "INTEGER"),
            (ANIME_VOTES_TABLE, "anime_name", "TEXT"),
            (ANIME_VOTES_TABLE, "voteType", "TEXT"),
            (ANIME_VOTES_TABLE, "vote_type", "TEXT"),
            (ANIME_VOTES_TABLE, "userId", "TEXT"),
            (ANIME_VOTES_TABLE, "user_hash", "TEXT"),
            (ANIME_VOTES_TABLE, "messageId", "INTEGER"),
            (ANIME_VOTES_TABLE, "message_id", "INTEGER"),
            (ANIME_VOTES_TABLE, "comment", "TEXT"),
            (ANIME_VOTES_TABLE, "votedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_VOTES_TABLE, "voted_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
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
            (ANIME_WEEKLY_SCHEDULE_TABLE, "videoSn", "INTEGER"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "animeData", "TEXT"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "pushed", "INTEGER DEFAULT 0"),
            (ANIME_WEEKLY_SCHEDULE_TABLE, "createdAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            (ANIME_DETAILS_TABLE, "animeSn", "INTEGER PRIMARY KEY"),
            (ANIME_DETAILS_TABLE, "name", "TEXT"),
            (ANIME_DETAILS_TABLE, "content", "TEXT"),
            (ANIME_DETAILS_TABLE, "coverUrl", "TEXT"),
            (ANIME_DETAILS_TABLE, "tags", "TEXT"),
            (ANIME_DETAILS_TABLE, "viewCount", "INTEGER DEFAULT 0"),
            (ANIME_DETAILS_TABLE, "score", "REAL DEFAULT 0"),
            (ANIME_DETAILS_TABLE, "updatedAt", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ]

        for table_name, column_name, column_def in migrations:
            try:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [row[1] for row in cursor.fetchall()]
                if column_name not in columns:
                    logger.info(f"[Migration] Adding column {column_name} to {table_name}")
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            except Exception as e:
                logger.warning(f"[Migration] Could not add {column_name} to {table_name}: {e}")

    # ==================== Notification Methods ====================
    def is_notified(self, video_sn: int) -> bool:
        """檢查動畫集數是否已經通知過"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT 1 FROM {NOTIFIED_TABLE} WHERE videoSn = ?", (video_sn,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ [is_notified] Error checking video_sn {video_sn}: {e}", exc_info=True)
            return False

    def add_notified(
        self,
        video_sn: int,
        anime_sn: int,
        anime_name: str,
        volume: str = "",
        cover_url: str = "",
    ) -> bool:
        """標記動畫集數為已通知"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {NOTIFIED_TABLE}
                    (videoSn, animeSn, anime_name, volume, cover_url,
                     animeName, coverUrl)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (video_sn, anime_sn, anime_name, volume, cover_url,
                     anime_name, cover_url),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [add_notified] Error adding notified for video_sn {video_sn}: {e}", exc_info=True)
            return False

    # ==================== Message Methods ====================
    def get_message_info(self, message_id: int) -> Optional[dict]:
        """根據 message_id 取得訊息資訊"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT messageId, videoSn, animeSn, anime_name, animeName_old, channelId
                    FROM {ANIME_MESSAGES_TABLE}
                    WHERE messageId = ?
                    """,
                    (message_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "messageId": row[0],
                        "videoSn": row[1],
                        "animeSn": row[2],
                        "anime_name": row[3],
                        "animeName_old": row[4],
                        "channelId": row[5],
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_message_info] Error for message_id {message_id}: {e}", exc_info=True)
            return None

    def get_video_sn_from_message(self, message_id: int) -> Optional[int]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT videoSn FROM {ANIME_MESSAGES_TABLE} WHERE messageId = ?", (message_id,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"❌ [get_video_sn_from_message] Error for message_id {message_id}: {e}", exc_info=True)
            return None

    def save_message_info(
        self,
        message_id: int,
        video_sn: int,
        anime_sn: int,
        anime_name: str,
        channel_id: int,
    ) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {ANIME_MESSAGES_TABLE}
                    (messageId, videoSn, animeSn, anime_name, animeName_old, channelId,
                     video_sn, anime_sn, anime_name, channel_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (message_id, video_sn, anime_sn, anime_name, anime_name, channel_id,
                     video_sn, anime_sn, anime_name, channel_id),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [save_message_info] Error saving message_id {message_id}: {e}", exc_info=True)
            return False

    # ==================== Schedule Methods ====================
    def get_schedule_video_sns(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> set:
        """根據週表取得特定時段的 videoSn 集合"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT videoSn FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                    """,
                    (week_start_date, day_of_week, scheduled_time),
                )
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"❌ [get_schedule_video_sns] Error: {e}", exc_info=True)
            return set()

    def get_schedule_titles(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> set:
        """根據週表取得特定時段的動畫標題集合（fallback 用）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT json_extract(animeData, '$.title') FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                    """,
                    (week_start_date, day_of_week, scheduled_time),
                )
                return {row[0] for row in cursor.fetchall() if row[0]}
        except Exception as e:
            logger.error(f"❌ [get_schedule_titles] Error: {e}", exc_info=True)
            return set()

    def get_today_schedule(self) -> list:
        """取得今日完整時程表（含 pushed 狀態）"""
        try:
            week_start_date = get_week_start_date(api_week=True)
            now = datetime.now(TW_TZ)
            day_of_week = now.weekday() + 1
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT weekStartDate, dayOfWeek, scheduledTime, videoSn, pushed
                    FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE weekStartDate = ? AND dayOfWeek = ?
                    ORDER BY scheduledTime
                    """,
                    (week_start_date, day_of_week),
                )
                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "weekStartDate": row[0],
                            "dayOfWeek": row[1],
                            "scheduled_time": row[2],
                            "video_sn": row[3],
                            "pushed": bool(row[4]),
                        }
                    )
                return results
        except Exception as e:
            logger.error(f"❌ [get_today_schedule] Error: {e}", exc_info=True)
            return []

    def mark_anime_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str, video_sn: int
    ) -> bool:
        """標記特定時段的特定 videoSn 為已推送"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                    SET pushed = 1
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ? AND videoSn = ?
                    """,
                    (week_start_date, day_of_week, scheduled_time, video_sn),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ [mark_anime_pushed] Error: {e}", exc_info=True)
            return False

    def mark_time_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> bool:
        """標記特定時段所有動畫為已推送（無 videoSn 時）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                    SET pushed = 1
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ?
                    """,
                    (week_start_date, day_of_week, scheduled_time),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ [mark_time_pushed] Error: {e}", exc_info=True)
            return False

    # ==================== Anime Details Cache ====================
    def cache_anime_details(
        self,
        anime_sn: int,
        name: str,
        content: str,
        cover_url: str,
        tags: list,
        view_count: int,
        score: float,
    ) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {ANIME_DETAILS_TABLE}
                    (animeSn, name, content, coverUrl, tags, viewCount, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (anime_sn, name, content, cover_url, json.dumps(tags), view_count, score),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [cache_anime_details] Error: {e}", exc_info=True)
            return False

    def get_anime_details(self, anime_sn: int) -> Optional[dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT name, content, coverUrl, tags, viewCount, score
                    FROM {ANIME_DETAILS_TABLE}
                    WHERE animeSn = ?
                    """,
                    (anime_sn,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "animeSn": anime_sn,
                        "title": row[0],
                        "name": row[0],
                        "content": row[1],
                        "cover_url": row[2],
                        "tags": json.loads(row[3]) if row[3] else [],
                        "view_count": row[4],
                        "score": row[5],
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_anime_details] Error for anime_sn {anime_sn}: {e}", exc_info=True)
            return None

    # ==================== Episode Stats ====================
    def record_episode_stats(
        self,
        video_sn: int,
        anime_sn: int,
        episode_num: str,
        views: int,
        score: float = 0,
    ) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {EPISODE_STATS_TABLE}
                    (videoSn, animeSn, episodeNum, views, score)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (video_sn, anime_sn, episode_num, views, score),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [record_episode_stats] Error: {e}", exc_info=True)
            return False

    def get_top_anime_by_views(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                time_condition = ""
                params: list = []
                if start_time and end_time:
                    time_condition = " AND es.recordedAt BETWEEN ? AND ?"
                    params = [
                        start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    ]

                query = f"""
                    SELECT d.animeSn, d.name, SUM(es.views) as total_views, COUNT(es.videoSn) as episode_count
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
                    results.append(
                        {
                            "anime_sn": row[0],
                            "name": row[1],
                            "total_views": row[2] if row[2] is not None else 0,
                            "total_episodes": row[3] if row[3] is not None else 0,
                        }
                    )
                return results
        except Exception as e:
            logger.error(f"❌ [get_top_anime_by_views] Error: {e}", exc_info=True)
            return []

    def get_multi_episode_anime_for_chart(
        self,
        limit: int = 10,
        min_episodes: int = 2,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                time_condition = ""
                params: list = []
                if start_time and end_time:
                    time_condition = " AND es.recordedAt BETWEEN ? AND ?"
                    params = [
                        start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    ]

                query = f"""
                    SELECT d.animeSn, d.name, es.videoSn, es.episodeNum, es.views
                    FROM {EPISODE_STATS_TABLE} es
                    JOIN {ANIME_DETAILS_TABLE} d ON es.animeSn = d.animeSn
                    WHERE 1=1 {time_condition}
                    AND d.animeSn IN (
                        SELECT animeSn FROM {EPISODE_STATS_TABLE}
                        GROUP BY animeSn HAVING COUNT(*) >= ?
                    )
                    ORDER BY d.animeSn, es.videoSn
                """
                params.append(min_episodes)
                params.append(limit * 10)
                cursor.execute(query, params)

                anime_dict = {}
                for row in cursor.fetchall():
                    anime_sn, name, video_sn, episode_num, views = row
                    if anime_sn not in anime_dict:
                        anime_dict[anime_sn] = {"anime_sn": anime_sn, "name": name, "episodes": []}
                    anime_dict[anime_sn]["episodes"].append({"num": episode_num, "views": views})

                return list(anime_dict.values())[:limit]
        except Exception as e:
            logger.error(f"❌ [get_multi_episode_anime_for_chart] Error: {e}", exc_info=True)
            return []

    def get_anime_details_by_videosn(self, video_sn: int) -> Optional[dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT animeSn, episodeNum FROM {EPISODE_STATS_TABLE} WHERE videoSn = ?",
                    (video_sn,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                anime_sn, episode_num = row
                cursor.execute(
                    f"""
                    SELECT name, content, coverUrl, tags, viewCount, score
                    FROM {ANIME_DETAILS_TABLE} WHERE animeSn = ?
                    """,
                    (anime_sn,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "videoSn": video_sn,
                        "animeSn": anime_sn,
                        "title": row[0],
                        "name": row[0],
                        "content": row[1],
                        "cover_url": row[2],
                        "tags": json.loads(row[3]) if row[3] else [],
                        "view_count": row[4],
                        "score": row[5],
                        "volume": episode_num or "",
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_anime_details_by_videosn] Error for video_sn {video_sn}: {e}", exc_info=True)
            return None

    def get_anime_statistics(self, anime_sn: int) -> Optional[dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT totalViews, avgViews, totalEpisodes, latestScore FROM {ANIME_STATS_TABLE} WHERE animeSn = ?",
                    (anime_sn,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "total_views": row[0] if row[0] is not None else 0,
                        "avg_views": row[1] if row[1] is not None else 0.0,
                        "total_episodes": row[2] if row[2] is not None else 0,
                        "latest_score": row[3] if row[3] is not None else 0.0,
                    }
                return None
        except Exception as e:
            logger.error(f"❌ [get_anime_statistics] Error for anime_sn {anime_sn}: {e}", exc_info=True)
            return None

    # ==================== Vote & Reward Methods ====================
    def is_reward_already_given(self, user_id: int, message_id: int, reward_type: str) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT 1 FROM {ANIME_REWARDS_TABLE} WHERE userId = ? AND messageId = ? AND rewardType = ? LIMIT 1",
                    (str(user_id), message_id, reward_type),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ [is_reward_already_given] Error: {e}", exc_info=True)
            return False

    def record_reward(self, message_id: int, reward_type: str, reward_amount: int, user_id: str) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT INTO {ANIME_REWARDS_TABLE}
                    (message_id, messageId, reward_type, rewardType, reward_amount, amount, user_id, userId, awarded_at, rewardedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (message_id, message_id, reward_type, reward_type, reward_amount, reward_amount, user_id, user_id),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ [record_reward] Error: {e}", exc_info=True)
            return False

    def record_vote(
        self,
        video_sn: int,
        anime_sn: int,
        message_id: int,
        vote_type: str,
        comment: Optional[str] = None,
        user_hash: Optional[str] = None,
        anime_name: str = "",
    ) -> bool:
        if not anime_name:
            anime_details = self.get_anime_details(anime_sn)
            if anime_details:
                anime_name = anime_details.get("title", "") or anime_details.get("name", "")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT INTO {ANIME_VOTES_TABLE}
                    (videoSn, animeSn, video_sn, anime_sn, anime_name, vote_type, voteType, user_hash, userId, message_id, messageId, comment, voted_at, votedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (
                        video_sn,
                        anime_sn,
                        video_sn,
                        anime_sn,
                        anime_name,
                        vote_type,
                        vote_type,
                        user_hash,
                        user_hash,
                        message_id,
                        message_id,
                        comment,
                    ),
                )
                conn.commit()
                logger.info(f"✅ [record_vote] video_sn={video_sn}, anime_sn={anime_sn}, vote_type={vote_type}")
                return True
        except Exception as e:
            logger.error(f"❌ [record_vote] Error: {e}", exc_info=True)
            return False

    def get_vote_stats(self, message_id: int) -> Dict[str, int]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT voteType, COUNT(*) FROM {ANIME_VOTES_TABLE} WHERE messageId = ? AND voteType != 'comment' GROUP BY voteType",
                    (message_id,),
                )
                return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"❌ [get_vote_stats] Error: {e}", exc_info=True)
            return {}

    def get_vote_comments(self, message_id: int, limit: int = 5) -> List[str]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT comment FROM {ANIME_VOTES_TABLE} WHERE messageId = ? AND voteType = 'comment' AND comment IS NOT NULL ORDER BY votedAt DESC LIMIT ?",
                    (message_id, limit),
                )
                return [row[0] for row in cursor.fetchall() if row[0]]
        except Exception as e:
            logger.error(f"❌ [get_vote_comments] Error: {e}", exc_info=True)
            return []

    def get_weekly_vote_stats(self) -> Dict[int, Dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now(TW_TZ)
                week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                cursor.execute(
                    f"SELECT animeSn, voteType, COUNT(*) FROM {ANIME_VOTES_TABLE} WHERE votedAt >= ? AND voteType != 'comment' GROUP BY animeSn, voteType",
                    (week_start.strftime("%Y-%m-%d %H:%M:%S"),),
                )
                stats: Dict[int, Dict] = {}
                for anime_sn, vote_type, count in cursor.fetchall():
                    if anime_sn not in stats:
                        stats[anime_sn] = {"total_votes": 0, "votes": {}}
                    stats[anime_sn]["votes"][vote_type] = count
                    stats[anime_sn]["total_votes"] += count
                return stats
        except Exception as e:
            logger.error(f"❌ [get_weekly_vote_stats] Error: {e}", exc_info=True)
            return {}


# ==================== AnimePushCore (Refactored - Simplified) ====================
class AnimePushCore:
    """動畫推送核心邏輯 - 簡化版精準派發器

    核心原則：
    1. 逐時段獨立鎖：防止 dispatcher + catchup 同時推同一時段
    2. 單一入口：send_anime_push 供所有路徑呼叫（dispatcher、catchup、手動指令）
    3. 無預熱：時間到 → 查 API → 推動畫
    4. 簡化 fallback：videoSn 匹配 → title 匹配（可選） → notified 表去重
    5. 重試機制：最多 3 次，失敗則標記 exhausted 避免無限重試
    """

    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 30

    def __init__(self, db_path: str):
        self.db = AnimeDatabase(db_path)
        self.bot: Optional[discord.Client] = None
        self._view_factory = None  # 由外部注入 generate_anime_view
        self._embed_factory = None  # 由外部注入 generate_anime_embed

        # 逐時段獨立鎖：key = (week_start_date, day_of_week, scheduled_time)
        self._push_locks: Dict[tuple, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # 保護 _push_locks 字典本身

        # 重試計數：key = (week_start_date, day_of_week, scheduled_time, video_sn)
        self._retry_counts: Dict[tuple, int] = {}

    def set_bot_and_db(self, bot: discord.Client, db: AnimeDatabase):
        """由 AnimeTracker 呼叫注入 bot 和 db"""
        self.bot = bot
        self.db = db

    def set_view_factory(self, factory):
        """注入視圖生成工廠函數"""
        self._view_factory = factory

    def set_embed_factory(self, factory):
        """注入 embed 生成工廠函數"""
        self._embed_factory = factory

    # ---------- Lock Management ----------
    async def _get_push_lock(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> asyncio.Lock:
        """取得該時段的專屬鎖（逐時段獨立鎖）"""
        key = (week_start_date, day_of_week, scheduled_time)
        async with self._locks_lock:
            if key not in self._push_locks:
                self._push_locks[key] = asyncio.Lock()
            return self._push_locks[key]

    def _get_retry_key(self, week_start_date: str, day_of_week: int, scheduled_time: str, video_sn: int) -> tuple:
        return (week_start_date, day_of_week, scheduled_time, video_sn)

    def _increment_retry(self, key: tuple) -> int:
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
        return self._retry_counts[key]

    def _reset_retry(self, key: tuple):
        self._retry_counts.pop(key, None)

    def _is_exhausted(self, key: tuple) -> bool:
        return self._retry_counts.get(key, 0) >= self.MAX_RETRIES

    # ---------- Main Entry Point ----------
    async def send_anime_push(
        self,
        scheduled_time: str,
        channel_id: int,
        day_of_week: Optional[int] = None,
        week_start_date: Optional[str] = None,
    ) -> bool:
        """統一推送入口：時間到 → 查 API → 推動畫

        Args:
            scheduled_time: 推送時刻 "HH:MM"
            channel_id: Discord 頻道 ID
            day_of_week: 1=週一~7=週日，預設為今天
            week_start_date: 週起始日期 "YYYY-MM-DD"，預設為本週（API 週語義）

        Returns:
            bool: 是否有成功推送至少一筆
        """
        # 計算預設值
        now = datetime.now(TW_TZ)
        if day_of_week is None:
            day_of_week = now.weekday() + 1
        if week_start_date is None:
            week_start_date = get_week_start_date(now, api_week=True)

        logger.info(f"🚀 [send_anime_push] 開始處理 {scheduled_time} (week={week_start_date}, day={day_of_week})")

        # 取得該時段的專屬鎖
        push_lock = await self._get_push_lock(week_start_date, day_of_week, scheduled_time)

        async with push_lock:
            logger.info(f"🔒 [send_anime_push] 獲得鎖 {scheduled_time}")

            # 鎖內二次檢查：重讀週表確認仍有未推送項目
            today_schedule = self.db.get_today_schedule()
            expected_video_sns = self.db.get_schedule_video_sns(week_start_date, day_of_week, scheduled_time)

            if not expected_video_sns:
                logger.info(f"📭 [send_anime_push] {scheduled_time} 週表無對應 videoSn，標記 exhausted 跳過")
                self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
                return False

            # 找出尚未推送的 videoSn
            pushed_video_sns = {
                item["video_sn"] for item in today_schedule
                if item["scheduled_time"] == scheduled_time and item.get("pushed")
            }
            pending_video_sns = expected_video_sns - pushed_video_sns

            if not pending_video_sns:
                logger.info(f"⏭️ [send_anime_push] {scheduled_time} 所有預期動畫已推送 ({expected_video_sns})，跳過")
                return False

            logger.info(f"📋 [send_anime_push] {scheduled_time} 待推送 videoSn: {pending_video_sns}")

            # 檢查 bot 就緒
            if self.bot is None:
                logger.error(f"❌ [send_anime_push] Bot 未初始化")
                return False
            await self.bot.wait_until_ready()

            # 取得頻道
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.warning(f"⚠️ [send_anime_push] 頻道 {channel_id} 不存在，標記所有 pending 為 exhausted")
                for vsn in pending_video_sns:
                    self.db.mark_anime_pushed(week_start_date, day_of_week, scheduled_time, vsn)
                return False

            # 呼叫 API 獲取最新動畫
            episodes = await self._fetch_new_anime_from_api()
            if not episodes:
                logger.warning(f"⚠️ [send_anime_push] {scheduled_time} API 無回應，將重試")
                return False  # 不標記，讓上層重試

            # 過濾：只保留今日上架的集數
            today_str = now.strftime("%m/%d")
            today_episodes = [ep for ep in episodes if ep.get("upTime", "").strip() == today_str]

            if not today_episodes:
                logger.warning(f"⚠️ [send_anime_push] {scheduled_time} 今日無新番集數 (API 回傳 {len(episodes)} 筆 but upTime!=today)")
                return False  # 不標記，API 可能尚未更新

            logger.info(f"📅 [send_anime_push] 今日集數過濾: {len(episodes)} -> {len(today_episodes)} 筆")

            # ========== 核心匹配邏輯：videoSn 優先，title fallback ==========
            new_episodes = []
            matched_by_videosn = set()

            # 1. videoSn 精確匹配
            for ep in today_episodes:
                video_sn = ep.get("videoSn")
                if not video_sn:
                    continue
                try:
                    video_sn_int = int(video_sn)
                except (ValueError, TypeError):
                    continue
                if video_sn_int in pending_video_sns:
                    new_episodes.append(ep)
                    matched_by_videosn.add(video_sn_int)

            # 2. title fallback（若 videoSn 全部匹配失敗）
            if not new_episodes:
                expected_titles = self.db.get_schedule_titles(week_start_date, day_of_week, scheduled_time)
                if expected_titles:
                    logger.info(f"🔄 [send_anime_push] {scheduled_time} videoSn 匹配失敗，改用 title fallback")
                    for ep in today_episodes:
                        ep_title = (ep.get("title") or "").strip()
                        if ep_title in expected_titles:
                            video_sn = ep.get("videoSn")
                            try:
                                video_sn_int = int(video_sn) if video_sn else 0
                            except (ValueError, TypeError):
                                video_sn_int = 0
                            if video_sn_int in pending_video_sns and not self.db.is_notified(video_sn_int):
                                new_episodes.append(ep)
                                logger.info(f"  ✅ title 匹配: {ep_title} (videoSn={video_sn_int})")

            # 3. 最後防線：notified 表去重（週表外新增的新番）
            if not new_episodes:
                logger.info(f"🔍 [send_anime_push] {scheduled_time} 週表匹配完全失敗，啟用 notified 去重模式")
                for ep in today_episodes:
                    video_sn = ep.get("videoSn")
                    if not video_sn:
                        continue
                    try:
                        video_sn_int = int(video_sn)
                    except (ValueError, TypeError):
                        continue
                    if video_sn_int in pending_video_sns and not self.db.is_notified(video_sn_int):
                        new_episodes.append(ep)
                        logger.info(f"🔄 發現週表外新番: {ep.get('title')} (videoSn={video_sn_int})")

            if not new_episodes:
                logger.info(f"📭 [send_anime_push] {scheduled_time} 無匹配的新番需推送")
                # 判斷是否 exhausted：所有 pending 都已重試滿 MAX_RETRIES 次
                all_exhausted = True
                for vsn in pending_video_sns:
                    key = self._get_retry_key(week_start_date, day_of_week, scheduled_time, vsn)
                    if not self._is_exhausted(key):
                        all_exhausted = False
                        self._increment_retry(key)
                        logger.info(f"⏳ [send_anime_push] {scheduled_time} videoSn={vsn} 第 {self._retry_counts[key]} 次重試")
                        break

                if all_exhausted:
                    logger.info(f"🏁 [send_anime_push] {scheduled_time} 所有 pending 已達最大重試次數，標記 exhausted")
                    for vsn in pending_video_sns:
                        self.db.mark_anime_pushed(week_start_date, day_of_week, scheduled_time, vsn)
                        self._reset_retry(self._get_retry_key(week_start_date, day_of_week, scheduled_time, vsn))
                return False

            # ========== 發送推送 ==========
            sent_count = 0
            pushed_this_run = set()

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
                        logger.warning(f"⚠️ [send_anime_push] Skip invalid video_sn: {episode}")
                        continue

                    # 生成 embed 和 view
                    embed = await self._generate_anime_embed(episode)
                    if not embed:
                        continue

                    view = await self._generate_anime_view(episode)
                    if view is None:
                        logger.warning(f"⚠️ [send_anime_push] No view for episode {video_sn}, skipping")
                        continue

                    # 發送訊息（silent=True 靜音推送）
                    message = await channel.send(embed=embed, view=view, silent=True)

                    # 存入 view 的 message_id 供 modal 使用
                    if view and hasattr(view, "message_id"):
                        view.message_id = message.id

                    # 存儲訊息資訊
                    self.db.save_message_info(message.id, video_sn, anime_sn, title, channel_id)
                    self.db.add_notified(video_sn, anime_sn, title, episode.get("volume", ""), episode.get("cover", ""))

                    # 註冊永久視圖
                    if view and self.bot is not None:
                        self.bot.add_view(view, message_id=message.id)

                    sent_count += 1
                    pushed_this_run.add(video_sn)
                    logger.info(f"✅ [send_anime_push] 已推送: {title} (videoSn={video_sn}, animeSn={anime_sn})")

                except Exception as e:
                    logger.error(f"❌ [send_anime_push] Error sending episode {episode.get('videoSn')}: {e}", exc_info=True)
                    continue

            # ========== 標記成功推送的 videoSn ==========
            for vsn in pushed_this_run:
                self.db.mark_anime_pushed(week_start_date, day_of_week, scheduled_time, vsn)
                self._reset_retry(self._get_retry_key(week_start_date, day_of_week, scheduled_time, vsn))
                logger.info(f"✅ [send_anime_push] 已標記 {scheduled_time} videoSn={vsn} 為已推送")

            # 檢查是否該時段所有預期動畫都已推送完成
            today_schedule = self.db.get_today_schedule()
            all_pushed_video_sns = {
                item["video_sn"] for item in today_schedule
                if item["scheduled_time"] == scheduled_time and item.get("pushed")
            }

            if expected_video_sns.issubset(all_pushed_video_sns):
                logger.info(f"✅ [send_anime_push] {scheduled_time} 所有預期動畫已推送完成 ({expected_video_sns})")
            else:
                remaining = expected_video_sns - all_pushed_video_sns
                logger.info(f"⏳ [send_anime_push] {scheduled_time} 仍有 {len(remaining)} 部待推送: {remaining}")

            return sent_count > 0

    # ---------- API & Generation Methods ----------
    async def _fetch_new_anime_from_api(self) -> List[Dict]:
        """從 API 獲取新番資料"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    new_anime = data.get("data", {}).get("newAnime")
                    if not new_anime or "date" not in new_anime:
                        return []
                    return new_anime["date"]
        except Exception as e:
            logger.error(f"❌ [_fetch_new_anime_from_api] Error: {e}", exc_info=True)
            return []

    async def _generate_anime_embed(self, episode: Dict) -> Optional[discord.Embed]:
        """生成動畫嵌入訊息"""
        if self._embed_factory:
            try:
                return await self._embed_factory(episode)
            except Exception as e:
                logger.error(f"❌ [_generate_anime_embed] Factory error: {e}", exc_info=True)
        # Fallback: 簡易 embed
        try:
            embed = discord.Embed(
                title=episode.get("title", "未知標題"),
                description=episode.get("content", "")[:500],
                color=discord.Color.from_rgb(178, 108, 196),
                timestamp=datetime.now(TW_TZ),
            )
            if episode.get("cover"):
                embed.set_thumbnail(url=episode["cover"])
            embed.add_field(name="集數", value=episode.get("volume", "?"), inline=True)
            embed.add_field(name="觀看數", value=f"{episode.get('viewCount', 0):,}", inline=True)
            embed.set_footer(text="資料來源：巴哈姆特動畫瘋")
            return embed
        except Exception as e:
            logger.error(f"❌ [_generate_anime_embed] Fallback error: {e}", exc_info=True)
            return None

    async def _generate_anime_view(self, episode: Dict) -> Optional[discord.ui.View]:
        """生成動畫視圖"""
        if self._view_factory:
            try:
                return await self._view_factory(episode)
            except Exception as e:
                logger.error(f"❌ [_generate_anime_view] Factory error: {e}", exc_info=True)
        return None


# ==================== Backward Compatibility ====================
# 保留原有函數名稱供舊代碼呼叫
async def fetch_new_anime_from_api() -> List[Dict]:
    """向後相容：直接呼叫 AnimePushCore 的方法"""
    core = AnimePushCore("user_data.db")
    return await core._fetch_new_anime_from_api()
