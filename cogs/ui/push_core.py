# -*- coding: utf-8 -*-
"""
動畫推送核心模組 - 極簡版

核心邏輯：時間到 → 查 API → 推送 → 標記 push=1
補推邏輯：偵測 push=0 且時間已過 → 未超過 1 小時 → 推送；超過 1 小時 → 標記 pushed 並放棄

移除所有過度設計：retry/lock/exhausted/catchup 等複雜機制
"""

import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# 常數
TW_TZ = ZoneInfo("Asia/Taipei")
API_ENDPOINT = "https://ani.gamer.com.tw/animeList.php?type=newAnime"
API_TIMEOUT = 15
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


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

    def set_bot(self, bot):
        """設置 bot 實例"""
        self.bot = bot

    # ========== 核心查詢方法 ==========

    def is_notified(self, video_sn: int) -> bool:
        """檢查 video_sn 是否已推送過 (anime_notified 表)"""
        try:
            return self.db.is_notified(video_sn)
        except Exception as e:
            logger.error(f"is_notified 錯誤 video_sn={video_sn}: {e}")
            return False

    def add_notified(self, video_sn: int, anime_sn: int, title: str, volume: str = "", cover: str = "") -> bool:
        """記錄已推送 - 使用 INSERT OR IGNORE 避免重複"""
        try:
            return self.db.add_notified(video_sn, anime_sn, title, volume, cover)
        except Exception as e:
            logger.error(f"add_notified 錯誤 video_sn={video_sn}: {e}")
            return False

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記某個時刻已推送過 (anime_weekly_schedule 表)"""
        try:
            return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
        except Exception as e:
            logger.error(f"mark_time_pushed 錯誤: {e}")
            return False

    # ========== API 獲取 ==========

    async def _fetch_new_anime_from_api(self) -> List[Dict]:
        """從 API 獲取新番資料"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout, headers=API_HEADERS) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        logger.warning(f"API 回傳狀態碼 {resp.status}")
                        return []
                    data = await resp.json()
                    new_anime = data.get("data", {}).get("newAnime")
                    if not new_anime or "date" not in new_anime:
                        return []
                    return new_anime.get("date", [])
        except Exception as e:
            logger.error(f"API 呼叫失敗: {e}")
            return []

    # ========== 核心推送流程 ==========

    async def send_anime_push(
        self,
        scheduled_time: str,
        channel_id: int,
        day_of_week: Optional[int] = None,
        week_start_date: Optional[str] = None,
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
            week_start_date = get_week_start_date(now, api_week=False)  # Dispatcher 用本週

        logger.info(f"🚀 [send_anime_push] 開始 {scheduled_time} (week={week_start_date}, day={day_of_week})")

        # 1. 取得該時段的預期 videoSn (從週表)
        expected_video_sns = self.db.get_schedule_video_sns(week_start_date, day_of_week, scheduled_time)

        if not expected_video_sns:
            logger.info(f"📭 無預期 videoSn，標記時刻完成並結束")
            self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
            return False

        # 2. 篩選出尚未推送的 videoSn (去除已 pushed=1 的)
        pushed_video_sns = {
            item["video_sn"] for item in self.db.get_today_schedule()
            if item["scheduled_time"] == scheduled_time and item.get("pushed")
        }
        pending_video_sns = expected_video_sns - pushed_video_sns

        if not pending_video_sns:
            logger.info(f"⏭️ 所有預期動畫已推送 ({expected_video_sns})")
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

        # 4. 呼叫 API 獲取最新動畫資料
        episodes = await self._fetch_new_anime_from_api()
        if not episodes:
            logger.warning("API 無回應")
            return False

        # 5. 過濾今日上架的集數
        today_str = now.strftime("%m/%d")
        today_episodes = [ep for ep in episodes if ep.get("upTime", "").strip() == today_str]

        if not today_episodes:
            logger.warning(f"今日無新番 (API 回傳 {len(episodes)} 筆 but upTime!=today)")
            return False

        logger.info(f"📅 今日集數: {len(today_episodes)} 筆")

        # 6. 配對並推送：每個 pending_videoSn 找對應的 today_episodes
        sent_count = 0
        matched_videosns: Set[int] = set()

        for video_sn in pending_video_sns:
            # 在 today_episodes 中找 matching videoSn
            matched_ep = None
            for ep in today_episodes:
                ep_vsn = ep.get("videoSn")
                if ep_vsn:
                    try:
                        if int(ep_vsn) == video_sn:
                            matched_ep = ep
                            break
                    except (ValueError, TypeError):
                        continue

            if matched_ep is None:
                logger.warning(f"week 表有 videoSn={video_sn} 但 API 當日無對應資料，略過")
                continue

            # 7. 雙重去重檢查：anime_notified + week pushed
            if self.is_notified(video_sn):
                logger.info(f"⏭️ videoSn={video_sn} 已在 notified 表，標記 pushed 並略過")
                self.db.mark_anime_pushed(week_start_date, day_of_week, scheduled_time, video_sn)
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
                self.db.save_message_info(message.id, video_sn, anime_sn, title, channel_id)
                self.add_notified(video_sn, anime_sn, title, matched_ep.get("volume", ""), matched_ep.get("cover", ""))

                # 註冊永久視圖
                if self.bot is not None:
                    self.bot.add_view(view, message_id=message.id)

                # 標記 pushed=1
                self.db.mark_anime_pushed(week_start_date, day_of_week, scheduled_time, video_sn)
                matched_videosns.add(video_sn)
                sent_count += 1
                logger.info(f"✅ 已推送: {title} (videoSn={video_sn})")

            except Exception as e:
                logger.error(f"發送失敗 videoSn={video_sn}: {e}")
                continue

        # 10. 若該時段所有預期都已推送，標記時刻完成
        if expected_video_sns.issubset(pushed_video_sns | matched_videosns):
            self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
            logger.info(f"✅ 時刻 {scheduled_time} 全部完成")

        return sent_count > 0

    # ========== Embed & View 生成 (保留原有邏輯) ==========

    async def _generate_anime_embed(self, episode: Dict) -> Optional[discord.Embed]:
        """生成動畫推送 embed - 大圖在下方"""
        try:
            import discord
            title = episode.get("title", "未知標題")
            cover = episode.get("cover", "")
            description = episode.get("description", "")

            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue()
            )

            if cover:
                embed.set_image(url=cover)  # 大圖在下方

            return embed
        except Exception as e:
            logger.error(f"生成 embed 失敗: {e}")
            return None

    async def _generate_anime_view(self, episode: Dict):
        """生成動畫推送視圖"""
        try:
            # 這裡保留原有的 view 生成邏輯，或從原檔複製
            from shared.utils.embed_views import create_anime_push_view
            return create_anime_push_view(episode)
        except Exception as e:
            logger.error(f"生成 view 失敗: {e}")
            return None


