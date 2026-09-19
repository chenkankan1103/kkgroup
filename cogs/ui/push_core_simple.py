"""
動畫推送核心模組 - 簡化版 15分鐘輪詢 (穩定版)

核心邏輯：每 15 分鐘 → 查 API → 推送 Embed → 標記 notified
專門負責 Embed 推送（含圖片和按鈕）
使用獨立資料庫：anime_push.db
"""

import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import discord

# Add kkgroup directory to sys.path for absolute imports
kkgroup_dir = Path(__file__).resolve().parent.parent.parent
if str(kkgroup_dir) not in sys.path:
    sys.path.insert(0, str(kkgroup_dir))


logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333

# 獨立推送資料庫（anime_notified、anime_votes、anime_weekly_schedule）
# 週表與推送資料同庫管理，與 user_data.db 完全分離
ANIME_PUSH_DB_PATH = Path(__file__).resolve().parent.parent.parent / "anime_push.db"

# API 常數
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15

# 完整瀏覽器指紋 Header
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
    "Sec-CH-UA-Full-Version-List": '"Not)A;Brand";v="99.0.0.0", "Google Chrome";v="127.0.0.0", "Chromium";v="127.0.0.0"',
}

# ========== 資料庫實現 ==========


class AnimePushDB:
    """動畫推送專用資料庫 - 只維護 anime_notified 表"""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or str(ANIME_PUSH_DB_PATH)
        self._init_tables()

    def _init_tables(self):
        """初始化 anime_notified、anime_votes 和 anime_weekly_schedule 表"""
        conn = self._get_conn()
        c = conn.cursor()

        # anime_notified 表 - 追蹤已推送的動畫
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_notified (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                videoSn INTEGER NOT NULL,
                animeSn INTEGER NOT NULL,
                anime_name TEXT NOT NULL,
                volume TEXT NOT NULL DEFAULT '',
                cover_url TEXT,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(videoSn, volume)
            )
        """)

        # anime_votes 表 - 追蹤動畫投票
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                videoSn INTEGER NOT NULL,
                animeSn INTEGER NOT NULL,
                message_id INTEGER,
                vote_type TEXT NOT NULL,  -- masterpiece, great, decent, small_audience, disaster, comment
                user_hash TEXT NOT NULL,  -- 匿名用戶雜湊
                comment TEXT,             -- 只有在 vote_type='comment' 時有值
                anime_name TEXT,          -- 動畫名稱（備用）
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(videoSn, user_hash, vote_type)  -- 同一用戶對同一動畫只能投同一類型的一票
            )
        """)

        # anime_weekly_schedule 表 - 週表排程（本庫專屬，與 user_data.db 分離）
        # dayOfWeek 慣例: 1=週一, ..., 7=週日（與填充腳本一致）
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

        conn.commit()
        conn.close()
        logger.info("✅ [AnimePushDB] 資料庫初始化完成: anime_push.db")

    def _get_conn(self):
        """獲取連線，啟用 WAL 模式"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = None
        conn.text_factory = bytes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # ---- 通知/推送相關 ----
    def is_notified(self, video_sn: int, volume: str = "") -> bool:
        """檢查是否已推送"""
        conn = self._get_conn()
        c = conn.cursor()
        if volume:
            c.execute(
                "SELECT 1 FROM anime_notified WHERE videoSn=? AND volume=?",
                (video_sn, volume),
            )
        else:
            c.execute("SELECT 1 FROM anime_notified WHERE videoSn=?", (video_sn,))
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
        """記錄已推送"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT OR IGNORE INTO anime_notified
               (videoSn, animeSn, anime_name, volume, cover_url, notified_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (video_sn, anime_sn, title, volume, cover),
        )
        conn.commit()
        conn.close()
        return True

    def get_notified_video_sns(self) -> set[int]:
        """獲取所有已通知的 videoSn（用於快速比對）"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT videoSn FROM anime_notified")
        rows = c.fetchall()
        conn.close()
        return {int(row[0]) for row in rows if row[0] is not None}

    # ====== 投票功能 ======

    def record_vote(
        self,
        video_sn: int,
        anime_sn: int,
        message_id: int | None,
        vote_type: str,
        user_hash: str,
        anime_name: str = "",
        comment: str = "",
    ) -> bool:
        """記錄投票（如果用戶已投過同類型票則更新）"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 使用 INSERT OR REPLACE 來實現「新票替換舊票」的邏輯
            c.execute(
                """
                INSERT OR REPLACE INTO anime_votes
                (videoSn, animeSn, message_id, vote_type, user_hash, comment, anime_name, voted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    video_sn,
                    anime_sn,
                    message_id,
                    vote_type,
                    user_hash,
                    comment,
                    anime_name,
                ),
            )

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ 記錄投票失敗: {e}")
            return False

    def get_vote_stats(self, video_sn: int) -> dict[str, int]:
        """獲取指定動畫的投票統計"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 統計每種投票類型的數量（不包括評論）
            c.execute(
                """
                SELECT vote_type, COUNT(*) as count
                FROM anime_votes
                WHERE videoSn = ? AND vote_type != 'comment'
                GROUP BY vote_type
                """,
                (video_sn,),
            )

            rows = c.fetchall()
            conn.close()

            # 初始化所有投票類型為0
            vote_stats = {
                "masterpiece": 0,
                "great": 0,
                "decent": 0,
                "small_audience": 0,
                "disaster": 0,
            }

            # 填入實際統計值
            for row in rows:
                vote_type = row[0]
                count = int(row[1])
                if vote_type in vote_stats:
                    vote_stats[vote_type] = count

            return vote_stats
        except Exception as e:
            logger.error(f"❌ 獲取投票統計失敗: {e}")
            return {
                "masterpiece": 0,
                "great": 0,
                "decent": 0,
                "small_audience": 0,
                "disaster": 0,
            }

    def get_vote_comments(self, video_sn: int, limit: int = 10) -> list[dict]:
        """獲取指定動畫的評論"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            c.execute(
                """
                SELECT user_hash, comment, voted_at
                FROM anime_votes
                WHERE videoSn = ? AND vote_type = 'comment' AND comment IS NOT NULL AND comment != ''
                ORDER BY voted_at DESC
                LIMIT ?
                """,
                (video_sn, limit),
            )

            rows = c.fetchall()
            conn.close()

            comments = []
            for row in rows:
                comments.append(
                    {
                        "user_hash": row[0],
                        "comment": row[1],
                        "voted_at": row[2],
                    }
                )

            return comments
        except Exception as e:
            logger.error(f"❌ 獲取評論失敗: {e}")
            return []

    # ====== 新增：週表相關方法 ======

    def _get_week_start_date(self, date_obj: datetime) -> str:
        """取得指定日期所在週的週一日期 (YYYY-MM-DD)"""
        # weekday() 回傳 0 為週一, 6 為週日
        monday = date_obj - timedelta(days=date_obj.weekday())
        return monday.strftime("%Y-%m-%d")

    def get_today_schedule(self, week_start_date: str = None) -> list[dict]:
        """查詢今日應該推送的動畫排程（anime_weekly_schedule 表）

        week_start_date 參數為相容 AnimeScheduleTracker 的委託呼叫，忽略之
        （本方法一律以目前時間計算所在週）
        """
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 取得今天的日期和星期
            now = datetime.now(TW_TZ)
            today_date = now.strftime("%Y-%m-%d")
            # Python的weekday(): 0=週一, 6=週日
            # 資料庫中的weekday: 1=週一, ..., 7=週日（與填充腳本一致）
            # 轉換公式: database_weekday = python_weekday + 1
            python_weekday = now.weekday()
            database_weekday = python_weekday + 1
            # 取得本週的週一日期
            week_start_date = self._get_week_start_date(now)

            # 查詢今日的排程（明確欄位，避免依賴表結構順序）
            c.execute(
                """
                SELECT id, weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn
                FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND dayOfWeek = ? AND pushed = 0
            """,
                (week_start_date, database_weekday),
            )

            rows = c.fetchall()
            conn.close()

            # 轉換為字典列表
            schedule = []
            for row in rows:
                # 假設表結構為：id, weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn
                # 由於連線使用 text_factory = bytes，需要解碼文字欄位
                weekStartDate = (
                    row[1].decode("utf-8") if isinstance(row[1], bytes) else row[1]
                )
                scheduledTime = (
                    row[3].decode("utf-8") if isinstance(row[3], bytes) else row[3]
                )
                animeData = (
                    row[5].decode("utf-8") if isinstance(row[5], bytes) else row[5]
                )
                schedule.append(
                    {
                        "id": row[0],
                        "weekStartDate": weekStartDate,
                        "dayOfWeek": row[2],
                        "scheduledTime": scheduledTime,
                        "pushed": bool(row[4]),
                        "animeData": animeData,  # 這可能是JSON字符串
                        "videoSn": row[6],
                    }
                )

            return schedule
        except Exception as e:
            logger.error(f"❌ 查詢今日排程失敗: {e}")
            return []

    def get_upcoming_schedules(self) -> list[dict]:
        """查詢本週排程時刻尚未到達且未推送的排程（供輪詢路徑暫緩判斷）

        回傳的每一項含 videoSn / dayOfWeek / scheduledTime / scheduleDt。
        只查本週（weekStartDate = 本週一）：排程時刻已過或跨週後查不到，
        輪詢路徑即照常推送（安全後備，不會漏推）。
        """
        try:
            conn = self._get_conn()
            c = conn.cursor()

            now = datetime.now(TW_TZ)
            week_start_date = self._get_week_start_date(now)

            c.execute(
                """
                SELECT dayOfWeek, scheduledTime, videoSn
                FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND pushed = 0
                """,
                (week_start_date,),
            )

            rows = c.fetchall()
            conn.close()

            upcoming = []
            for day_of_week, scheduled_time, video_sn in rows:
                if not video_sn:
                    continue
                scheduled_time = (
                    scheduled_time.decode("utf-8")
                    if isinstance(scheduled_time, bytes)
                    else scheduled_time
                )
                try:
                    # DB dayOfWeek 1-7（週一=1）換算為實際日期，再與現在比較
                    sched_date = datetime.strptime(
                        week_start_date, "%Y-%m-%d"
                    ) + timedelta(days=int(day_of_week) - 1)
                    sched_dt = datetime.strptime(
                        f"{sched_date.strftime('%Y-%m-%d')} {scheduled_time}",
                        "%Y-%m-%d %H:%M",
                    ).replace(tzinfo=TW_TZ)
                except (ValueError, TypeError):
                    continue
                if sched_dt > now:
                    upcoming.append(
                        {
                            "videoSn": video_sn,
                            "dayOfWeek": day_of_week,
                            "scheduledTime": scheduled_time,
                            "scheduleDt": sched_dt,
                        }
                    )
            return upcoming
        except Exception as e:
            logger.error(f"❌ 查詢本週未來排程失敗: {e}")
            return []

    def get_next_push_time(self) -> datetime | None:
        """計算距離下次排程推送的時間（anime_weekly_schedule 表）"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 取得現在時間
            now = datetime.now(TW_TZ)
            today_date = now.strftime("%Y-%m-%d")
            # Python的weekday(): 0=週一, 6=週日
            # 資料庫中的weekday: 1=週一, ..., 7=週日（與填充腳本一致）
            # 轉換公式: database_weekday = python_weekday + 1
            python_weekday = now.weekday()
            database_weekday = python_weekday + 1
            current_time = now.strftime("%H:%M")
            # 取得本週的週一日期
            week_start_date = self._get_week_start_date(now)

            # 查詢今日尚未推送的排程
            c.execute(
                """
                SELECT scheduledTime FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND dayOfWeek = ? AND pushed = 0
                ORDER BY scheduledTime ASC
            """,
                (week_start_date, database_weekday),
            )

            today_schedule = c.fetchall()

            # 先找今日尚未推送且在未來的排程（按時間順序）
            for (scheduled_time_bytes,) in today_schedule:
                try:
                    # 解碼 bytes 為 string
                    scheduled_time = scheduled_time_bytes.decode("utf-8")
                    schedule_dt = datetime.strptime(
                        f"{today_date} {scheduled_time}", "%Y-%m-%d %H:%M"
                    )
                    schedule_dt = schedule_dt.replace(tzinfo=TW_TZ)
                    if schedule_dt > now:
                        conn.close()
                        return schedule_dt
                except (ValueError, UnicodeDecodeError):
                    continue

            # 查詢未來日期的排程（從明天開始）
            # 我們只需要查詢未來7天內的最近一個排程
            for days_ahead in range(1, 8):  # 未來1到7天
                target_date = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                target_python_weekday = (now + timedelta(days=days_ahead)).weekday()
                # 轉換為資料庫中的weekday: 1=週一, ..., 7=週日（與填充腳本一致）
                target_database_weekday = target_python_weekday + 1
                # 取得目標日期所在週的週一日期
                target_date_obj = datetime.strptime(target_date, "%Y-%m-%d")
                target_week_start_date = self._get_week_start_date(target_date_obj)

                c.execute(
                    """
                    SELECT MIN(scheduledTime) FROM anime_weekly_schedule
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND pushed = 0
                """,
                    (target_week_start_date, target_database_weekday),
                )

                result = c.fetchone()
                if result and result[0]:
                    # 找到了未來某一天的最近排程
                    target_time_bytes = result[0]
                    try:
                        # 解碼 bytes 為 string
                        target_time = target_time_bytes.decode("utf-8")
                        target_datetime = datetime.strptime(
                            f"{target_date} {target_time}", "%Y-%m-%d %H:%M"
                        )
                        target_datetime = target_datetime.replace(tzinfo=TW_TZ)
                        conn.close()
                        return target_datetime
                    except (ValueError, UnicodeDecodeError):
                        continue

            conn.close()
            return None  # 沒有找到未來的排程
        except Exception as e:
            logger.error(f"❌ 計算下次推送時間失敗: {e}")
            return None

    def mark_time_pushed(
        self, day_of_week: int, scheduled_time: str, video_sn: int
    ) -> bool:
        """標記特定時間的動畫已推送"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 取得今天的日期（週StartDate）
            now = datetime.now(TW_TZ)
            today_date = now.strftime("%Y-%m-%d")
            # 取得本週的週一日期
            week_start_date = self._get_week_start_date(now)

            # 更新對應的記錄
            c.execute(
                """
                UPDATE anime_weekly_schedule
                SET pushed = 1
                WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ? AND videoSn = ?
            """,
                (week_start_date, day_of_week, scheduled_time, video_sn),
            )

            conn.commit()
            conn.close()

            logger.debug(
                f"✅ 標記排程為已推送: videoSn={video_sn}, day={day_of_week}, time={scheduled_time}"
            )
            return True
        except Exception as e:
            logger.error(f"❌ 標記排程為已推送失敗: {e}")
            return False

    def save_weekly_schedule(self, week_start_date: str, schedule_data: list) -> bool:
        """全量覆蓋週表：先刪除該週資料再插入，保留 pushed=1（UPSERT 機制）

        Args:
            week_start_date: 週起始日期 "YYYY-MM-DD"
            schedule_data: 列表，每項包含 {day_of_week, scheduled_time, anime_data}
        """
        conn = self._get_conn()
        c = conn.cursor()

        try:
            # 1. 查詢該週已推送的記錄（保留 pushed=1）
            c.execute(
                "SELECT dayOfWeek, scheduledTime, videoSn FROM anime_weekly_schedule WHERE weekStartDate=? AND pushed=1",
                (week_start_date,),
            )
            pushed_records = c.fetchall()
            pushed_set = {(row[0], row[1], row[2]) for row in pushed_records}

            # 2. 刪除該週所有資料
            c.execute(
                "DELETE FROM anime_weekly_schedule WHERE weekStartDate=?",
                (week_start_date,),
            )

            # 3. Pre-dedup by (day_of_week, scheduled_time) 避免重複插入
            seen = set()
            deduped = []
            for item in schedule_data:
                key = (item["day_of_week"], item["scheduled_time"])
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)

            for item in deduped:
                day_of_week = item["day_of_week"]
                scheduled_time = item["scheduled_time"]
                anime_data = item.get("anime_data", {})
                video_sn = anime_data.get("videoSn")
                pushed = (
                    1 if (day_of_week, scheduled_time, video_sn) in pushed_set else 0
                )

                c.execute(
                    """INSERT INTO anime_weekly_schedule
                       (weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        week_start_date,
                        day_of_week,
                        scheduled_time,
                        pushed,
                        json.dumps(anime_data, ensure_ascii=False),
                        video_sn,
                    ),
                )

            conn.commit()
            logger.info(
                f"✅ [AnimePushDB] 週表覆蓋完成: {week_start_date} ({len(deduped)} 個時刻)"
            )
            return True
        except Exception as e:
            logger.error(
                f"❌ [AnimePushDB] save_weekly_schedule 失敗: {e}", exc_info=True
            )
            conn.rollback()
            return False
        finally:
            conn.close()


