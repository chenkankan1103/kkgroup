"""
動畫推送核心模組 - 增強版輪詢 with 排程檢查

核心邏輯：智能輪詢 → 檢查排程表 → 推送 → 標記 notified
保持簡單架構：移除過度設計但保留排程檢查能力
使用主要資料庫：anime_push.db (利用 anime_weekly_schedule 表)
"""

import json
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Set
from zoneinfo import ZoneInfo

import aiohttp
import discord

from .bahamut_web_scraper import fetch_new_anime_from_web

logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333

# 主要推送資料庫 (使用 anime_push.db)
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
    "Sec-CH-UA-Platform-Version": '"10.0.0"',
    "Sec-CH-UA-Full-Version-List": '"Not)A;Brand";v="99.0.0.0", "Google Chrome";v="127.0.0.0", "Chromium";v="127.0.0.0"',
}


# ========== 資料庫實現 ==========

class AnimePushDB:
    """動畫推送專用資料庫 - 維護 anime_notified 表和讀取 anime_weekly_schedule 表"""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or str(ANIME_PUSH_DB_PATH)
        self._init_tables()

    def _init_tables(self):
        """初始化 anime_notified 表和 anime_weekly_schedule 表"""
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

        # anime_weekly_schedule 表 - 存放每週動畫排程
        c.execute("""
            CREATE TABLE IF NOT EXISTS anime_weekly_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weekStartDate TEXT NOT NULL,
                dayOfWeek INTEGER NOT NULL,
                scheduledTime TEXT NOT NULL,
                pushed INTEGER DEFAULT 0,
                animeData TEXT,
                videoSn INTEGER NOT NULL,
                UNIQUE(weekStartDate, dayOfWeek, scheduledTime, videoSn)
            )
        """)

        conn.commit()
        conn.close()
        logger.info("✅ [AnimePushDB] 資料庫初始化完成: anime_push.db")

    def _get_conn(self):
        """獲取連線，啟用 WAL 模式"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = None
        conn.text_factory = str  # Use str for TEXT columns (default)
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
            c.execute("SELECT 1 FROM anime_notified WHERE videoSn=? AND volume=?", (video_sn, volume))
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

    def get_notified_video_sns(self) -> Set[int]:
        """獲取所有已通知的 videoSn（用於快速比對）"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT videoSn FROM anime_notified")
        rows = c.fetchall()
        conn.close()
        return {int(row[0]) for row in rows if row[0] is not None}

    # ---- 週表相關 ----
    def get_today_schedule(self) -> List[Dict]:
        """取得今日應該推送的動畫排程"""
        conn = self._get_conn()
        c = conn.cursor()
        try:
            now = datetime.now(TW_TZ)
            # Monday of the current week (weekStartDate)
            monday = now - timedelta(days=now.weekday())
            monday_str = monday.strftime("%Y-%m-%d")
            # 取得今天是星期幾 (1-7, 週一=1)
            weekday = now.weekday() + 1
            # 查詢今日的排程
            c.execute("""
                SELECT * FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND dayOfWeek = ?
            """, (monday_str, weekday))
            rows = c.fetchall()
            # 取得欄位名稱
            column_names = [description[0] for description in c.description]
            # 轉換為字典列表
            schedule = []
            for row in rows:
                schedule.append(dict(zip(column_names, row)))
            return schedule
        except Exception as e:
            logger.error(f"❌ [AnimePushDB] 取得今日排程失敗: {e}")
            return []
        finally:
            conn.close()

    def get_next_push_time(self) -> Optional[datetime]:
        """計算距離下次排程推送的時間"""
        conn = self._get_conn()
        c = conn.cursor()
        try:
            now = datetime.now(TW_TZ)
            # Monday of the current week (weekStartDate)
            monday_now = now - timedelta(days=now.weekday())
            monday_now_str = monday_now.strftime("%Y-%m-%d")
            weekday = now.weekday() + 1
            # 查詢今日尚未推送的排程
            c.execute("""
                SELECT scheduledTime FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND dayOfWeek = ? AND (pushed IS NULL OR pushed = 0)
                ORDER BY scheduledTime
            """, (monday_now_str, weekday))
            rows = c.fetchall()
            if rows:
                # 取得第一個未推送的時間
                next_time_str = rows[0][0]  # scheduledTime 是 HH:MM 格式
                next_time = datetime.strptime(f"{monday_now_str} {next_time_str}", "%Y-%m-%d %H:%M")
                next_time = next_time.replace(tzinfo=TW_TZ)
                if next_time > now:
                    return next_time
            # 若今日無未推送排程，找未來 7 天內的最近排程
            for offset in range(1, 8):
                check_date = now + timedelta(days=offset)
                # Monday of the check_date's week
                monday_check = check_date - timedelta(days=check_date.weekday())
                monday_check_str = monday_check.strftime("%Y-%m-%d")
                check_weekday = check_date.weekday() + 1
                c.execute("""
                    SELECT scheduledTime FROM anime_weekly_schedule
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND (pushed IS NULL OR pushed = 0)
                    ORDER BY scheduledTime LIMIT 1
                """, (monday_check_str, check_weekday))
                row = c.fetchone()
                if row:
                    next_time_str = row[0]
                    next_time = datetime.strptime(f"{monday_check_str} {next_time_str}", "%Y-%m-%d %H:%M")
                    next_time = next_time.replace(tzinfo=TW_TZ)
                    if next_time > now:
                        return next_time
            return None
        except Exception as e:
            logger.error(f"❌ [AnimePushDB] 計算下次推送時間失敗: {e}")
            return None
        finally:
            conn.close()

    def mark_time_pushed(self, day_of_week: int, scheduled_time: str, video_sn: int) -> bool:
        """標記特定時間的動畫已推送（更新週表 pushed 欄位）"""
        conn = self._get_conn()
        c = conn.cursor()
        try:
            now = datetime.now(TW_TZ)
            # Monday of the current week (weekStartDate)
            monday = now - timedelta(days=now.weekday())
            monday_str = monday.strftime("%Y-%m-%d")
            # 更新週表中的 pushed 欄位為 1
            c.execute("""
                UPDATE anime_weekly_schedule
                SET pushed = 1
                WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ? AND videoSn = ?
            """, (monday_str, day_of_week, scheduled_time, video_sn))
            conn.commit()
            updated = c.rowcount > 0
            if updated:
                logger.info(f"✅ [AnimePushDB] 標記已推送: weekStartDate={monday_str}, dayOfWeek={day_ofWeek}, time={scheduled_time}, videoSn={video_sn}")
            else:
                logger.warning(f"⚠️ [AnimePushDB] 找不到匹配的排程記錄進行標記: weekStartDate={monday_str}, dayOfWeek={day_ofWeek}, time={scheduled_time}, videoSn={video_sn}")
            return updated
        except Exception as e:
            logger.error(f"❌ [AnimePushDB] 標記已推送失敗: {e}")
            return False
        finally:
            conn.close()


