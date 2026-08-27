"""
動畫推送核心模組 - 極簡版

核心邏輯：時間到 → 查 API → 推送 → 標記 push=1
補推邏輯：偵測 push=0 且時間已過 → 未超過 1 小時 → 推送；超過 1 小時 → 標記 pushed 並放棄

移除所有過度設計：retry/lock/exhausted/catchup 等複雜機制
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo

import aiohttp
import discord

# 導入新的網頁爬蟲模組
from .bahamut_web_scraper import fetch_new_anime_from_web

logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333
ANIME_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"

# 完整瀏覽器指紋 Header（繞過 Cloudflare WAF）
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://ani.gamer.com.tw/",
    "Origin": "https://ani.gamer.com.tw",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-CH-UA": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-CH-UA-Arch": '"x86_64"',
    "Sec-CH-UA-Bitness": '"64"',
    "Sec-CH-UA-Full-Version": '"127.0.0.0"',
    "Sec-CH-UA-Platform-Version": '"10.0.0"',
    "Sec-CH-UA-Full-Version-List": '"Not)A;Brand";v="99.0.0.0", "Google Chrome";v="127.0.0.0", "Chromium";v="127.0.0.0"',
}


# ========== 相容性介面：AnimeDatabase 類別 (需在 AnimePushCore 之前定義，供 anime_tracker 匯入) ==========

# 匯入 API 常數以供相容性使用（實際定義在 anime_scraper.py 中）
try:
    from .anime_scraper import API_ENDPOINT, API_TIMEOUT, API_HEADERS
except ImportError:
    # 後備方案：如果無法從 anime_scraper 導入，則定義預設值
    API_ENDPOINT = "https://api.gamer.com.tw/anime/v1/anime_list.php"
    API_TIMEOUT = 15
    API_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": "https://ani.gamer.com.tw/",
        "Origin": "https://ani.gamer.com.tw",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-CH-UA": '"Not A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-CH-UA-Arch": '"x86_64"',
        "Sec-CH-UA-Bitness": '"64"',
        "Sec-CH-UA-Full-Version": '"127.0.0.0"',
        "Sec-CH-UA-Platform-Version": '"10.0.0"',
        "Sec-CH-UA-Full-Version-List": '"Not A;Brand";v="99.0.0.0", "Google Chrome";v="127.0.0.0", "Chromium";v="127.0.0.0"',
    }


class AnimeDatabase:
    """相容性包裝：將舊版 AnimeDatabase 介面委託給 db adapter"""

    def __init__(self, db):
        self.db = db

    async def fetchone(self, query: str, params: tuple = ()):
        """通用查詢單行結果 - 委託給底層實現"""
        return await self.db.fetchone(query, params)

    # ---- 通知/推送相關 ----
    def is_notified(self, video_sn: int) -> bool:
        return self.db.is_notified(video_sn)

    def add_notified(
        self,
        video_sn: int,
        anime_sn: int,
        title: str,
        volume: str = "",
        cover: str = "",
    ) -> bool:
        return self.db.add_notified(video_sn, anime_sn, title, volume, cover)

    def mark_time_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> bool:
        return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)

    def mark_anime_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str, video_sn: int
    ) -> bool:
        return self.db.mark_anime_pushed(
            week_start_date, day_of_week, scheduled_time, video_sn
        )

    def save_message_info(
        self, message_id: int, video_sn: int, anime_sn: int, title: str, channel_id: int
    ) -> bool:
        return self.db.save_message_info(
            message_id, video_sn, anime_sn, title, channel_id
        )

    # ---- 時程查詢 ----
    def get_today_schedule(self, week_start_date: str | None = None) -> list:
        return self.db.get_today_schedule(week_start_date)

    def get_schedule_video_sns(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> set:
        return self.db.get_schedule_video_sns(
            week_start_date, day_of_week, scheduled_time
        )

    # ---- 獎勵系統 ----
    def is_reward_already_given(
        self, user_id: int, message_id: int, reward_type: str
    ) -> bool:
        return self.db.is_reward_already_given(user_id, message_id, reward_type)

    def record_reward(
        self, user_id: int, message_id: int, reward_type: str, reward_amount: int
    ) -> bool:
        return self.db.record_reward(user_id, message_id, reward_type, reward_amount)

    # ---- 投票系統 ----
    def record_vote(
        self,
        video_sn: int,
        anime_sn: int,
        message_id: int,
        vote_type: str,
        comment: str = None,
        user_hash: str = None,
        anime_name: str = "",
    ) -> bool:
        return self.db.record_vote(
            video_sn, anime_sn, message_id, vote_type, comment, user_hash, anime_name
        )

    def get_vote_stats(self, message_id: int) -> dict:
        return self.db.get_vote_stats(message_id)

    def get_vote_comments(self, message_id: int, limit: int = 5) -> list:
        return self.db.get_vote_comments(message_id, limit)

    def get_weekly_vote_stats(self) -> dict:
        return self.db.get_weekly_vote_stats()

    # ---- 統計/快取 ----
    def record_episode_stats(
        self, video_sn: int, anime_sn: int, episode_num: str, views: int, score: float
    ) -> bool:
        return self.db.record_episode_stats(
            video_sn, anime_sn, episode_num, views, score
        )

    def get_anime_details(self, anime_sn: int) -> dict:
        return self.db.get_anime_details(anime_sn)

    def cache_anime_details(
        self,
        anime_sn: int,
        title: str,
        content: str,
        cover: str,
        tags: list,
        views: int,
        score: float,
    ) -> bool:
        return self.db.cache_anime_details(
            anime_sn, title, content, cover, tags, views, score
        )

    # ---- 統計查詢 (for ranking_stats) ----
    def get_anime_statistics(self, anime_sn: int) -> dict | None:
        return self.db.get_anime_statistics(anime_sn)

    def get_top_anime_by_views(
        self,
        limit: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        return self.db.get_top_anime_by_views(limit, start_time, end_time)

    def get_multi_episode_anime_for_chart(
        self,
        limit: int = 10,
        min_episodes: int = 1,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        return self.db.get_multi_episode_anime_for_chart(
            limit, min_episodes, start_time, end_time
        )

    @property
    def db_path(self) -> str:
        return self.db.db_path

    # ---- 維護 ----
    def save_weekly_schedule(self, week_start_date: str, schedule_data: list) -> bool:
        return self.db.save_weekly_schedule(week_start_date, schedule_data)

    def clean_orphaned_records(self, week_start_date: str) -> dict:
        return self.db.clean_orphaned_records(week_start_date)

    def cleanup_old_weeks(self) -> int:
        return self.db.cleanup_old_weeks()


class AnimeDBImpl:
    """AnimeDatabase 的完整 SQLite 實現 - 提供所有必要的方法"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """初始化所有必要的資料表"""
        conn = self._get_conn()
        c = conn.cursor()

        # anime_notified 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_notified (
                videoSn INTEGER PRIMARY KEY,
                animeSn INTEGER NOT NULL,
                anime_name TEXT NOT NULL,
                volume TEXT,
                cover_url TEXT,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                animeName TEXT,
                coverUrl TEXT,
                notifiedAt TIMESTAMP
            )
        """)

        # anime_votes 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_sn INTEGER NOT NULL,
                anime_sn INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                vote_type TEXT NOT NULL,
                comment TEXT,
                user_hash TEXT,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                animeName TEXT,
                voteType TEXT,
                userId TEXT,
                messageId INTEGER,
                votedAt TIMESTAMP,
                anime_name TEXT
            )
        """)

        # anime_rewards 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                reward_type TEXT NOT NULL,
                reward_amount INTEGER NOT NULL,
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                messageId INTEGER,
                rewardType TEXT,
                amount INTEGER,
                userId TEXT,
                rewardedAt TIMESTAMP,
                UNIQUE(user_id, message_id, reward_type)
            )
        """)

        # anime_messages 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_messages (
                messageId INTEGER PRIMARY KEY,
                videoSn INTEGER NOT NULL,
                animeSn INTEGER NOT NULL,
                animeName_old TEXT NOT NULL,
                channelId INTEGER NOT NULL,
                createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                anime_name TEXT,
                video_sn INTEGER,
                anime_sn INTEGER,
                message_id INTEGER,
                channel_id INTEGER,
                created_at TEXT
            )
        """)

        # anime_weekly_schedule 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_weekly_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weekStartDate TEXT NOT NULL,
                dayOfWeek INTEGER NOT NULL,
                scheduledTime TEXT NOT NULL,
                pushed INTEGER DEFAULT 0,
                animeData TEXT,
                videoSn INTEGER,
                createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # anime_details_cache 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_details_cache (
                animeSn INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                tags TEXT,
                popular INTEGER,
                score REAL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                coverUrl TEXT,
                viewCount INTEGER DEFAULT 0,
                updatedAt TIMESTAMP,
                cover_url TEXT,
                description TEXT,
                createdAt TEXT,
                cover TEXT,
                created_at TEXT,
                name TEXT
            )
        """)

        # episode_statistics 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS episode_statistics (
                videoSn INTEGER PRIMARY KEY,
                animeSn INTEGER NOT NULL,
                episode_num TEXT,
                views INTEGER,
                score REAL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                episodeNum TEXT,
                recordedAt TIMESTAMP
            )
        """)

        # anime_statistics 表
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_statistics (
                animeSn INTEGER PRIMARY KEY,
                anime_name TEXT NOT NULL,
                total_episodes INTEGER DEFAULT 0,
                avg_views REAL DEFAULT 0,
                avg_score REAL DEFAULT 0,
                total_views INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                totalEpisodes INTEGER DEFAULT 0,
                totalViews INTEGER DEFAULT 0,
                avgViews REAL DEFAULT 0,
                latestScore REAL DEFAULT 0,
                updatedAt TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _get_conn(self):
        """獲取連線，啟用 WAL 模式和 busy_timeout 避免鎖定問題"""
        import sqlite3

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = None
        conn.text_factory = bytes
        # 啟用 WAL 模式：讀取不阻塞寫入，寫入不阻塞讀取
        conn.execute("PRAGMA journal_mode=WAL")
        # 設定 30 秒等待超時，避免無限阻塞
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # ---- 通知/推送相關 ----
    def is_notified(self, video_sn: int) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT 1 FROM anime_notified WHERE video_sn=?", (video_sn,))
        row = c.fetchone()
        conn.close()
        return row is not None

    def add_notified(
        self,
        video_sn: int,
        anime_sn: int,
        title: str,
        volume: str = "",
        cover: str = "",
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT OR IGNORE INTO anime_notified
               (video_sn, anime_sn, anime_name, volume, cover_url, notified_at, animeName, coverUrl, notifiedAt)
               VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'))""",
            (video_sn, anime_sn, title, volume, cover, title, cover, cover),
        )
        conn.commit()
        conn.close()
        return True

    def mark_time_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> bool:
        """標記某時段所有動畫為已推送"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE anime_weekly_schedule SET pushed=1 WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=? AND pushed=0",
            (week_start_date, day_of_week, scheduled_time),
        )
        conn.commit()
        conn.close()
        return True

    def mark_anime_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str, video_sn: int
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE anime_weekly_schedule SET pushed=1 WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=? AND videoSn=?",
            (week_start_date, day_of_week, scheduled_time, video_sn),
        )
        conn.commit()
        conn.close()
        return True

    def save_message_info(
        self, message_id: int, video_sn: int, anime_sn: int, title: str, channel_id: int
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO anime_messages (messageId, videoSn, animeSn, animeName_old, channelId) VALUES (?, ?, ?, ?, ?)",
            (message_id, video_sn, anime_sn, title, channel_id),
        )
        conn.commit()
        conn.close()
        return True

    # ---- 時程查詢 ----
    def get_today_schedule(self, week_start_date: str | None = None) -> list:
        """獲取今天的時程表（從週表中） - 可選擇按 week_start_date 過濾

        Args:
            week_start_date: 週起始日期 "YYYY-MM-DD"，若不提供則使用當前週 (api_week=True)
        """
        from datetime import datetime
        import json
        from .push_core import get_week_start_date, TW_TZ

        if week_start_date is None:
            week_start_date = get_week_start_date(datetime.now(TW_TZ), api_week=True)

        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT videoSn, weekStartDate, dayOfWeek, scheduledTime, pushed, animeData FROM anime_weekly_schedule WHERE weekStartDate=?",
            (week_start_date,),
        )
        rows = c.fetchall()
        conn.close()

        result = []
        for row in rows:
            (
                video_sn,
                week_start_date_db,
                day_of_week,
                scheduled_time,
                pushed,
                anime_data_raw,
            ) = row

            # 解析可能為 bytes 的字串欄位
            def decode_if_bytes(val):
                if isinstance(val, bytes):
                    return val.decode("utf-8", errors="replace")
                return val

            item = {
                "video_sn": video_sn,
                "week_start_date": decode_if_bytes(week_start_date_db),
                "day_of_week": day_of_week,
                "scheduled_time": decode_if_bytes(scheduled_time),
                "pushed": bool(pushed) if pushed is not None else False,
            }
            if anime_data_raw:
                try:
                    if isinstance(anime_data_raw, bytes):
                        anime_data_raw = anime_data_raw.decode(
                            "utf-8", errors="replace"
                        )
                    anime_data = json.loads(anime_data_raw)
                    item["anime_data"] = anime_data
                    # 從 anime_data 提取 anime_sn (支援 camelCase 和 snake_case)
                    item["anime_sn"] = anime_data.get("animeSn") or anime_data.get("anime_sn")
                except Exception as e:
                    logger.warning(f"animeData 解析失敗 videoSn={video_sn}: {e}")
                    item["anime_data"] = {}
                    item["anime_sn"] = None
            else:
                item["anime_data"] = {}
                item["anime_sn"] = None
            result.append(item)
        return result

    def get_schedule_video_sns(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> set:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT videoSn FROM anime_weekly_schedule WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?",
            (week_start_date, day_of_week, scheduled_time),
        )
        rows = c.fetchall()
        conn.close()
        return {row[0] for row in rows if row[0] is not None}

    # ---- 獎勵系統 ----
    def is_reward_already_given(
        self, user_id: int, message_id: int, reward_type: str
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT 1 FROM anime_rewards WHERE user_id=? AND message_id=? AND reward_type=?",
            (user_id, message_id, reward_type),
        )
        row = c.fetchone()
        conn.close()
        return row is not None

    def record_reward(
        self, user_id: int, message_id: int, reward_type: str, reward_amount: int
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO anime_rewards (user_id, message_id, reward_type, reward_amount, awarded_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (user_id, message_id, reward_type, reward_amount),
        )
        conn.commit()
        conn.close()
        return True

    # ---- 投票系統 ----
    def record_vote(
        self,
        video_sn: int,
        anime_sn: int,
        message_id: int,
        vote_type: str,
        comment: str = None,
        user_hash: str = None,
        anime_name: str = "",
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO anime_votes
               (video_sn, anime_sn, message_id, vote_type, comment, user_hash, anime_name, voted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (video_sn, anime_sn, message_id, vote_type, comment, user_hash, anime_name),
        )
        conn.commit()
        conn.close()
        return True

    def get_vote_stats(self, message_id: int) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT vote_type, COUNT(*) as count FROM anime_votes WHERE message_id=? GROUP BY vote_type",
            (message_id,),
        )
        rows = c.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    def get_vote_comments(self, message_id: int, limit: int = 5) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT user_hash, comment, vote_type, anime_name, voted_at FROM anime_votes WHERE message_id=? AND comment IS NOT NULL AND comment != '' ORDER BY voted_at DESC LIMIT ?",
            (message_id, limit),
        )
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            user_hash, comment, vote_type, anime_name, voted_at = row
            result.append(
                {
                    "user_hash": user_hash,
                    "comment": (
                        comment
                        if isinstance(comment, str)
                        else comment.decode("utf-8", errors="replace")
                    ),
                    "vote_type": (
                        vote_type
                        if isinstance(vote_type, str)
                        else vote_type.decode("utf-8", errors="replace")
                    ),
                    "anime_name": (
                        anime_name
                        if isinstance(anime_name, str)
                        else anime_name.decode("utf-8", errors="replace")
                    ),
                    "created_at": (
                        voted_at
                        if isinstance(voted_at, str)
                        else voted_at.decode("utf-8", errors="replace")
                    ),
                }
            )
        return result

    def get_weekly_vote_stats(self) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT vote_type, COUNT(*) as count FROM anime_votes WHERE vote_type IN ('masterpiece', 'great', 'darkhorse', 'decent', 'controversial', 'disaster') GROUP BY vote_type"
        )
        rows = c.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    # ---- 統計/快取 ----
    def record_episode_stats(
        self, video_sn: int, anime_sn: int, episode_num: str, views: int, score: float
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO anime_episode_stats
               (video_sn, anime_sn, episode_num, views, score, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (video_sn, anime_sn, episode_num, views, score),
        )
        conn.commit()
        conn.close()
        return True

    def get_anime_details(self, anime_sn: int) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT title, content, cover, tags, views, score FROM anime_details_cache WHERE anime_sn=?",
            (anime_sn,),
        )
        row = c.fetchone()
        conn.close()
        if row:
            title, content, cover, tags, views, score = row
            import json

            return {
                "title": (
                    title
                    if isinstance(title, str)
                    else title.decode("utf-8", errors="replace")
                ),
                "content": (
                    content
                    if isinstance(content, str)
                    else content.decode("utf-8", errors="replace")
                ),
                "cover": (
                    cover
                    if isinstance(cover, str)
                    else cover.decode("utf-8", errors="replace")
                ),
                "tags": (
                    json.loads(tags)
                    if isinstance(tags, str)
                    else json.loads(tags.decode("utf-8", errors="replace"))
                ),
                "views": views,
                "score": score,
            }
        return {}

    def cache_anime_details(
        self,
        anime_sn: int,
        title: str,
        content: str,
        cover: str,
        tags: list,
        views: int,
        score: float,
    ) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        import json

        c.execute(
            """INSERT OR REPLACE INTO anime_details_cache
               (anime_sn, title, content, cover, tags, views, score, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                anime_sn,
                title,
                content,
                cover,
                json.dumps(tags, ensure_ascii=False),
                views,
                score,
            ),
        )
        conn.commit()
        conn.close()
        return True

    # ---- 維護 ----
    def clean_orphaned_records(self, week_start_date: str) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        result = {"deleted_schedule": 0, "deleted_notified": 0, "deleted_votes": 0}
        # 清理該週的 schedule 記錄
        c.execute(
            "DELETE FROM anime_weekly_schedule WHERE weekStartDate=?",
            (week_start_date,),
        )
        result["deleted_schedule"] = c.rowcount
        # 清理該週相關的 notified 記錄 (通過 videoSn 關聯)
        c.execute(
            """
            DELETE FROM anime_notified
            WHERE video_sn IN (SELECT videoSn FROM anime_weekly_schedule WHERE weekStartDate=?)
        """,
            (week_start_date,),
        )
        result["deleted_notified"] = c.rowcount
        conn.commit()
        conn.close()
        return result

    def save_weekly_schedule(self, week_start_date: str, schedule_data: list) -> bool:
        """
        全量覆蓋週表：先刪除該 week_start_date 的舊資料，再插入新資料
        保留 pushed=1 的記錄（UPSERT 保留機制）+ pre-dedup

        Args:
            week_start_date: 週起始日期 "YYYY-MM-DD"
            schedule_data: 列表，每項包含 {day_of_week, scheduled_time, anime_data}

        Returns:
            bool: 是否成功
        """
        import json

        conn = self._get_conn()
        c = conn.cursor()

        try:
            # 1. 先查詢該週已經 pushed=1 的記錄，保留它們
            c.execute(
                "SELECT dayOfWeek, scheduledTime, videoSn FROM anime_weekly_schedule WHERE weekStartDate=? AND pushed=1",
                (week_start_date,),
            )
            pushed_records = c.fetchall()
            pushed_set = {(row[0], row[1], row[2]) for row in pushed_records}

            # 2. 刪除該 week_start_date 的所有資料
            c.execute(
                "DELETE FROM anime_weekly_schedule WHERE weekStartDate=?",
                (week_start_date,),
            )

            # 3. 插入新資料，保留 pushed=1
            # Pre-deduplicate by (day_of_week, scheduled_time) to avoid UNIQUE constraint failure
            seen = set()
            deduped_schedule_data = []
            duplicates = 0
            for item in schedule_data:
                key = (item["day_of_week"], item["scheduled_time"])
                if key in seen:
                    duplicates += 1
                    logger.warning(f"⚠️ [save_weekly_schedule] Duplicate schedule entry ignored: day_of_week={item['day_of_week']}, scheduled_time={item['scheduled_time']}")
                    continue
                seen.add(key)
                deduped_schedule_data.append(item)

            if duplicates > 0:
                logger.info(f"📝 [save_weekly_schedule] Removed {duplicates} duplicate schedule entries")

            for item in deduped_schedule_data:
                day_of_week = item["day_of_week"]
                scheduled_time = item["scheduled_time"]
                anime_data = item.get("anime_data", {})

                # 從 anime_data 提取 videoSn
                video_sn = anime_data.get("videoSn") or anime_data.get("video_sn")

                # 檢查是否已經推送過
                pushed = (
                    1 if (day_of_week, scheduled_time, video_sn) in pushed_set else 0
                )

                # 序列化 anime_data
                anime_data_json = json.dumps(anime_data, ensure_ascii=False)

                c.execute(
                    """INSERT INTO anime_weekly_schedule
                       (weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        week_start_date,
                        day_of_week,
                        scheduled_time,
                        pushed,
                        anime_data_json,
                        video_sn,
                    ),
                )

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"❌ [save_weekly_schedule] 失敗: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            conn.close()

    def cleanup_old_weeks(self) -> int:
        conn = self._get_conn()
        c = conn.cursor()
        # 刪除 4 週前的資料
        cutoff_date = datetime.now().date() - timedelta(weeks=4)
        c.execute(
            "DELETE FROM anime_weekly_schedule WHERE weekStartDate < ?",
            (cutoff_date.strftime("%Y-%m-%d"),),
        )
        deleted = c.rowcount
        conn.commit()
        conn.close()
        return deleted

    # ---- 統計查詢 (for ranking_stats) ----
    def get_anime_statistics(self, anime_sn: int) -> dict | None:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT AVG(views) as avg_views, AVG(score) as avg_score, COUNT(*) as total_episodes
               FROM episode_statistics WHERE animeSn=?""",
            (anime_sn,),
        )
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None:
            return {
                "avg_views": row[0],
                "avg_score": row[1] if row[1] is not None else 0,
                "total_episodes": row[2],
            }
        return None

    def get_top_anime_by_views(
        self,
        limit: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        query = """SELECT animeSn, SUM(views) as total_views, COUNT(*) as total_episodes
                   FROM episode_statistics"""
        params = []
        if start_time or end_time:
            conditions = []
            if start_time:
                conditions.append("recorded_at >= ?")
                params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))
            if end_time:
                conditions.append("recorded_at <= ?")
                params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))
            query += " WHERE " + " AND ".join(conditions)
        query += " GROUP BY animeSn ORDER BY total_views DESC LIMIT ?"
        params.append(limit)
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            anime_sn, total_views, total_episodes = row
            result.append(
                {
                    "anime_sn": anime_sn,
                    "total_views": total_views,
                    "total_episodes": total_episodes,
                }
            )
        return result

    def get_multi_episode_anime_for_chart(
        self,
        limit: int = 10,
        min_episodes: int = 1,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        query = """SELECT animeSn, episode_num, views, score, recorded_at
                   FROM episode_statistics"""
        params = []
        if start_time or end_time:
            conditions = []
            if start_time:
                conditions.append("recorded_at >= ?")
                params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))
            if end_time:
                conditions.append("recorded_at <= ?")
                params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY animeSn, recorded_at"
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        # 聚合按 animeSn
        anime_map = {}
        for row in rows:
            anime_sn, episode_num, views, score, recorded_at = row
            if anime_sn not in anime_map:
                anime_map[anime_sn] = {"episodes": [], "total_views": 0}
            anime_map[anime_sn]["episodes"].append(
                {
                    "episode_num": episode_num,
                    "views": views if views is not None else 0,
                    "score": score if score is not None else 0,
                    "recorded_at": recorded_at,
                }
            )
            if views is not None:
                anime_map[anime_sn]["total_views"] += views
        result = []
        for anime_sn, data in anime_map.items():
            if len(data["episodes"]) >= min_episodes:
                result.append(
                    {
                        "anime_sn": anime_sn,
                        "name": "",
                        "episodes": data["episodes"],
                        "total_views": data["total_views"],
                    }
                )
        # 排序並限制
        result.sort(key=lambda x: x["total_views"], reverse=True)
        return result[:limit]

    @property
    def db_path(self) -> str:
        return self._db_path

    async def fetchone(self, query: str, params: tuple = ()):
        """通用查詢單行結果"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(query, params)
        row = c.fetchone()
        conn.close()
        return row


def _get_db_connection():
    """獲取資料庫連線 - 啟用 WAL 模式和 busy_timeout 避免鎖定問題"""
    conn = sqlite3.connect(str(ANIME_DB_PATH))
    conn.text_factory = bytes  # 所有 TEXT 欄位回傳 bytes，由上層自行 decode
    # 啟用 WAL 模式：讀取不阻塞寫入，寫入不阻塞讀取
    conn.execute("PRAGMA journal_mode=WAL")
    # 設定 30 秒等待超時，避免無限阻塞
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_week_start_date(dt: datetime, api_week: bool = True) -> str:
    """
    計算週起始日期 (週一為週起始)

    Args:
        dt: 參考日期
        api_week: True=API 語義週（上週一），False=Dispatcher 語義週（本週一）

    Returns:
        str: "YYYY-MM-DD" 格式的週一日期
    """
    if api_week:
        # API 週：當天是週一，週起始是上週一 (7 天前)
        days_back = (dt.weekday() + 7) % 7
        if days_back == 0:
            days_back = 7
    else:
        # Dispatcher 週：標準週一
        days_back = dt.weekday()
    return (dt - timedelta(days=days_back)).strftime("%Y-%m-%d")


class AnimePushCore:
    """極簡動畫推送核心：只有 send, is_notified, add_notified, mark_time_pushed, fetch_api"""

    def __init__(self, db):
        self.db = db
        self.bot = None
        self._view_factory = None
        self._embed_factory = None

    def set_bot(self, bot):
        """設置 bot 實例"""
        self.bot = bot

    def set_view_factory(self, factory):
        """設置視圖生成工廠函數"""
        self._view_factory = factory

    def set_embed_factory(self, factory):
        """設置 embed 生成工廠函數"""
        self._embed_factory = factory

    def set_dependencies(self, bot, db, anime_tracker=None):
        """設置依賴 (for compatibility with anime_tracker)"""
        self.set_bot(bot)
        # The db is already set in constructor, but we can update it if needed
        if db is not None:
            self.db = db
        # anime_tracker reference not needed for core functionality

    async def _generate_anime_view(self, episode: dict):
        """生成動畫推送視圖 - 使用工廠函數或預設"""
        try:
            if self._view_factory:
                return await self._view_factory(episode)
            from shared.utils.embed_views import create_anime_push_view

            return create_anime_push_view(episode)
        except Exception as e:
            logger.error(f"生成 view 失敗: {e}")
            return None

    async def _generate_anime_embed(self, episode: dict) -> discord.Embed | None:
        """生成動畫推送 embed - 使用工廠函數或預設"""
        try:
            if self._embed_factory:
                return await self._embed_factory(episode)
            # 預設實現
            import discord

            title = episode.get("title", "未知標題")
            cover = episode.get("cover", "")
            description = episode.get("description", "")

            embed = discord.Embed(
                title=title, description=description, color=discord.Color.blue()
            )

            if cover:
                embed.set_image(url=cover)  # 大圖在下方

            return embed
        except Exception as e:
            logger.error(f"生成 embed 失敗: {e}")
            return None

    # ========== 核心查詢方法 ==========

    def is_notified(self, video_sn: int) -> bool:
        """檢查 video_sn 是否已推送過 (anime_notified 表)"""
        try:
            return self.db.is_notified(video_sn)
        except Exception as e:
            logger.error(f"is_notified 錯誤 video_sn={video_sn}: {e}")
            return False

    def add_notified(
        self,
        video_sn: int,
        anime_sn: int,
        title: str,
        volume: str = "",
        cover: str = "",
    ) -> bool:
        """記錄已推送 - 使用 INSERT OR IGNORE 避免重複"""
        try:
            return self.db.add_notified(video_sn, anime_sn, title, volume, cover)
        except Exception as e:
            logger.error(f"add_notified 錯誤 video_sn={video_sn}: {e}")
            return False

    def mark_time_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> bool:
        """標記某個時刻已推送過 (anime_weekly_schedule 表) - 將該時段所有動畫標記為 pushed=1"""
        try:
            return self.db.mark_time_pushed(
                week_start_date, day_of_week, scheduled_time
            )
        except Exception as e:
            logger.error(f"mark_time_pushed 錯誤: {e}")
            return False

    # ========== 直接查詢 anime_weekly_schedule 表 ==========
    def get_schedule_video_sns(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> set[int]:
        """獲取某時段預期的 videoSn 集合 (同時查 videoSn 欄位與 anime_data JSON)"""
        try:
            conn = _get_db_connection()
            c = conn.cursor()
            # 優先查 videoSn 欄位，若為 NULL 則從 anime_data JSON 提取 (COALESCE)
            c.execute(
                "SELECT COALESCE(videoSn, JSON_EXTRACT(animeData, '$.videoSn')) as videoSn FROM anime_weekly_schedule WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?",
                (week_start_date, day_of_week, scheduled_time),
            )
            rows = c.fetchall()
            conn.close()
            result = set()
            for row in rows:
                if row[0] is not None:
                    try:
                        # COALESCE/JSON_EXTRACT 可能回傳字串或整數
                        result.add(int(row[0]))
                    except (ValueError, TypeError):
                        pass
            return result
        except Exception as e:
            logger.error(f"get_schedule_video_sns 錯誤: {e}")
            return set()

    def get_today_schedule(self, week_start_date: str | None = None) -> list[dict]:
        """獲取今天的所有排程

        Args:
            week_start_date: 週起始日期 "YYYY-MM-DD"，若不提供則使用當前週 (api_week=True)
        """
        from datetime import datetime
        from .push_core import get_week_start_date, TW_TZ

        if week_start_date is None:
            week_start_date = get_week_start_date(datetime.now(TW_TZ), api_week=True)

        try:
            conn = _get_db_connection()
            c = conn.cursor()
            # 移除 videoSn 欄位 (不存在)，從 anime_data JSON 提取
            c.execute("""SELECT weekStartDate, dayOfWeek, scheduledTime, pushed,
                           CAST(animeData AS BLOB) as animeData
                        FROM anime_weekly_schedule WHERE weekStartDate=?""",
                        (week_start_date,))
            rows = c.fetchall()
            conn.close()
            result = []
            for row in rows:
                week_start_date_db, day_of_week, scheduled_time, pushed, anime_data_raw = (
                    row
                )
                video_sn = None
                if anime_data_raw:
                    try:
                        if isinstance(anime_data_raw, bytes):
                            anime_data_raw = anime_data_raw.decode(
                                "utf-8", errors="replace"
                            )
                        anime_data = json.loads(anime_data_raw)
                        video_sn = anime_data.get("videoSn")
                    except Exception:
                        pass
                item = {
                    "video_sn": video_sn,
                    "week_start_date": (
                        week_start_date_db.decode("utf-8", errors="replace")
                        if isinstance(week_start_date_db, bytes)
                        else week_start_date_db
                    ),
                    "day_of_week": day_of_week,
                    "scheduled_time": (
                        scheduled_time.decode("utf-8", errors="replace")
                        if isinstance(scheduled_time, bytes)
                        else scheduled_time
                    ),
                    "pushed": bool(pushed) if pushed is not None else False,
                }
                if anime_data_raw:
                    try:
                        if isinstance(anime_data_raw, bytes):
                            anime_data_raw = anime_data_raw.decode(
                                "utf-8", errors="replace"
                            )
                        anime_data = json.loads(anime_data_raw)
                        item["anime_data"] = anime_data
                        # 從 anime_data 提取 anime_sn (支援 camelCase 和 snake_case)
                        item["anime_sn"] = anime_data.get("animeSn") or anime_data.get("anime_sn")
                    except Exception as e:
                        logger.warning(f"animeData 解析失敗 videoSn={video_sn}: {e}")
                        item["anime_data"] = {}
                        item["anime_sn"] = None
                else:
                    item["anime_data"] = {}
                    item["anime_sn"] = None
                result.append(item)
            return result
        except Exception as e:
            logger.error(f"get_today_schedule 錯誤: {e}")
            return []

    def mark_anime_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str, video_sn: int
    ) -> bool:
        """標記某動畫已推送 (設定 pushed=1)"""
        try:
            conn = _get_db_connection()
            c = conn.cursor()
            c.execute(
                "UPDATE anime_weekly_schedule SET pushed=1 WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=? AND videoSn=?",
                (week_start_date, day_of_week, scheduled_time, video_sn),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"mark_anime_pushed 錯誤: {e}")
            return False

    def save_message_info(
        self, message_id: int, video_sn: int, anime_sn: int, title: str, channel_id: int
    ) -> bool:
        """儲存訊息資訊到 anime_messages 表"""
        try:
            conn = _get_db_connection()
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO anime_messages (message_id, video_sn, anime_sn, title, channel_id) VALUES (?, ?, ?, ?, ?)",
                (message_id, video_sn, anime_sn, title, channel_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"save_message_info 錯誤: {e}")
            return False

    # ========== 網頁爬取 ==========

    async def _fetch_new_anime_from_web(self) -> List[Dict]:
        """獲取新番動畫列表 - 使用網頁爬取"""
        return await fetch_new_anime_from_web()

    def _extract_video_sn_from_html(self, html_text: str, anime_sn: int) -> Optional[int]:
        """從HTML片段中提取 videoSn"""
        try:
            # 尋找 animeVideo.php?sn=XXXX 鏈接
            video_pattern = r'animeVideo\.php\?sn=(\d+)'
            video_matches = re.findall(video_pattern, html_text, re.IGNORECASE)

            if video_matches:
                # 取第一個找到的 videoSn
                return int(video_matches[0])

            # 另外可能是 data-video-sn 屬性
            data_pattern = r'data-video-sn\s*=\s*["\'](\d+)["\']'
            data_matches = re.findall(data_pattern, html_text, re.IGNORECASE)
            if data_matches:
                return int(data_matches[0])

        except (ValueError, IndexError):
            pass
        return None

    def _extract_cover_from_html(self, html_text: str) -> Optional[str]:
        """從HTML片段中提取封面圖 URL"""
        try:
            # 尋找 img 標籤，優先找看起來像封面的圖片
            img_patterns = [
                r'<img\s[^>]*src\s*=\s*["\']([^"\']*\/cover[^"\']*)["\'][^>]*>',  # 包含 cover 的 URL
                r'<img\s[^>]*src\s*=\s*["\']([^"\']*\.(jpg|jpeg|png|webp))["\'][^>]*>',  # 圖片檔案
                r'<img\s[^>]*data-src\s*=\s*["\']([^"\']*)["\'][^>]*>',  # lazy loading
                r'<img\s[^>]*src\s*=\s*["\']([^"\']*)["\'][^>]*>',  # 任意圖片
            ]

            for pattern in img_patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                if matches:
                    # 取第一個匹配的 URL
                    src = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    # 確保是完整 URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://ani.gamer.com.tw' + src
                    elif not src.startswith('http'):
                        src = 'https://ani.gamer.com.tw/' + src
                    return src

        except Exception:
            pass
        return None

    def _extract_title_from_html(self, html_text: str, anime_sn: int) -> Optional[str]:
        """從HTML片段中提取標題"""
        try:
            # 嘗試找看起來像標題的文字
            # 常見標題位置：在 h1-h6 標籤中，或有特定 class 的元素中
            title_patterns = [
                r'<h[1-6][^>]*>([^<]+)</h[1-6]>',  # 標題標籤
                r'<[^>]*class\s*=\s*["\'][^"\']*title[^"\']*["\'][^>]*>([^<]*)</[^>]*>',  # title class
                r'<[^>]*class\s*=\s*["\'][^"\']*name[^"\']*["\'][^>]*>([^<]*)</[^>]*>',  # name class
                r'<[^>]*class\s*=\s*["\'][^"\']*anime-name[^"\']*["\'][^>]*>([^<]*)</[^>]*>',  # anime-name class
            ]

            for pattern in title_patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                if matches:
                    # 取第一個非空的匹配
                    for match in matches:
                        title = match.strip()
                        if title and len(title) > 1:
                            return title

            # 如果上面都沒找到，嘗試從 alt 屬性中取得
            alt_pattern = r'<img\s[^>]*alt\s*=\s*["\']([^"\']*)["\'][^>]*>'
            alt_matches = re.findall(alt_pattern, html_text, re.IGNORECASE)
            if alt_matches:
                for alt in alt_matches:
                    if alt.strip() and len(alt.strip()) > 1:
                        return alt.strip()

        except Exception:
            pass
        return None

    def _extract_volume_from_html(self, html_text: str) -> Optional[str]:
        """從HTML片段中提取卷數/集數"""
        try:
            # 常見的集數顯示模式
            volume_patterns = [
                r'第\s*(\d+)\s*話',  # 第1話
                r'Vol\.?\s*(\d+)',  # Vol.1 或 Vol1
                r'EP\.?\s*(\d+)',   # EP.1 或 EP1
                r'(\d+)\s*話',      # 1話
                r'(\d+)\s*集',      # 1集
            ]

            for pattern in volume_patterns:
                match = re.search(pattern, html_text, re.IGNORECASE)
                if match:
                    return match.group(0)  # 返回完整匹配，如 "第1話"

        except Exception:
            pass
        return None

    def _parse_by_containers(self, html_text: str) -> list[dict]:
        """按容器元素解析動畫列表 - 備用方法"""
        anime_list = []

        try:
            # 嘗試找可能的動畫條目容器
            container_patterns = [
                r'<div\s[^>]*class\s*=\s*["\'][^"\']*anime[^"\']*["\'][^>]*>.*?</div>',
                r'<li\s[^>]*class\s*=\s*["\'][^"\']*anime[^"\']*["\'][^>]*>.*?</li>',
                r'<div\s[^>]*class\s*=\s*["\'][^"\']*item[^"\']*["\'][^>]*>.*?</div>',
                r'<div\s[^>]*class\s*=\s*["\'][^"\']*entry[^"\']*["\'][^>]*>.*?</div>',
                r'<div\s[^>]*class\s*=\s*["\'][^"\']*card[^"\']*["\'][^>]*>.*?</div>',
            ]

            for container_pattern in container_patterns:
                containers = re.findall(container_pattern, html_text, re.IGNORECASE | re.DOTALL)
                for container in containers:
                    anime = self._extract_anime_from_container(container)
                    if anime:
                        anime_list.append(anime)

                # 如果這個模式找到了動畫，就停止嘗試其他模式
                if anime_list:
                    break

        except Exception as e:
            logger.error(f"按容器解析時發生錯誤: {e}")

        return anime_list

    def _extract_anime_from_container(self, container_html: str) -> Optional[dict]:
        """從容器HTML中提取動畫資訊"""
        try:
            # 尋找 animeRef.php 鏈接取得 animeSn
            ref_match = re.search(r'animeRef\.php\?sn=(\d+)', container_html, re.IGNORECASE)
            if not ref_match:
                return None
            anime_sn = int(ref_match.group(1))

            # 尋找 animeVideo.php 鏈接取得 videoSn
            video_match = re.search(r'animeVideo\.php\?sn=(\d+)', container_html, re.IGNORECASE)
            if not video_match:
                return None
            video_sn = int(video_match.group(1))

            # 尋找封面圖
            cover_url = self._extract_cover_from_html(container_html)

            # 尋找標題
            title = self._extract_title_from_html(container_html, anime_sn)
            if not title:
                # 嘗試從連結文字中取得
                link_text_match = re.search(r'<a[^>]*animeRef\.php\?sn=' + str(anime_sn) + '[^>]*>([^<]*)</a>', container_html, re.IGNORECASE)
                if link_text_match:
                    title = link_text_match.group(1).strip()
                if not title:
                    title = f"未知標題_{anime_sn}"

            # 尋找卷數/集數
            volume = self._extract_volume_from_html(container_html)

            return {
                "videoSn": video_sn,
                "animeSn": anime_sn,
                "title": title,
                "cover": cover_url or "",
                "volume": volume or ""
            }

        except Exception as e:
            logger.debug(f"從容器提取動畫資訊失敗: {e}")
            return None

    # ========== 核心推送流程 ==========

    async def send_anime_push(
        self,
        scheduled_time: str,
        channel_id: int,
        day_of_week: int | None = None,
        week_start_date: str | None = None,
    ) -> bool:
        """
        統一推送入口：時間到 → 查 API → 推送 → 標記 push=1

        Args:
            scheduled_time: 推送時刻 "HH:MM"
            channel_id: Discord 頻道 ID
            day_of_week: 1=週一~7=週日，預設為今天
            week_start_date: 週起始日期 "YYYY-MM-DD"，預設為本週 (Dispatcher 週語義)

        Returns:
            bool: 是否有成功推送至少一筆
        """
        now = datetime.now(TW_TZ)
        if day_of_week is None:
            day_of_week = now.weekday() + 1
        if week_start_date is None:
            week_start_date = get_week_start_date(
                now, api_week=True
            )  # API 週，與週表儲存一致

        logger.info(
            f"🚀 [send_anime_push] 開始 {scheduled_time} (week={week_start_date}, day={day_of_week})"
        )

        # 1. 取得該時段的預期 videoSn (從週表)
        expected_video_sns = self.get_schedule_video_sns(
            week_start_date, day_of_week, scheduled_time
        )

        if not expected_video_sns:
            logger.info("📭 無預期 videoSn，標記時刻完成並結束")
            self.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
            return False

        # 2. 篩選出尚未推送的 videoSn (去除已 pushed=1 的)
        pushed_video_sns = {
            item["video_sn"]
            for item in self.get_today_schedule()
            if item["scheduled_time"] == scheduled_time and item.get("pushed")
        }
        pending_video_sns = expected_video_sns - pushed_video_sns

        if not pending_video_sns:
            logger.info(f"⏭️ 所有預期動畫已推送 ({expected_video_sns})，標記時刻完成")
            self.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
            return False

        logger.info(f"📋 待推送 videoSn: {pending_video_sns}")

        # 3. 檢查 bot 和頻道
        if self.bot is None:
            logger.error("Bot 未初始化")
            return False
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"頻道 {channel_id} 不存在或非文字頻道")
            # 不標記 push，讓下次重試
            return False

        # 4. 呼叫網頁爬取獲取最新動畫資料
        episodes = await fetch_new_anime_from_web()
        if not episodes:
            logger.warning("API 無回應")
            return False

        # 5. 直接用 videoSn 比對 (API 回傳完整 animeList，不需要按日期過濾)
        # 建立 videoSn -> episode 的映射
        episodes_by_vsn = {}
        for ep in episodes:
            ep_vsn = ep.get("videoSn")
            if ep_vsn:
                try:
                    episodes_by_vsn[int(ep_vsn)] = ep
                except (ValueError, TypeError):
                    pass

        logger.info(
            f"📋 API 回傳 {len(episodes)} 筆，可比對 {len(episodes_by_vsn)} 筆 videoSn"
        )

        # 6. 配對並推送：每個 pending_videoSn 直接從映射找對應 episode
        sent_count = 0
        matched_videosns: set[int] = set()

        for video_sn in pending_video_sns:
            matched_ep = episodes_by_vsn.get(video_sn)
            if matched_ep is None:
                logger.warning(f"week 表有 videoSn={video_sn} 但 API 無對應資料，略過")
                continue

            if matched_ep is None:
                logger.warning(
                    f"week 表有 videoSn={video_sn} 但 API 當日無對應資料，略過"
                )
                continue

            # 7. 雙重去重檢查：anime_notified + week pushed
            if self.is_notified(video_sn):
                logger.info(
                    f"⏭️ videoSn={video_sn} 已在 notified 表，標記 pushed 並略過"
                )
                self.mark_anime_pushed(
                    week_start_date, day_of_week, scheduled_time, video_sn
                )
                continue

            # 8. 生成 embed 和 view
            embed = await self._generate_anime_embed(matched_ep)
            if not embed:
                continue

            view = await self._generate_anime_view(matched_ep)
            if view is None:
                logger.warning(f"無 view for videoSn={video_sn}")
                continue

            # 9. 發送
            try:
                message = await channel.send(embed=embed, view=view, silent=True)

                if view and hasattr(view, "message_id"):
                    view.message_id = message.id

                # 記錄
                anime_sn = int(matched_ep.get("animeSn", 0))
                title = matched_ep.get("title", "未知標題")
                self.save_message_info(
                    message.id, video_sn, anime_sn, title, channel_id
                )
                self.add_notified(
                    video_sn,
                    anime_sn,
                    title,
                    matched_ep.get("volume", ""),
                    matched_ep.get("cover", ""),
                )

                # 註冊永久視圖
                if self.bot is not None:
                    self.bot.add_view(view, message_id=message.id)

                # 標記 pushed=1
                self.mark_anime_pushed(
                    week_start_date, day_of_week, scheduled_time, video_sn
                )
                matched_videosns.add(video_sn)
                sent_count += 1
                logger.info(f"✅ 已推送: {title} (videoSn={video_sn})")

            except Exception as e:
                logger.error(f"發送失敗 videoSn={video_sn}: {e}")
                continue

        # 10. 若該時段所有預期都已推送，標記時刻完成
        if expected_video_sns.issubset(pushed_video_sns | matched_videosns):
            self.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
            logger.info(f"✅ 時刻 {scheduled_time} 全部完成")

        return sent_count > 0


# ========== 為了相容性保留的介面 (scheduled_tasks 用) ==========


async def push_new_anime_episodes(
    bot, channel_id: int, db, target_time: str = None, test_mode: bool = False
) -> bool:
    """
    相容性入口：供排程任務呼叫
    會依傳入的 target_time 推送該時段，或推送所有待推送時段
    """
    core = AnimePushCore(db)
    core.set_bot(bot)

    now = datetime.now(TW_TZ)
    week_start_date = get_week_start_date(now, api_week=False)
    day_of_week = now.weekday() + 1

    if target_time:
        # 推送指定時段
        return await core.send_anime_push(
            target_time, channel_id, day_of_week, week_start_date
        )
    else:
        # 推送今日所有未推送時段
        today_schedule = core.db.get_today_schedule()
        pending_times = set()
        for item in today_schedule:
            if not item.get("pushed") and item["day_of_week"] == day_of_week:
                pending_times.add(item["scheduled_time"])

        if not pending_times:
            logger.info("無待推送時段")
            return False

        results = []
        for st in sorted(pending_times):
            results.append(
                await core.send_anime_push(st, channel_id, day_of_week, week_start_date)
            )

        return any(results)
