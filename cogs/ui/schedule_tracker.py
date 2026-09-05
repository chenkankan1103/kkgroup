# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 週表排程系統

負責週表機制：
- 每天 02:00 自動從 Bahamut API 下載完整一週時程表
- 將時程表儲存到本地資料庫 (anime_weekly_schedule 表)
- 大幅減少 API 呼叫頻率：從每天 288 次減少到每天 1 次

此設計解決機器人重啟時可能錯過推送時刻的問題：
- 週表機制保證每個時刻只會被檢查一次
- 重啟時由 APScheduler 排程系統確保時準推送
"""

import logging
from datetime import datetime, timedelta
import asyncio
import aiohttp
from .push_core import (
    TW_TZ,
    API_ENDPOINT,
    API_TIMEOUT,
    API_HEADERS,
    get_week_start_date,
)

# 嘗試導入 BahamutWebScraper
try:
    from .bahamut_web_scraper import BahamutWebScraper
except ImportError:
    BahamutWebScraper = None

logger = logging.getLogger(__name__)


class AnimeScheduleTracker:
    """週表排程管理器 - 與 AnimeDatabase 合作實現週表機制"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.db = None
        self._last_fallback_check = None
        self._last_schedule_fallback = None
        self._last_run_date = None

    def set_dependencies(self, bot, db, push_core, anime_tracker=None):
        """設置依賴"""
        self.bot = bot
        self.db = db
        self.push_core = push_core
        self.anime_tracker = anime_tracker

    async def _get_anime_schedule(self) -> dict:
        """從 API 獲取日程表

        注意：新版 API 已改版為 data.animeList (分頁)，不再提供按星期分組的 newAnimeSchedule 格式。
        因此此方法直接返回空字典，讓 refresh_weekly_schedule 改用首頁爬蟲作為主要資料來源。
        """
        logger.info("📡 新版 API 不再提供按星期分組的資料，改用首頁爬蟲獲取週表")
        return {}

    async def _get_anime_schedule_from_homepage(self) -> dict:
        """從首頁爬取日程表 (備用方案 - 當 API 失效時使用)

        Returns:
            dict: 模擬 API 格式的時程表 { "1": [...], "2": [...], ... }
        """
        if BahamutWebScraper is None:
            logger.warning("⚠️ [_get_anime_schedule_from_homepage] BahamutWebScraper 不可用")
            return {}

        try:
            scraper = BahamutWebScraper()
            homepage_schedule = await scraper.fetch_weekly_schedule_from_homepage()

            if not homepage_schedule:
                logger.warning("⚠️ [_get_anime_schedule_from_homepage] 首頁爬取無資料")
                return {}

            # 將首頁爬取的資料轉換為 API 相容格式
            schedule = {}
            for entry in homepage_schedule:
                day_str = str(entry['day_of_week'])
                if day_str not in schedule:
                    schedule[day_str] = []

                schedule[day_str].append({
                    'videoSn': entry['video_sn'],
                    'animeSn': entry['anime_sn'],
                    'scheduleTime': entry['scheduled_time'],
                    'animeTitle': entry['title'],
                    'episode': entry['episode']
                })

            logger.info(f"✅ [_get_anime_schedule_from_homepage] 從首頁獲取到 {len(homepage_schedule)} 筆時程")
            return schedule

        except Exception as e:
            logger.error(f"❌ [_get_anime_schedule_from_homepage] 首頁爬取失敗: {e}")
            return {}

    def _get_expected_check_times(self, schedule: dict, now: datetime) -> list:
        """取得今天和明天的所有預期檢查時刻

        修復: 移除 1 小時過濾，改用日期過濾，防止凌晨時同日時刻被篩除
        例如: 凌公元 03:59 時 01:00 不應被過濾
        """
        check_times = []
        weekday_today = (now.weekday() + 1) % 7 or 7
        weekday_tomorrow = (weekday_today % 7) + 1

        for day_offset, weekday in [
            (0, str(weekday_today)),
            (1, str(weekday_tomorrow)),
        ]:
            target_date = (now + timedelta(days=day_offset)).date()
            for anime_info in schedule.get(weekday, []):
                schedule_time = anime_info.get("scheduleTime", "")
                if schedule_time:
                    try:
                        scheduled_time = datetime.strptime(
                            schedule_time, "%H:%M"
                        ).time()
                        scheduled_dt = datetime.combine(
                            target_date, scheduled_time, tzinfo=TW_TZ
                        )
                        # 改用日期過濾：超過 1 天的時刻才篩除，同日所有時刻都保留
                        # 這防止凌晨時早晨時刻被篩除（例如: 凌公元 03:59 時 01:00 不應被篩除）
                        if scheduled_dt.date() >= (now - timedelta(days=1)).date():
                            check_times.append(scheduled_dt)
                    except ValueError as e:
                        logger.warning(
                            f"⚠️ [_get_expected_check_times] 無法解析時間格式 '{schedule_time}': {e}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ [_get_expected_check_times] 處理時間時發生未預期錯誤 '{schedule_time}': {e}",
                            exc_info=True,
                        )

        return sorted(check_times)

    async def refresh_weekly_schedule(self, force: bool = False) -> dict:
        """
        每天 02:00 拉取完整週表並全量覆蓋 - 兼具「填滿行事曆」與「檢查漏推」功能

        流程：
        1. 呼叫 newAnimeSchedule API 取得 7 天時程表
        2. 使用 BahamutWebScraper 爬取 animeSn <-> videoSn 映射關係
        3. 豐富 anime_data 使其包含 animeSn
        4. 以「本週一」為 week_start_date 全量覆蓋 anime_weekly_schedule 表
        5. 回傳今日時程供上層檢查 <=02:00 的漏推項目

        Args:
            force: 如果為 True，則忽略時間限制並強制執行週表更新

        Returns:
            dict: {
                'success': bool,
                'week_start_date': str,
                'today_schedule': list,  # 今日所有時程（含 pushed 狀態）
                'total_count': int
            }
        """
        now = datetime.now(TW_TZ)
        current_time_str = now.strftime("%H:%M")

        try:
            # 每天 02:00 執行（除非強制執行）
            if not force:
                # 限制為每日一次，且在 02:00 時段執行（容忍分鐘誤差）
                if now.hour != 2:
                    logger.debug("⏭️ [refresh_weekly_schedule] 跳過（非凌晨 2 點時段）")
                    return {"success": False, "skipped": True}
                # 防止同一天重複執行多次
                if self._last_run_date == now.date():
                    logger.debug("⏭️ [refresh_weekly_schedule] 今日已執行過，跳過")
                    return {"success": False, "skipped": True}

            logger.info("🔄 [refresh_weekly_schedule] 開始拉取本週時程表...")

            # 拉取完整一週的時程表 (優先使用 API，失敗則嘗試首頁爬取)
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [refresh_weekly_schedule] API 拉取失敗，嘗試從首頁爬取...")
                schedule = await self._get_anime_schedule_from_homepage()
                if not schedule:
                    logger.error("❌ [refresh_weekly_schedule] API 和首頁爬取均失敗")
                    return {"success": False, "error": "所有來源皆無法取得時程表"}
                else:
                    logger.info("✅ [refresh_weekly_schedule] 成功從首頁爬取到時程表")

            # 🔑 正確計算 week_start_date (api_week=True: 用於儲存從 API 拉取的週表)
            week_start_str = get_week_start_date(now, api_week=True)
            logger.info(
                f"📅 [refresh_weekly_schedule] 保存週起始日期: {week_start_str} (today={now.strftime('%Y-%m-%d %a')})"
            )

            # 使用爬蟲建立 videoSn -> animeSn 映射表
            video_to_anime_map = await self._build_video_to_anime_map()
            enriched_count = 0

            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)

                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get("scheduleTime", "")
                        if scheduled_time:
                            # 豐富 anime_data：從爬蟲映射表中查找 animeSn
                            video_sn = anime.get("videoSn")
                            if video_sn and video_sn in video_to_anime_map:
                                # 複製 anime 避免修改原始對象
                                enriched_anime = anime.copy()
                                enriched_anime["animeSn"] = video_to_anime_map[video_sn]
                                enriched_count += 1
                                logger.debug(f"🔗 [refresh_weekly_schedule] 找到映射: videoSn={video_sn} -> animeSn={video_to_anime_map[video_sn]}")
                            else:
                                enriched_anime = anime
                                if video_sn:
                                    logger.debug(f"⚠️ [refresh_weekly_schedule] 未找到 animeSn 映射: videoSn={video_sn}")

                            schedule_data.append(
                                {
                                    "day_of_week": day_of_week,
                                    "scheduled_time": scheduled_time,
                                    "anime_data": enriched_anime,
                                }
                            )

            logger.info(
                f"📊 [refresh_weekly_schedule] 爬蟲映射表大小: {len(video_to_anime_map)}, 成功豐富: {enriched_count}/{len(schedule_data)}"
            )

            # 全量覆蓋：先刪除該 week_start_date 的舊資料，再插入新資料
            # save_weekly_schedule 內部已做 UPSERT (保留 pushed=1) + pre-dedup
            if schedule_data:
                success = self.db.save_weekly_schedule(week_start_str, schedule_data)
                if success:
                    logger.info(
                        f"✅ [refresh_weekly_schedule] 週表全量覆蓋完成 ({len(schedule_data)} 個時刻)"
                    )
                else:
                    logger.error(
                        f"❌ [refresh_weekly_schedule] 週表全量覆蓋失敗 ({len(schedule_data)} 個時刻)"
                    )

            # 清理孤兒記錄：週表刷新後，清理不在週表中的 anime_messages、anime_notified
            if hasattr(self.db, "clean_orphaned_records"):
                orphan_stats = self.db.clean_orphaned_records(week_start_str)
                if (
                    orphan_stats.get("messages", 0) > 0
                    or orphan_stats.get("notified", 0) > 0
                ):
                    logger.info(
                        f"🧹 [refresh_weekly_schedule] 清理孤兒記錄: messages={orphan_stats.get('messages')}, notified={orphan_stats.get('notified')}"
                    )

            # 清理舊週記錄，只保留本週（週一則保留上週）（2026-07-28 新增）
            if hasattr(self.db, "cleanup_old_weeks"):
                deleted = self.db.cleanup_old_weeks()
                if deleted > 0:
                    logger.info(
                        f"🧹 [refresh_weekly_schedule] 清理舊週記錄: {deleted} 筆"
                    )

            # 取得今日時程（含 pushed 狀態）供上層檢查漏推
            today_schedule = self.get_today_schedule()

            # 重新排程推送任務（週表更新後需要重新設定排程）
            if self.anime_tracker and hasattr(self.anime_tracker, '_reschedule_push_jobs'):
                import asyncio
                # 創建任務但不等待完成，避免阻塞
                asyncio.create_task(self.anime_tracker._reschedule_push_jobs())

            return {
                "success": True,
                "week_start_date": week_start_str,
                "today_schedule": today_schedule,
                "total_count": len(schedule_data),
            }

        except Exception as e:
            error_msg = str(e)
            if not error_msg:
                error_msg = f"{type(e).__name__} with empty message"
            logger.error(f"❌ [refresh_weekly_schedule] 失敗: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    async def _build_video_to_anime_map(self) -> dict:
        """
        使用 BahamutWebScraper 從首頁爬取完整週表並建立 videoSn -> animeSn 映射表

        Returns:
            dict: {videoSn: animeSn}
        """
        video_to_anime_map = {}

        if BahamutWebScraper is None:
            logger.warning("⚠️ [_build_video_to_anime_map] BahamutWebScraper 不可用，跳過爬蟲映射")
            return video_to_anime_map

        try:
            scraper = BahamutWebScraper()
            logger.info("🕷️ [_build_video_to_anime_map] 開始爬取巴哈動畫瘋首頁週表獲取 animeSn 映射...")

            homepage_schedule = await scraper.fetch_weekly_schedule_from_homepage()

            for entry in homepage_schedule:
                video_sn = entry.get('video_sn')
                anime_sn = entry.get('anime_sn')
                if video_sn and anime_sn:
                    video_to_anime_map[video_sn] = anime_sn
                    logger.debug(f"🔗 [_build_video_to_anime_map] 映射: videoSn={video_sn} -> animeSn={anime_sn} ({entry.get('title', '未知標題')})")

            logger.info(f"✅ [_build_video_to_anime_map] 爬蟲完成，從首頁週表獲得 {len(video_to_anime_map)} 個映射關係")

        except Exception as e:
            logger.error(f"❌ [_build_video_to_anime_map] 爬蟲失敗: {e}", exc_info=True)

        return video_to_anime_map

    def get_today_schedule(self, week_start_date: str | None = None) -> list:
        """獲取今天的時程表（從週表中） - 委託給 AnimeDatabase

        Args:
            week_start_date: 週起始日期 "YYYY-MM-DD"，若不提供則使用當前週
        """
        return self.db.get_today_schedule(week_start_date)

    def mark_time_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> bool:
        """標記某個時刻已推送過 - 委託給 AnimeDatabase"""
        return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