# ========== 為了相容性保留的介面 (scheduled_tasks 用) ==========

async def push_new_anime_episodes(bot, channel_id: int, db, target_time: str = None, test_mode: bool = False) -> bool:
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
        # 推送指定時刻
        return await core.send_anime_push(target_time, channel_id, day_of_week, week_start_date)
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
            results.append(await core.send_anime_push(st, channel_id, day_of_week, week_start_date))

        return any(results)


# ========== 相容性介面：供 ranking_stats.py、schedule_tracker.py 透過 __getattr__ 呼叫 ==========
# 這些方法一律委託給 self.db (真正的資料庫適配器)，保持與舊版 AnimeDatabase 相同介面

class AnimeDatabase:
    """相容性包裝：將舊版 AnimeDatabase 介面委託給 db adapter"""

    def __init__(self, db):
        self.db = db

    # ---- 通知/推送相關 ----
    def is_notified(self, video_sn: int) -> bool:
        return self.db.is_notified(video_sn)

    def add_notified(self, video_sn: int, anime_sn: int, title: str, volume: str = "", cover: str = "") -> bool:
        return self.db.add_notified(video_sn, anime_sn, title, volume, cover)

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)

    def mark_anime_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str, video_sn: int) -> bool:
        return self.db.mark_anime_pushed(week_start_date, day_of_week, scheduled_time, video_sn)

    def save_message_info(self, message_id: int, video_sn: int, anime_sn: int, title: str, channel_id: int) -> bool:
        return self.db.save_message_info(message_id, video_sn, anime_sn, title, channel_id)

    # ---- 時程查詢 ----
    def get_today_schedule(self) -> list:
        return self.db.get_today_schedule()

    def get_schedule_video_sns(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> set:
        return self.db.get_schedule_video_sns(week_start_date, day_of_week, scheduled_time)

    # ---- 獎勵系統 ----
    def is_reward_already_given(self, user_id: int, message_id: int, reward_type: str) -> bool:
        return self.db.is_reward_already_given(user_id, message_id, reward_type)

    def record_reward(self, user_id: int, message_id: int, reward_type: str, reward_amount: int) -> bool:
        return self.db.record_reward(user_id, message_id, reward_type, reward_amount)

    # ---- 投票系統 ----
    def record_vote(self, video_sn: int, anime_sn: int, message_id: int, vote_type: str, comment: str = None, user_hash: str = None) -> bool:
        return self.db.record_vote(video_sn, anime_sn, message_id, vote_type, comment, user_hash)

    def get_vote_stats(self, message_id: int) -> dict:
        return self.db.get_vote_stats(message_id)

    def get_vote_comments(self, message_id: int, limit: int = 5) -> list:
        return self.db.get_vote_comments(message_id, limit)

    def get_weekly_vote_stats(self) -> dict:
        return self.db.get_weekly_vote_stats()

    # ---- 統計/快取 ----
    def record_episode_stats(self, video_sn: int, anime_sn: int, episode_num: str, views: int, score: float) -> bool:
        return self.db.record_episode_stats(video_sn, anime_sn, episode_num, views, score)

    def get_anime_details(self, anime_sn: int) -> dict:
        return self.db.get_anime_details(anime_sn)

    def cache_anime_details(self, anime_sn: int, title: str, content: str, cover: str, tags: list, views: int, score: float) -> bool:
        return self.db.cache_anime_details(anime_sn, title, content, cover, tags, views, score)

    # ---- 維護 ----
    def clean_orphaned_records(self, week_start_date: str) -> dict:
        return self.db.clean_orphaned_records(week_start_date)

    def cleanup_old_weeks(self) -> int:
        return self.db.cleanup_old_weeks()