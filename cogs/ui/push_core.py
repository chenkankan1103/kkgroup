"""
動畫推送核心模組 - 極簡版

核心邏輯：時間到 → 查 API → 推送 → 標記 push=1
補推邏輯：偵測 push=0 且時間已過 → 未超過 1 小時 → 推送；超過 1 小時 → 標記 pushed 並放棄

移除所有過度設計：retry/lock/exhausted/catchup 等複雜機制
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import discord

logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333
ANIME_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"
API_ENDPOINT = "https://api.gamer.com.tw/anime/v1/anime_list.php"
API_TIMEOUT = 15

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
}


# ========== 相容性介面：AnimeDatabase 類別 (需在 AnimePushCore 之前定義，供 anime_tracker 匯入) ==========


class AnimeDatabase:
    """相容性包裝：將舊版 AnimeDatabase 介面委託給 db adapter"""

    def __init__(self, db):
        self.db = db

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
    def get_today_schedule(self) -> list:
        return self.db.get_today_schedule()

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
        """獲取連線，禁用 row_factory 避免 UTF-8 解碼問題"""
        import sqlite3

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = None
        conn.text_factory = bytes
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
            item = {
                "video_sn": video_sn,
                "week_start_date": week_start_date_db,
                "day_of_week": day_of_week,
                "scheduled_time": scheduled_time,
                "pushed": bool(pushed) if pushed is not None else False,
            }
            if anime_data_raw:
                try:
                    if isinstance(anime_data_raw, bytes):
                        anime_data_raw = anime_data_raw.decode(
                            "utf-8", errors="replace"
                        )
                    item["anime_data"] = json.loads(anime_data_raw)
                except Exception as e:
                    logger.warning(f"animeData 解析失敗 videoSn={video_sn}: {e}")
                    item["anime_data"] = {}
            else:
                item["anime_data"] = {}
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
            for item in schedule_data:
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


def _get_db_connection():
    """獲取資料庫連線 - 使用 text_factory=bytes 避免 UTF-8 解碼問題"""
    conn = sqlite3.connect(str(ANIME_DB_PATH))
    conn.text_factory = bytes  # 所有 TEXT 欄位回傳 bytes，由上層自行 decode
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
        """獲取某時段預期的 videoSn 集合 (從 anime_data JSON 提取)"""
        try:
            conn = _get_db_connection()
            c = conn.cursor()
            # 使用 JSON_EXTRACT 從 anime_data 提取 videoSn
            c.execute(
                "SELECT JSON_EXTRACT(animeData, '$.videoSn') as videoSn FROM anime_weekly_schedule WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?",
                (week_start_date, day_of_week, scheduled_time),
            )
            rows = c.fetchall()
            conn.close()
            result = set()
            for row in rows:
                if row[0] is not None:
                    try:
                        # JSON_EXTRACT 可能回傳字串或整數
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
                        item["anime_data"] = json.loads(anime_data_raw)
                    except Exception as e:
                        logger.warning(f"animeData 解析失敗 videoSn={video_sn}: {e}")
                        item["anime_data"] = {}
                else:
                    item["anime_data"] = {}
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

    # ========== API 獲取 ==========

    async def _fetch_new_anime_from_api(self) -> list[dict]:
        """從 API 獲取新番資料 - 單次請求，完整 Header，失敗直接回空

        新 API: https://api.gamer.com.tw/anime/v1/anime_list.php?type=newAnime
        回傳格式: {"data": {"animeList": [...], "totalPage": N}}
        每個項目包含: videoSn, animeSn, title, cover, dateInfo, totalEpisode, popular 等
        """
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            params = {"type": "newAnime"}
            async with aiohttp.ClientSession(
                timeout=timeout, headers=API_HEADERS
            ) as session, session.get(API_ENDPOINT, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"API 回傳狀態碼 {resp.status}")
                    return []
                data = await resp.json()
                # 新 API 格式: data.animeList
                anime_list = data.get("data", {}).get("animeList", [])
                if not anime_list:
                    return []
                return anime_list
        except Exception as e:
            logger.error(f"API 呼叫失敗: {e}")
            return []

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

        logger.info(f"📋 本時段預期 videoSn: {expected_video_sns}")

        # 2. 檢查 bot 和頻道
        if self.bot is None:
            logger.error("Bot 未初始化")
            return False
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"頻道 {channel_id} 不存在或非文字頻道")
            # 不標記 push，讓下次重試
            return False

        # 3. 呼叫 API 獲取最新動畫資料
        episodes = await self._fetch_new_anime_from_api()
        if not episodes:
            logger.warning("API 無回應")
            return False

        # 4. 建立 videoSn -> episode 的映射
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

        # 5. 配對並推送：處理所有預期 videoSn（不進行去重檢查）
        sent_count = 0
        matched_videosns: set[int] = set()

        for video_sn in expected_video_sns:
            matched_ep = episodes_by_vsn.get(video_sn)
            if matched_ep is None:
                logger.warning(f"week 表有 videoSn={video_sn} 但 API 無對應資料，略過")
                continue

            # 6. 生成 embed 和 view
            embed = await self._generate_anime_embed(matched_ep)
            if not embed:
                continue

            view = await self._generate_anime_view(matched_ep)
            if view is None:
                logger.warning(f"無 view for videoSn={video_sn}")
                continue

            # 7. 發送
            try:
                message = await channel.send(embed=embed, view=view, silent=True)

                if view and hasattr(view, "message_id"):
                    view.message_id = message.id

                # 記錄（僅作為日誌，不用於去重）
                anime_sn = int(matched_ep.get("animeSn", 0))
                title = matched_ep.get("title", "未知標題")
                self.save_message_info(
                    message.id, video_sn, anime_sn, title, channel_id
                )

                # 註冊永久視圖
                if self.bot is not None:
                    self.bot.add_view(view, message_id=message.id)

                matched_videosns.add(video_sn)
                sent_count += 1
                logger.info(f"✅ 已推送: {title} (videoSn={video_sn})")

            except Exception as e:
                logger.error(f"發送失敗 videoSn={video_sn}: {e}")
                continue

        # 8. 標記時刻已處理（嘗試推送所有預期動畫）
        self.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
        logger.info(f"✅ 時刻 {scheduled_time} 處理完成")

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
