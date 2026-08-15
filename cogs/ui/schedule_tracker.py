# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 週表排程系統

負責週表機制：
- 每天晚上 22:00 自動從 Bahamut API 下載完整一週時程表
- 將時程表儲存到本地資料庫 (anime_weekly_schedule 表)
- 大幅減少 API 呼叫頻率：從每天 288 次減少到每天 1 次

此設計解決機器人重啟時可能錯過推送時刻的問題：
- 週表機制保證每個時刻只會被檢查一次
- 重啟時由 dispatcher 自動補推已過時段
"""

import logging
from datetime import datetime, timedelta
import asyncio
import aiohttp
from .push_core import TW_TZ, API_ENDPOINT, API_TIMEOUT, get_week_start_date

logger = logging.getLogger(__name__)


class AnimeScheduleTracker:
    """週表排程管理器 - 與 AnimeDatabase 合作實現週表機制"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.db = None
        self._last_fallback_check = None
        self._last_schedule_fallback = None

    def set_dependencies(self, bot, db, push_core):
        """設置依賴"""
        self.bot = bot
        self.db = db
        self.push_core = push_core

    async def _get_anime_schedule(self) -> dict:
        """從 API 獲取日程表 (newAnimeSchedule)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        logger.error(f"❌ API returned status {response.status}")
                        return {}

                    data = await response.json()
                    schedule = data.get("data", {}).get("newAnimeSchedule", {})
                    return schedule
        except Exception as e:
            logger.error(f"❌ Error fetching schedule: {e}")
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

    async def refresh_weekly_schedule(self) -> dict:
        """
        每天晚上 22:00 拉取完整週表並全量覆蓋 - 兼具「填滿行事曆」與「檢查漏推」功能

        流程：
        1. 呼叫 newAnimeSchedule API 取得 7 天時程表
        2. 以「本週一」為 week_start_date 全量覆蓋 anime_weekly_schedule 表
        3. 回傳今日時程供上層檢查 <=22:00 的漏推項目

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
            # 每天 22:00 執行（移除 is_sunday 判斷）
            is_refresh_time = now.hour == 22  # 台灣時間 22:00-22:59

            if not is_refresh_time:
                logger.debug("⏭️ [refresh_weekly_schedule] 跳過（非晚上 10 點）")
                return {"success": False, "skipped": True}

            logger.info("🔄 [refresh_weekly_schedule] 開始拉取本週時程表...")

            # 拉取完整一週的時程表
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [refresh_weekly_schedule] 無法拉取時程表")
                return {"success": False, "error": "API 回傳空時程表"}

            # 🔑 正確計算 week_start_date (api_week=True: 用於儲存從 API 拉取的週表)
            week_start_str = get_week_start_date(now, api_week=True)
            logger.info(
                f"📅 [refresh_weekly_schedule] 保存週起始日期: {week_start_str} (today={now.strftime('%Y-%m-%d %a')})"
            )

            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)

                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get("scheduleTime", "")
                        if scheduled_time:
                            schedule_data.append(
                                {
                                    "day_of_week": day_of_week,
                                    "scheduled_time": scheduled_time,
                                    "anime_data": anime,
                                }
                            )

            # 全量覆蓋：先刪除該 week_start_date 的舊資料，再插入新資料
            # save_weekly_schedule 內部已做 UPSERT (保留 pushed=1) + pre-dedup
            if schedule_data:
                self.db.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(
                    f"✅ [refresh_weekly_schedule] 週表全量覆蓋完成 ({len(schedule_data)} 個時刻)"
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

            return {
                "success": True,
                "week_start_date": week_start_str,
                "today_schedule": today_schedule,
                "total_count": len(schedule_data),
            }

        except Exception as e:
            logger.error(f"❌ [refresh_weekly_schedule] 失敗: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_today_schedule(self) -> list:
        """獲取今天的時程表（從週表中） - 委託給 AnimeDatabase"""
        return self.db.get_today_schedule()

    def mark_time_pushed(
        self, week_start_date: str, day_of_week: int, scheduled_time: str
    ) -> bool:
        """標記某個時刻已推送過 - 委託給 AnimeDatabase"""
        return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)
