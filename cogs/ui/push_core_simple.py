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
import sys

import aiohttp
import discord

# Add kkgroup directory to sys.path for absolute imports
kkgroup_dir = Path(__file__).resolve().parent.parent.parent
if str(kkgroup_dir) not in sys.path:
    sys.path.insert(0, str(kkgroup_dir))

from cogs.ui.bahamut_web_scraper import fetch_new_anime_from_web
from cogs.ui.push_embed import generate_anime_view, generate_anime_embed

logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
ANIME_CHANNEL_ID = 1252204317453324333

# 獨立推送資料庫
ANIME_PUSH_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"

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

    # ====== 新增：週表相關方法 ======

    def get_today_schedule(self) -> List[Dict]:
        """查詢今日應該推送的動畫排程"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 取得今天的日期和星期
            now = datetime.now(TW_TZ)
            today_date = now.strftime("%Y-%m-%d")
            # 星期：0=週一, 6=週日
            weekday = now.weekday()
            today_time = now.strftime("%H:%M")

            # 查詢今日的排程
            c.execute("""
                SELECT * FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND dayOfWeek = ? AND pushed = 0
            """, (today_date, weekday))

            rows = c.fetchall()
            conn.close()

            # 轉換為字典列表
            schedule = []
            for row in rows:
                # 假設表結構為：id, weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn
                schedule.append({
                    "id": row[0],
                    "weekStartDate": row[1],
                    "dayOfWeek": row[2],
                    "scheduledTime": row[3],
                    "pushed": bool(row[4]),
                    "animeData": row[5],  # 這可能是JSON字符串
                    "videoSn": row[6]
                })

            return schedule
        except Exception as e:
            logger.error(f"❌ 查詢今日排程失敗: {e}")
            return []

    def get_next_push_time(self) -> Optional[datetime]:
        """計算距離下次排程推送的時間"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 取得現在時間
            now = datetime.now(TW_TZ)
            today_date = now.strftime("%Y-%m-%d")
            weekday = now.weekday()
            current_time = now.strftime("%H:%M")

            # 查詢今日尚未推送的排程
            c.execute("""
                SELECT scheduledTime FROM anime_weekly_schedule
                WHERE weekStartDate = ? AND dayOfWeek = ? AND pushed = 0
                ORDER BY scheduledTime ASC
            """, (today_date, weekday))

            today_schedule = c.fetchall()

            # 查詢未來日期的排程（從明天開始）
            # 我們只需要查詢未來7天內的最近一個排程
            for days_ahead in range(1, 8):  # 未來1到7天
                target_date = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                target_weekday = (now + timedelta(days=days_ahead)).weekday()

                c.execute("""
                    SELECT MIN(scheduledTime) FROM anime_weekly_schedule
                    WHERE weekStartDate = ? AND dayOfWeek = ? AND pushed = 0
                """, (target_date, target_weekday))

                result = c.fetchone()
                if result and result[0]:
                    # 找到了未來某一天的最近排程
                    target_time = result[0]
                    target_datetime = datetime.strptime(f"{target_date} {target_time}", "%Y-%m-%d %H:%M")
                    target_datetime = TW_TZ.localize(target_datetime)
                    conn.close()
                    return target_datetime

            # 如果今日有未推送的排程，返回最早的一個
            if today_schedule:
                earliest_time = today_schedule[0][0]  # 因為我們已經按時間排序了
                # 但需要確認這個時間是否已經過去了
                earliest_datetime = datetime.strptime(f"{today_date} {earliest_time}", "%Y-%m-%d %H:%M")
                earliest_datetime = TW_TZ.localize(earliest_datetime)

                if earliest_datetime > now:
                    conn.close()
                    return earliest_datetime

            conn.close()
            return None  # 沒有找到未來的排程
        except Exception as e:
            logger.error(f"❌ 計算下次推送時間失敗: {e}")
            return None

    def mark_time_pushed(self, day_of_week: int, scheduled_time: str, video_sn: int) -> bool:
        """標記特定時間的動畫已推送"""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # 取得今天的日期（週StartDate）
            now = datetime.now(TW_TZ)
            today_date = now.strftime("%Y-%m-%d")

            # 更新對應的記錄
            c.execute("""
                UPDATE anime_weekly_schedule
                SET pushed = 1
                WHERE weekStartDate = ? AND dayOfWeek = ? AND scheduledTime = ? AND videoSn = ?
            """, (today_date, day_of_week, scheduled_time, video_sn))

            conn.commit()
            conn.close()

            logger.debug(f"✅ 標記排程為已推送: videoSn={video_sn}, day={day_of_week}, time={scheduled_time}")
            return True
        except Exception as e:
            logger.error(f"❌ 標記排程為已推送失敗: {e}")
            return False


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

        logger.debug(f"😴 智能睡眠 {sleep_seconds:.0f} 秒直到下次推送時間: {next_push_time}")

        # 睡眠
        await asyncio.sleep(sleep_seconds)

        # 再次檢查時間（防止系統時間異常或睡眠被提前結束）
        now = datetime.now(TW_TZ)
        if now >= next_push_time:
            # 到達推送時間，檢查並推送當前時間的排程
            await self._check_and_push_schedule(channel_id)
        else:
            # 時間還沒到，這不應該發生，但為安全起見繼續循環
            logger.debug(f"⏰ 睡眠結束但尚未到達推送時間，當前時間: {now}, 推送時間: {next_push_time}")

    async def _fallback_polling_loop(self, channel_id: int):
        """備案模式：原始15分鐘輪詢"""
        logger.info("🔄 進入備案模式：使用原始15分鐘輪詢")
        await self._check_and_push(channel_id)

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

            # 取得詳細資訊（含簡介）
            try:
                details = await fetch_anime_details_from_api(video_sn)
                if details:
                    ep = {**ep, "description": details.get("content", "")}
            except Exception as e:
                logger.debug(f"取得動畫詳細資訊失敗 videoSn={video_sn}: {e}")

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

    async def _check_and_push_schedule(self, channel_id: int):
        """根據當前時間的排程檢查並推送動畫"""
        if not self.bot:
            return

        # 取得現在時間
        now = datetime.now(TW_TZ)
        today_date = now.strftime("%Y-%m-%d")
        weekday = now.weekday()
        current_time = now.strftime("%H:%M")

        logger.debug(f"🔍 檢查排程: 日期={today_date}, 星期={weekday}, 時間={current_time}")

        # 取得今日的排程
        today_schedule = self.db.get_today_schedule()
        if not today_schedule:
            logger.debug("📅 今日沒有排程")
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

                    # 允許1分鐘容忍度（前後各30秒）
                    if abs(schedule_total_minutes - current_total_minutes) <= 1:
                        pending_schedule.append(item)
                except ValueError:
                    logger.warning(f"⚠️ 無法解析排程時間: {scheduled_time}")
                    continue

        if not pending_schedule:
            logger.debug(f"⏰ 目前時間 {current_time} 沒有待推送的排程")
            return

        logger.info(f"📋 找到 {len(pending_schedule)} 項符合當前時間的排程")

        # 獲取頻道
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"頻道 {ANIME_CHANNEL_ID} 不存在")
            return

        # 處理每個待推送的排程
        for item in pending_schedule:
            video_sn = item.get("videoSn")
            if not video_sn:
                continue

            # 雙重檢查：確認尚未推送（防止競爭條件）
            if self.db.is_notified(video_sn, ""):
                logger.debug(f"⏭️ 動畫 videoSn={video_sn} 已經推送過，跳過")
                continue

            # 取得動畫詳細資訊
            try:
                # 嘗試從週表的 animeData 欄位取得詳細資訊
                anime_data_str = item.get("animeData")
                episode_data = None

                if anime_data_str:
                    try:
                        # 嘗試解析 JSON
                        import json
                        episode_data = json.loads(anime_data_str)
                        # 確保有必要的欄位
                        if not episode_data.get("title"):
                            episode_data = None
                    except (json.JSONDecodeError, TypeError):
                        episode_data = None

                # 如果週表沒有完整資料，則從 API 獲取
                if not episode_data:
                    episode_data = await fetch_anime_details_from_api(video_sn)
                    if not episode_data:
                        logger.warning(f"⚠️ 無法取得動畫 videoSn={video_sn} 的詳細資訊")
                        continue

                # 標準化資料格式
                episode = {
                    "videoSn": video_sn,
                    "animeSn": episode_data.get("anime_sn", 0),
                    "title": episode_data.get("title", "未知標題"),
                    "content": episode_data.get("content", ""),
                    "cover": episode_data.get("cover", ""),
                    "description": episode_data.get("content", ""),  # embed 需要 description
                    "popular": episode_data.get("popular", 0),
                    "score": episode_data.get("score", 0),
                }

                # 從週表補充資訊（如果有的話）
                if anime_data_str and isinstance(anime_data_str, str) and anime_data_str.startswith('{'):
                    try:
                        import json
                        anime_data_parsed = json.loads(anime_data_str)
                        episode.update({
                            "title": anime_data_parsed.get("title", episode["title"]),
                            "content": anime_data_parsed.get("content", episode["content"]),
                            "cover": anime_data_parsed.get("cover", episode["cover"]),
                        })
                    except:
                        pass  # 使用 API 取得的資料

            except Exception as e:
                logger.error(f"❌ 取得動畫詳細資訊失敗 videoSn={video_sn}: {e}")
                continue

            # 生成 view (按鈕)
            try:
                view = await generate_anime_view(episode)
                if not view:
                    logger.warning(f"⚠️ 生成視圖失敗 videoSn={video_sn}")
                    continue
            except Exception as e:
                logger.error(f"❌ 生成視圖失敗 videoSn={video_sn}: {e}")
                continue

            # 生成 embed 和發送訊息
            try:
                embed = await generate_anime_embed(episode, push_mode="排程推送")
                message = await channel.send(
                    embed=embed,
                    view=view,
                    silent=True
                )

                if view and hasattr(view, "message_id"):
                    view.message_id = message.id

                # 記錄為已推送
                anime_sn = episode.get("animeSn", 0)
                title = episode.get("title", "未知標題")
                self.db.add_notified(
                    video_sn,
                    anime_sn,
                    title,
                    "",  # volume（週表中沒有這個欄位）
                    episode.get("cover", ""),
                )

                # 同時更新週表的 pushed 欄位
                day_of_week = item.get("dayOfWeek", weekday)
                scheduled_time = item.get("scheduledTime", current_time)
                self.db.mark_time_pushed(day_of_week, scheduled_time, video_sn)

                # 註冊永久視圖
                if self.bot:
                    self.bot.add_view(view, message_id=message.id)

                logger.info(f"✅ 已排程推送 Embed: {title} (videoSn={video_sn})")

                # 重置失敗計數（成功推送）
                self._fail_count = max(0, self._fail_count - 1)

            except Exception as e:
                logger.error(f"❌ 發送失敗 videoSn={video_sn}: {e}")
                # 發送失敗時增加失敗計數
                self._fail_count += 1

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