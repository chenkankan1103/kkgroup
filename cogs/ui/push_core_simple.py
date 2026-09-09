"""
動畫推送核心模組 - 簡化版 15分鐘輪詢 (穩定版)

核心邏輯：每 15 分鐘 → 查 API → 推送 Embed → 標記 notified
專門負責 Embed 推送（含圖片和按鈕）
使用獨立資料庫：anime_push.db
"""

import json
import logging
import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set
from zoneinfo import ZoneInfo

import aiohttp
import discord

from .bahamut_web_scraper import fetch_new_anime_from_web
from .push_embed import generate_anime_view, generate_anime_embed

logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333

# 獨立推送資料庫
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
    """動畫推送專用資料庫 - 只維護 anime_notified 表"""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or str(ANIME_PUSH_DB_PATH)
        self._init_tables()

    def _init_tables(self):
        """初始化 anime_notified 表"""
        conn = self._get_conn()
        c = conn.cursor()

        # anime_notified 表 - 唯一需要的表
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


# ========== 簡化推送核心 ==========

class SimpleAnimePushCore:
    """極簡動畫推送核心：15分鐘輪詢 (圖片版)"""

    def __init__(self, db: AnimePushDB):
        self.db = db
        self.bot = None
        self._running = False
        self._task = None

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
        """15分鐘輪詢主循環"""
        while self._running:
            try:
                await self._check_and_push(channel_id)
            except Exception as e:
                logger.error(f"❌ [SimpleAnimePushCore] 輪詢異常: {e}", exc_info=True)

            # 等待 15 分鐘 (900 秒)
            await asyncio.sleep(900)

    async def _check_and_push(self, channel_id: int):
        """檢查並推送新動畫 (僅圖片)"""
        if not self.bot:
            return

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
        for ep in new_episodes:
            video_sn = int(ep.get("videoSn", 0))
            volume = ep.get("volume", "")

            # 雙重檢查：再次確認是否已推送（防止並發）
            if self.db.is_notified(video_sn, volume):
                continue

            # 生成 view (按鈕)
            view = await generate_anime_view(ep)
            if not view:
                continue

            # 生成 embed 和發送訊息
            try:
                embed = await generate_anime_embed(ep, push_mode="輪詢 (備案模式)")
                message = await channel.send(
                    embed=embed,
                    view=view,
                    silent=True
                )

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

                logger.info(f"✅ 已推送 Embed: {title} (videoSn={video_sn}, volume={volume})")

            except Exception as e:
                logger.error(f"發送失敗 videoSn={video_sn}: {e}")


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
    def get_schedule_video_sns(*args, **kwargs): return set()
    def is_reward_already_given(*args, **kwargs): return False
    def record_reward(*args, **kwargs): return True
    def record_vote(*args, **kwargs): return True
    def get_vote_stats(*args, **kwargs): return {}
    def get_vote_comments(*args, **kwargs): return []
    def get_weekly_vote_stats(*args, **kwargs): return {}
    def record_episode_stats(*args, **kwargs): return True
    def get_anime_details(*args, **kwargs): return {}
    def cache_anime_details(*args, **kwargs): return True
    def get_anime_statistics(*args, **kwargs): return None
    def get_top_anime_by_views(*args, **kwargs): return []
    def get_multi_episode_anime_for_chart(*args, **kwargs): return []
    def save_weekly_schedule(*args, **kwargs): return True
    def clean_orphaned_records(*args, **kwargs): return {}
    def cleanup_old_weeks(*args, **kwargs): return 0

    @property
    def db_path(self) -> str:
        return self.db._db_path


# ========== 擴展載入入口 ==========

async def setup(bot):
    """設置擴展的入口點"""
    pass