# ========== API 獲取方法（保留自 ranking_stats）==========


async def fetch_all_recent_anime_from_api() -> list[dict] | None:
    """從 Bahamut API 獲取所有最近的動畫集"""
    try:
        async with aiohttp.ClientSession() as session, session.get(
            API_ENDPOINT,
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        ) as resp:
            if resp.status != 200:
                logger.warning(f"⚠️ API returned status {resp.status}")
                return None

            data = await resp.json()
            new_anime = data.get("data", {}).get("newAnime", {})

            all_episodes = []
            if isinstance(new_anime, dict):
                all_episodes.extend(new_anime.get("date", []))
                all_episodes.extend(new_anime.get("popular", []))

            # 去重
            seen = set()
            unique_episodes = []
            for ep in all_episodes:
                if isinstance(ep, dict):
                    video_sn = ep.get("videoSn")
                    if video_sn and video_sn not in seen:
                        seen.add(video_sn)
                        unique_episodes.append(ep)

            logger.info(
                f"🔍 [fetch_all_recent_anime_from_api] 獲得 {len(unique_episodes)} 部最近的動畫"
            )
            return unique_episodes
    except TimeoutError:
        logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
        return None
    except Exception as e:
        logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
        return None


def extract_view_count_from_episode(episode: dict, default: int = 0) -> int:
    """從 episode 物件提取觀看數"""
    view_candidates = [
        "popular",
        "viewCount",
        "counter",
        "views",
        "view_counter",
        "page_views",
        "click",
        "playCount",
    ]
    for field in view_candidates:
        raw = episode.get(field)
        if raw is not None:
            try:
                val = int(str(raw).replace(",", ""))
                if val > 0:
                    return val
            except (ValueError, TypeError):
                continue
    return default