# ========== API 獲取方法（保留自 ranking_stats）==========

async def fetch_all_recent_anime_from_api() -> Optional[List[Dict]]:
    """從 Bahamut API 獲取所有最近的動畫集"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
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

                logger.info(f"🔍 [fetch_all_recent_anime_from_api] 獲得 {len(unique_episodes)} 部最近的動畫")
                return unique_episodes
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
        return None
    except Exception as e:
        logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
        return None


def extract_view_count_from_episode(episode: dict, default: int = 0) -> int:
    """從 episode 物件提取觀看數"""
    view_candidates = [
        "popular", "viewCount", "counter", "views", "view_counter",
        "page_views", "click", "playCount",
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


async def fetch_anime_details_from_api(video_sn: int) -> Optional[Dict]:
    """從 Bahamut 手機 API 獲取動畫詳細信息"""
    if not video_sn:
        return None

    api_url = f"https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)"},
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                anime = data.get("data", {}).get("anime", {})
                if not anime:
                    return None

                view_count = (
                    anime.get("popular", 0)
                    or anime.get("viewCount", 0)
                    or anime.get("counter", 0)
                    or anime.get("views", 0)
                    or anime.get("view_counter", 0)
                    or anime.get("page_views", 0)
                    or 0
                )
                if not isinstance(view_count, (int, float)):
                    try:
                        view_count = int(str(view_count).replace(",", ""))
                    except (ValueError, TypeError):
                        view_count = 0

                return {
                    "anime_sn": anime.get("anime_sn"),
                    "title": anime.get("title", ""),
                    "content": anime.get("content", ""),
                    "tags": anime.get("tags", []),
                    "popular": view_count,
                    "score": anime.get("score", 0),
                }
    except Exception as e:
        logger.warning(f"⚠️ fetch_anime_details_from_api error videoSn={video_sn}: {e}")
        return None


# ========== 推送格式實現（保留原有）==========

async def _generate_anime_embed(episode: dict) -> Optional[discord.Embed]:
    """生成動畫推送 embed"""
    try:
        title = episode.get("title", "未知標題")
        cover = episode.get("cover", "")
        description = episode.get("description", "")

        embed = discord.Embed(
            title=title, description=description, color=discord.Color.blue()
        )

        if cover:
            embed.set_image(url=cover)

        return embed
    except Exception as e:
        logger.error(f"生成 embed 失敗: {e}")
        return None


async def _generate_anime_view(episode: dict):
    """生成動畫推送視圖"""
    try:
        from shared.utils.embed_views import create_anime_push_view
        return create_anime_push_view(episode)
    except Exception as e:
        logger.error(f"生成 view 失敗: {e}")
        return None


# ========== 簡化推送核心 ==========

class SimpleAnimePushCore:
    """增強動畫推送核心：智能排程檢查"""

    def __init__(self, db: AnimePushDB):
        self.db = db
        self.bot = None
        self._running = False
        self._task = None

    def set_bot(self, bot):
        self.bot = bot

    async def start_polling(self, channel_id: int):
        """啟動智能排程檢查"""
        if self._running:
            logger.warning("排程檢查已在運行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._schedule_loop(channel_id))
        logger.info("🚀 [SimpleAnimePushCore] 智能排程檢查已啟動")

    async def stop_polling(self):
        """停止排程檢查"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 [SimpleAnimePushCore] 排程檢查已停止")

    async def _schedule_loop(self, channel_id: int):
        """智能排程檢查主循環"""
        while self._running:
            try:
                # 取得下次推送時間
                next_push = self.db.get_next_push_time()
                if next_push is None:
                    # 沒有即將到來的排程，先檢查是否有過去未推送的排程
                    await self._check_and_push_schedule(channel_id)
                    # 休息較長時間以避免頻繁檢查（例如 30 分鐘）
                    await asyncio.sleep(1800)
                    continue
                now = datetime.now(TW_TZ)
                wait_seconds = (next_push - now).total_seconds()
                if wait_seconds > 0:
                    # 休息但不超過 30 分鐘（避免因時間異常錯過排程）
                    sleep_time = min(wait_seconds, 1800)
                    await asyncio.sleep(sleep_time)
                # 休息後再次檢查是否真的到達推送時間
                await self._check_and_push_schedule(channel_id)
            except Exception as e:
                logger.error(f"❌ [SimpleAnimePushCore] 排程循環異常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 發生錯誤時休息一分鐘

    async def _check_and_push_schedule(self, channel_id: int):
        """檢查當前時間的排程並推送（包括過去未推送的排程）"""
        if not self.bot:
            return
        now = datetime.now(TW_TZ)
        # 取得本週的週一日期 (不含時分)
        monday = now - timedelta(days=now.weekday())
        monday_str = monday.strftime("%Y-%m-%d")
        # 產生週一 00:00:00 的 datetime 物件 (無時區)
        monday_naive = datetime.strptime(monday_str, "%Y-%m-%d")

        # 取得本週的排程
        conn = self._get_conn()
        c = conn.cursor()
        try:
            c.execute("""
                SELECT * FROM anime_weekly_schedule
                WHERE weekStartDate = ?
            """, (monday_str,))
            rows = c.fetchall()
            column_names = [description[0] for description in c.description]
            schedule = []
            for row in rows:
                schedule.append(dict(zip(column_names, row)))
        except Exception as e:
            logger.error(f"❌ [AnimePushDB] 取得本週排程失敗: {e}")
            return
        finally:
            conn.close()

        pushed_any = False
        for item in schedule:
            # 如果已標記為已推送，則跳過
            if item.get("pushed", 1) == 1:
                continue
            day_of_week = item.get("dayOfWeek")
            scheduled_time = item.get("scheduledTime")
            video_sn = item.get("videoSn")
            if day_of_week is None or scheduled_time is None or video_sn is None:
                continue

            # 計算此排程項目應該推送的日期時間
            try:
                # 週一 + (dayOfWeek-1) 天
                schedule_date = monday_naive + timedelta(days=day_of_week-1)
                # 合併日期和時間
                schedule_datetime = datetime.strptime(f"{schedule_date.strftime('%Y-%m-%d')} {scheduled_time}", "%Y-%m-%d %H:%M")
                schedule_datetime = schedule_datetime.replace(tzinfo=TW_TZ)
            except Exception as e:
                logger.error(f"❌ [SimpleAnimePushCore] 解析排程時間失敗: {e}")
                continue

            # 如果排程時間在未來，則跳過
            if schedule_datetime > now:
                continue

            # 此排程項目已到達推送時間且未推送
            episode = await fetch_anime_details_from_api(video_sn)
            if not episode:
                logger.warning(f"⚠️ [SimpleAnimePushCore] 無法獲取動畫詳情 videoSn={video_sn}")
                continue
            embed = await _generate_anime_embed(episode)
            view = await _generate_anime_view(episode)
            if not embed or not view:
                continue
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.send(embed=embed, view=view, silent=True)
                    if view and hasattr(view, "message_id"):
                        view.message_id = message.id
                    anime_sn = episode.get("anime_sn")
                    title = episode.get("title")
                    volume = episode.get("volume", "")
                    cover = episode.get("cover", "")
                    self.db.add_notified(video_sn, anime_sn, title, volume, cover)
                    # 標記排程為已推送
                    self.db.mark_time_pushed(day_of_week, scheduled_time, video_sn)
                    if self.bot:
                        self.bot.add_view(view, message_id=message.id)
                    logger.info(f"✅ [SimpleAnimePushCore] 推送排程動畫: {title} (videoSn={video_sn})")
                    pushed_any = True
                except Exception as e:
                    logger.error(f"❌ [SimpleAnimePushCore] 發送失敗 videoSn={video_sn}: {e}")
            else:
                logger.warning(f"頻道 {ANIME_CHANNEL_ID} 不存在或非文字頻道")

        # 如果已推送任何項目，休息一下避免同一分鐘內重複推送（依賴 pushed 標記也會防止）
        if pushed_any:
            await asyncio.sleep(60)  # 推送後休息一分鐘

    # 保留 _check_and_push 方法以相容手動觸發（但改為排程檢查）
    async def _check_and_push(self, channel_id: int):
        """手動觸發時的檢查與推送（基於當前時間的排程）"""
        await self._check_and_push_schedule(channel_id)


# ========== 相容性介面 ==========

class AnimeDatabase:
    """相容性包裝：提供給舊代碼使用"""

    def __init__(self, db: AnimePushDB):
        self.db = db

    def is_notified(self, video_sn: int, volume: str = "") -> bool:
        return self.db.is_notified(video_sn, volume)

    def add_notified(self, video_sn: int, anime_sn: int, title: str, volume: str = "", cover: str = "") -> bool:
        return self.db.add_notified(video_sn, anime_sn, title, volume, cover)

    def get_notified_video_sns(self) -> Set[int]:
        return self.db.get_notified_video_sns()

    # 為相容性保留的空實現
    def mark_time_pushed(self, *args, **kwargs): return True
    def mark_anime_pushed(self, *args, **kwargs): return True
    def save_message_info(self, *args, **kwargs): return True
    def get_today_schedule(self, *args, **kwargs): return []
    def get_schedule_video_sns(self, *args, **kwargs): return set()
    def is_reward_already_given(self, *args, **kwargs): return False
    def record_reward(self, *args, **kwargs): return True
    def record_vote(self, *args, **kwargs): return True
    def get_vote_stats(self, *args, **kwargs): return {}
    def get_vote_comments(self, *args, **kwargs): return []
    def get_weekly_vote_stats(self, *args, **kwargs): return {}
    def record_episode_stats(self, *args, **kwargs): return True
    def get_anime_details(self, *args, **kwargs): return {}
    def cache_anime_details(self, *args, **kwargs): return True
    def get_anime_statistics(self, *args, **kwargs): return None
    def get_top_anime_by_views(self, *args, **kwargs): return []
    def get_multi_episode_anime_for_chart(self, *args, **kwargs): return []
    def save_weekly_schedule(self, *args, **kwargs): return True
    def clean_orphaned_records(self, *args, **kwargs): return {}
    def cleanup_old_weeks(self, *args, **kwargs): return 0

    @property
    def db_path(self) -> str:
        return self.db._db_path


async def setup(bot):
    """Setup function for extension loading."""
    pass