async def fetch_anime_details_from_api(video_sn: int) -> dict | None:
    """從 Bahamut 手機 API 獲取動畫詳細信息"""
    if not video_sn:
        return None

    api_url = f"https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                headers={
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)"
                },
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                video_data = data.get("data", {}).get("video", {})
                anime_data = data.get("data", {}).get("anime", {})
                if not video_data and not anime_data:
                    return None

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        f"fetch_anime_details_from_api videoSn={video_sn} video keys: {list(video_data.keys())}"
                    )
                    logger.debug(
                        f"fetch_anime_details_from_api videoSn={video_sn} anime keys: {list(anime_data.keys())}"
                    )
                    logger.debug(f"videoCover={video_data.get('cover')}")
                    logger.debug(
                        f"episodeCover={anime_data.get('episodeCover')}, episodeThumb={anime_data.get('episodeThumb')}, thumb={anime_data.get('thumb')}, thumbnail={anime_data.get('thumbnail')}, videoThumb={anime_data.get('videoThumb')}, cover={anime_data.get('cover')}"
                    )

                view_count = (
                    anime_data.get("popular", 0)
                    or anime_data.get("viewCount", 0)
                    or anime_data.get("counter", 0)
                    or anime_data.get("views", 0)
                    or anime_data.get("view_counter", 0)
                    or anime_data.get("page_views", 0)
                    or 0
                )
                if not isinstance(view_count, (int, float)):
                    try:
                        view_count = int(str(view_count).replace(",", ""))
                    except (ValueError, TypeError):
                        view_count = 0

                # 嘗試獲取 episode-specific 的縮圖，如果沒有則退回到 series cover
                # 先嘗試 video 的 cover (episode-specific)
                episode_cover = (
                    video_data.get("cover")
                    or anime_data.get("episodeCover")
                    or anime_data.get("episodeThumb")
                    or anime_data.get("thumb")
                    or anime_data.get("thumbnail")
                    or anime_data.get("videoThumb")
                    or anime_data.get("cover")  # fallback to series cover
                )

                return {
                    "anime_sn": anime_data.get("anime_sn", 0),
                    "title": anime_data.get("title", ""),
                    "content": anime_data.get("content", ""),
                    "tags": anime_data.get("tags", []),
                    "popular": view_count,
                    # total_volume = 本季總集數（供 embed 計算平均觀看數）
                    "episode_count": anime_data.get("total_volume") or 0,
                    "score": anime_data.get("score", 0),
                    "cover": episode_cover,  # 使用 episode-specific 的縮圖如果可用
                }
    except Exception as e:
        logger.warning(f"⚠️ fetch_anime_details_from_api error videoSn={video_sn}: {e}")
        return None


# ========== 簡化推送核心 ==========


class SimpleAnimePushCore:
    """極簡動畫推送核心：智能排程檢查與15分鐘輪詢備案"""

    def __init__(self, db: AnimePushDB):
        self.db = db
        self.bot = None
        self._running = False
        self._task = None
        self._fail_count = 0
        self._max_failures = 3
        self._in_fallback = False

    def set_bot(self, bot):
        self.bot = bot

    async def start_polling(self, channel_id: int):
        """啟動 15 分鐘輪詢"""
        if self._running:
            logger.warning("輪詢已在運行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._polling_loop(channel_id))
        logger.info("🚀 [SimpleAnimePushCore] 15分鐘輪詢已啟動")

    async def stop_polling(self):
        """停止輪詢"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 [SimpleAnimePushCore] 輪詢已停止")

    async def _polling_loop(self, channel_id: int):
        """智能排程檢查主循環"""
        while self._running:
            try:
                # 如果在備案模式中，使用原始的15分鐘輪詢
                if self._in_fallback:
                    await self._fallback_polling_loop(channel_id)
                else:
                    # 正常的排程檢查模式
                    await self._schedule_based_loop(channel_id)
            except Exception as e:
                logger.error(f"❌ [SimpleAnimePushCore] 輪詢異常: {e}", exc_info=True)
                # 發生錯誤時增加失敗計數
                self._fail_count += 1
                logger.warning(f"推送失敗計數: {self._fail_count}/{self._max_failures}")

                # 如果連續失敗達到上限，進入備案模式
                if self._fail_count >= self._max_failures:
                    await self._enter_fallback_mode()

    async def _schedule_based_loop(self, channel_id: int):
        """智能排程檢查循環"""
        # 獲取下次推送時間
        next_push_time = self.db.get_next_push_time()

        if next_push_time is None:
            # 沒有找到未來的排程，備案到15分鐘輪詢
            logger.info("📅 沒有找到未來排程，切換到備案模式")
            await self._enter_fallback_mode()
            return

        # 計算現在時間
        now = datetime.now(TW_TZ)

        # 計算需要睡眠的秒數
        sleep_seconds = max(0, (next_push_time - now).total_seconds())

        # 設置上限為30分鐘（1800秒）以避免錯過排程
        sleep_seconds = min(sleep_seconds, 1800)

        logger.debug(
            f"😴 智能睡眠 {sleep_seconds:.0f} 秒直到下次推送時間: {next_push_time}"
        )

        # 睡眠
        await asyncio.sleep(sleep_seconds)

        # 再次檢查時間（防止系統時間異常或睡眠被提前結束）
        now = datetime.now(TW_TZ)
        if now >= next_push_time:
            # 到達推送時間，檢查並推送當前時間的排程
            await self._check_and_push(channel_id)
        else:
            # 時間還沒到，這不應該發生，但為安全起見繼續循環
            logger.debug(
                f"⏰ 睡眠結束但尚未到達推送時間，當前時間: {now}, 推送時間: {next_push_time}"
            )

    async def _fallback_polling_loop(self, channel_id: int):
        """備案模式：原始15分鐘輪詢"""
        logger.info("🔄 進入備案模式：使用原始15分鐘輪詢")
        await self._check_and_push_polling(channel_id)

        # 等待 15 分鐘 (900 秒)
        await asyncio.sleep(900)

        # 檢查是否可以退出備案模式
        self._fail_count = max(0, self._fail_count - 1)  # 逐漸減少失敗計數
        if self._fail_count == 0:
            await self._exit_fallback_mode()

    async def _enter_fallback_mode(self):
        """進入備案模式"""
        if self._in_fallback:
            return  # 已經在備案模式中

        self._in_fallback = True
        self._fail_count = self._max_failures  # 設置為最大值以保持在備案模式
        logger.warning("⚠️ 進入備案模式：切換到原始15分鐘輪詢")

    async def _exit_fallback_mode(self):
        """退出備案模式"""
        if not self._in_fallback:
            return  # 不在備案模式中

        self._in_fallback = False
        self._fail_count = 0
        logger.info("✅ 退出備案模式：恢復智能排程檢查")

    async def _check_and_push_polling(self, channel_id: int):
        """檢查並推送新動畫 (僅圖片)"""
        if not self.bot:
            return

        # Import here to avoid circular import
        from cogs.ui.push_embed import generate_anime_embed, generate_anime_view

        # 1. 從 API 獲取最新動畫列表
        episodes = await fetch_all_recent_anime_from_api()
        if not episodes:
            logger.warning("API 無回應")
            return

        # 2. 獲取已通知的 videoSn 集合
        notified_video_sns = self.db.get_notified_video_sns()

        # 3. 找出新動畫
        new_episodes = []
        for ep in episodes:
            video_sn = ep.get("videoSn")
            if video_sn and int(video_sn) not in notified_video_sns:
                new_episodes.append(ep)

        if not new_episodes:
            logger.info("📭 無新動畫需推送")
            return

        logger.info(f"📋 發現 {len(new_episodes)} 部新動畫")

        # 4. 檢查頻道
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"頻道 {ANIME_CHANNEL_ID} 不存在")
            return

        # 5. 推送每部新動畫 (僅圖片)
        # 排程保護：本週排程時刻未到的集數暫緩，讓排程路徑準時推送紫色 embed；
        # 排程時刻已過（或跨週後查不到）才照常推送（安全後備，不會漏推）
        upcoming_sns = {s.get("videoSn") for s in self.db.get_upcoming_schedules()}
        for ep in new_episodes:
            video_sn = int(ep.get("videoSn", 0))
            volume = ep.get("volume", "")

            if video_sn in upcoming_sns:
                logger.info(
                    f"⏳ {ep.get('title', '未知標題')} (videoSn={video_sn}) "
                    f"已排程且時刻未到，暫緩由排程路徑推送"
                )
                continue

            # 雙重檢查：再次確認是否已推送（防止並發）
            if self.db.is_notified(video_sn, volume):
                continue

            # 取得詳細資訊（含簡介和封面）
            try:
                # index API 的 popular 是當季總觀看數（逐集加總），在 detail 覆蓋前保留
                season_views = int(ep.get("popular") or 0)
                details = await fetch_anime_details_from_api(video_sn)
                if details:
                    ep = {
                        **ep,
                        "description": details.get("content", ""),
                        "cover": details.get("cover", ""),
                        "total_views": season_views,
                        "episode_count": int(details.get("episode_count") or 0),
                        # detail 的 popular 是本集觀看數（embed 端優先顯示當季總數）
                        "popular": details.get("popular", 0),
                        "score": details.get("score", 0),
                    }
            except Exception as e:
                logger.debug(f"取得動畫詳細資訊失敗 videoSn={video_sn}: {e}")

            # 生成 view (按鈕)
            view = await generate_anime_view(ep)
            if not view:
                continue

            # 生成 embed 和發送訊息
            try:
                embed = await generate_anime_embed(
                    ep, push_mode="輪詢 (備案模式)", db=self.db
                )
                message = await channel.send(embed=embed, view=view, silent=True)

                if view and hasattr(view, "message_id"):
                    view.message_id = message.id

                # 記錄
                anime_sn = int(ep.get("animeSn", 0))
                title = ep.get("title", "未知標題")
                self.db.add_notified(
                    video_sn,
                    anime_sn,
                    title,
                    volume,
                    ep.get("cover", ""),
                )

                # 註冊永久視圖
                if self.bot:
                    self.bot.add_view(view, message_id=message.id)

                logger.info(
                    f"✅ 已推送 Embed: {title} (videoSn={video_sn}, volume={volume})"
                )

            except Exception as e:
                logger.error(f"發送失敗 videoSn={video_sn}: {e}")

    async def _check_and_push(self, channel_id: int):
        """根據當前時間的排程檢查並推送動畫"""
        if not self.bot:
            return
        # Import here to avoid circular import
        from cogs.ui.push_embed import generate_anime_embed, generate_anime_view

        # 取得現在時間
        now = datetime.now(TW_TZ)
        today_date = now.strftime("%Y-%m-%d")
        weekday = now.weekday()
        current_time = now.strftime("%H:%M")

        logger.debug(
            f"🔍 檢查排程: 日期={today_date}, 星期={weekday}, 時間={current_time}"
        )

        # 取得今日的排程
        today_schedule = self.db.get_today_schedule()
        if not today_schedule:
            logger.info("📅 今日沒有排程（週表可能刷新失敗或資料缺失）")
            return

        # 過濾出符合當前時間且尚未推送的排程
        pending_schedule = []
        for item in today_schedule:
            scheduled_time = item.get("scheduledTime")
            pushed = item.get("pushed", False)
            video_sn = item.get("videoSn")

            # 檢查是否符合當前時間（允許1分鐘容忍度）
            if not pushed and scheduled_time:
                # 解析排程時間
                try:
                    schedule_hour, schedule_min = map(int, scheduled_time.split(":"))
                    current_hour, current_min = map(int, current_time.split(":"))

                    schedule_total_minutes = schedule_hour * 60 + schedule_min
                    current_total_minutes = current_hour * 60 + current_min

                    # 允許0~3分鐘容忍度（只在排程時間之後，防止推送舊集）
                    if 0 <= current_total_minutes - schedule_total_minutes <= 3:
                        pending_schedule.append(item)
                except ValueError:
                    logger.warning(f"⚠️ 無法解析排程時間: {scheduled_time}")
                    continue

        if not pending_schedule:
            logger.debug(f"⏰ 目前時間 {current_time} 沒有待推送的排程")
            return

        logger.info(f"📋 找到 {len(pending_schedule)} 項符合當前時間的排程")

        # 取得當季總觀看數映射（animeSn → popular），供 embed 顯示當季總數
        # （detail API 的 popular 是本集觀看數；當季總數只在 index API）
        season_popular_map = {}
        latest_video_map = {}
        try:
            recent_episodes = await fetch_all_recent_anime_from_api()
            for r in recent_episodes or []:
                r_sn = r.get("animeSn") or r.get("anime_sn")
                r_video = r.get("videoSn") or r.get("video_sn")
                if not r_sn:
                    continue
                try:
                    r_sn_int = int(r_sn)
                    season_popular_map[r_sn_int] = int(r.get("popular") or 0)
                    if r_video:
                        r_video_int = int(r_video)
                        # Keep the maximum videoSn for each animeSn (the latest episode)
                        if r_sn_int in latest_video_map:
                            latest_video_map[r_sn_int] = max(latest_video_map[r_sn_int], r_video_int)
                        else:
                            latest_video_map[r_sn_int] = r_video_int
                except (ValueError, TypeError):
                    continue
        except Exception as e:
            logger.debug(f"取得當季觀看數映射失敗: {e}")

        # 獲取頻道
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"頻道 {ANIME_CHANNEL_ID} 不存在")
            return

        for item in pending_schedule:
            video_sn = item.get("videoSn")
            if not video_sn:
                continue
            # 解析 animeData 以取得 anime_sn（若有的話）
            anime_data_str = item.get("animeData")
            anime_sn_early = 0
            if anime_data_str:
                try:
                    import json

                    anime_data_parsed = json.loads(anime_data_str)
                    anime_sn_early = int(
                        anime_data_parsed.get("anime_sn")
                        or anime_data_parsed.get("animeSn")
                        or 0
                    )
                except (json.JSONDecodeError, TypeError):
                    anime_sn_early = 0
            # 解析決議後的 videoSn：若週表有動畫資訊則使用最新集數，否則維持原始
            resolved_sn = video_sn
            if anime_sn_early and anime_sn_early in latest_video_map:
                resolved_sn = latest_video_map[anime_sn_early]
            # 防止重複推送（使用解析後的 videoSn 檢查）
            if self.db.is_notified(resolved_sn, ""):
                logger.info(
                    f"⏭️ 動畫 videoSn={resolved_sn} 已推送過（多為輪詢備案先推），排程跳過"
                )
                continue
            # 取得動畫詳細資訊
            try:
                episode_data = None
                # 如果解析後的 videoSn 與週表原始 videoSn 相同，則嘗試使用週表的 animeData
                if resolved_sn == video_sn and anime_data_str:
                    try:
                        episode_data = json.loads(anime_data_str)
                        if not episode_data.get("title"):
                            episode_data = None
                    except (json.JSONDecodeError, TypeError):
                        episode_data = None
                # 若週表沒有完整資料或 videoSn 已被更新，則從 API 獲取
                if not episode_data:
                    episode_data = await fetch_anime_details_from_api(resolved_sn)
                    if not episode_data:
                        logger.warning(
                            f"⚠️ 無法取得動畫 videoSn={resolved_sn} 的詳細資訊"
                        )
                        continue
                # 標準化資料格式（使用 resolved_sn 作為 videoSn）
                anime_sn_raw = (
                    episode_data.get("anime_sn") or episode_data.get("animeSn") or 0
                )
                try:
                    anime_sn_val = int(anime_sn_raw)
                except (ValueError, TypeError):
                    anime_sn_val = 0
                episode = {
                    "videoSn": resolved_sn,  # 使用解析後的 videoSn
                    "animeSn": anime_sn_val,
                    "title": episode_data.get("title", "未知標題"),
                    "content": episode_data.get("content", ""),
                    "cover": episode_data.get("cover", ""),
                    "description": episode_data.get(
                        "content", ""
                    ),  # embed 需要 description
                    "popular": episode_data.get("popular", 0),
                    # 當季總觀看數（index API），供 embed 顯示「總數 (平均 Y/集)」
                    "total_views": season_popular_map.get(anime_sn_val, 0),
                    "episode_count": int(
                        episode_data.get("episode_count")
                        or episode_data.get("total_volume")
                        or 0
                    ),
                    "score": episode_data.get("score", 0),
                }
                # 從週表補充資訊（如果有的話且 videoSn 未變更）
                if (
                    resolved_sn == video_sn
                    and anime_data_str
                    and isinstance(anime_data_str, str)
                    and anime_data_str.startswith("{")
                ):
                    try:
                        import json

                        anime_data_parsed = json.loads(anime_data_str)
                        episode.update(
                            {
                                "title": anime_data_parsed.get(
                                    "title", episode["title"]
                                ),
                                "content": anime_data_parsed.get(
                                    "content", episode["content"]
                                ),
                                # 嘗試獲取 episode-specific 的縮圖 - 優先使用 API 取得的資料
                                "cover": (
                                    episode["cover"]
                                    or anime_data_parsed.get("episodeCover")
                                    or anime_data_parsed.get("episodeThumb")
                                    or anime_data_parsed.get("thumb")
                                    or anime_data_parsed.get("thumbnail")
                                    or anime_data_parsed.get("videoThumb")
                                    or anime_data_parsed.get("cover")
                                ),  # 最後才使用週表的通用封面
                            }
                        )
                    except:
                        pass  # 使用 API 取得的資料
            except Exception as e:
                logger.error(f"❌ 取得動畫詳細資訊失敗 videoSn={resolved_sn}: {e}")
                continue
            # 生成 view (按鈕)
            try:
                view = await generate_anime_view(episode)
                if not view:
                    logger.warning(f"⚠️ 生成視圖失敗 videoSn={resolved_sn}")
                    continue
            except Exception as e:
                logger.error(f"❌ 生成視圖失敗 videoSn={resolved_sn}: {e}")
                continue
            # 生成 embed
            try:
                embed = await generate_anime_embed(
                    episode, push_mode="排程推送", db=self.db
                )
            except Exception as e:
                logger.error(f"❌ 生成 embed 失敗 videoSn={resolved_sn}: {e}")
                continue  # skip to next item
            # 發送訊息 (帶重試機制)
            message_sent = False
            last_send_error = None
            for attempt in range(3):
                try:
                    message = await channel.send(embed=embed, view=view, silent=True)
                    message_sent = True
                    break
                except Exception as e:
                    last_send_error = e
                    logger.warning(
                        f"⚠️ 發送失敗 (嘗試 {attempt + 1}/3) videoSn={resolved_sn}: {e}"
                    )
                    if attempt < 2:  # not the last attempt
                        await asyncio.sleep(1 * (attempt + 1))  # 1s, 2s, 4s delay
            if not message_sent:
                logger.error(f"❌ 發送失敗 videoSn={resolved_sn}: {last_send_error}")
                # 發送失敗時增加失敗計數
                self._fail_count += 1
                continue  # skip marking and move to next item
            # 只有發送成功時才進行後續處理
            if view and hasattr(view, "message_id"):
                view.message_id = message.id
            # 記錄為已推送（使用解析後的 videoSn）
            anime_sn = episode.get("animeSn", 0)
            title = episode.get("title", "未知標題")
            self.db.add_notified(
                resolved_sn,
                anime_sn,
                title,
                "",  # volume（週表中沒有這個欄位）
                episode.get("cover", ""),
            )
            # 同時更新週表的 pushed 欄位（使用原始 videoSn，因為排程行是以原始 videoSn 為キー）
            day_of_week = item.get("dayOfWeek", weekday)
            scheduled_time = item.get("scheduledTime", current_time)
            self.db.mark_time_pushed(day_of_week, scheduled_time, video_sn)
            # 註冊永久視圖
            if self.bot:
                self.bot.add_view(view, message_id=message.id)
            logger.info(f"✅ 已排程推送 Embed: {title} (videoSn={resolved_sn})")
            # 重置失敗計數（成功推送）
            self._fail_count = max(0, self._fail_count - 1)


# ========== 相容性介面 ==========


class AnimeDatabase:
    """相容性包裝：提供給舊代碼使用"""

    def __init__(self, db: AnimePushDB):
        self.db = db

    def is_notified(self, video_sn: int, volume: str = "") -> bool:
        return self.db.is_notified(video_sn, volume)

    def add_notified(
        self,
        video_sn: int,
        anime_sn: int,
        title: str,
        volume: str = "",
        cover: str = "",
    ) -> bool:
        return self.db.add_notified(video_sn, anime_sn, title, volume, cover)

    def get_notified_video_sns(self) -> set[int]:
        return self.db.get_notified_video_sns()

    # 為相容性保留的實現（委託給實際的 db 實例）
    def mark_time_pushed(self, *args, **kwargs):
        return self.db.mark_time_pushed(*args, **kwargs)

    def mark_anime_pushed(self, *args, **kwargs):
        return self.db.mark_anime_pushed(*args, **kwargs)

    def save_message_info(self, *args, **kwargs):
        return self.db.save_message_info(*args, **kwargs)

    def get_today_schedule(self, *args, **kwargs):
        return self.db.get_today_schedule(*args, **kwargs)

    def get_schedule_video_sns(self, *args, **kwargs):
        return self.db.get_schedule_video_sns(*args, **kwargs)

    def is_reward_already_given(self, *args, **kwargs):
        return self.db.is_reward_already_given(*args, **kwargs)

    def record_reward(self, *args, **kwargs):
        return self.db.record_reward(*args, **kwargs)

    def record_vote(self, *args, **kwargs):
        return self.db.record_vote(*args, **kwargs)

    def get_vote_stats(self, *args, **kwargs):
        return self.db.get_vote_stats(*args, **kwargs)

    def get_vote_comments(self, *args, **kwargs):
        return self.db.get_vote_comments(*args, **kwargs)

    def get_weekly_vote_stats(self, *args, **kwargs):
        return self.db.get_weekly_vote_stats(*args, **kwargs)

    def record_episode_stats(self, *args, **kwargs):
        return self.db.record_episode_stats(*args, **kwargs)

    def get_anime_details(self, *args, **kwargs):
        return self.db.get_anime_details(*args, **kwargs)

    def cache_anime_details(self, *args, **kwargs):
        return self.db.cache_anime_details(*args, **kwargs)

    def get_anime_statistics(self, *args, **kwargs):
        return self.db.get_anime_statistics(*args, **kwargs)

    def get_top_anime_by_views(self, *args, **kwargs):
        return self.db.get_top_anime_by_views(*args, **kwargs)

    def get_multi_episode_anime_for_chart(self, *args, **kwargs):
        return self.db.get_multi_episode_anime_for_chart(*args, **kwargs)

    def save_weekly_schedule(self, *args, **kwargs):
        return self.db.save_weekly_schedule(*args, **kwargs)

    def clean_orphaned_records(self, *args, **kwargs):
        return self.db.clean_orphaned_records(*args, **kwargs)

    def cleanup_old_weeks(self, *args, **kwargs):
        return self.db.cleanup_old_weeks(*args, **kwargs)

    @property
    def db_path(self) -> str:
        return self.db._db_path


# ========== 擴展載入入口 ==========


async def setup(bot):
    """設置擴展的入口點"""
