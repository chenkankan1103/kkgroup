# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 週表排程系統

負責週表機制：
- 每週一禮拜晚上 10 點自動從 Bahamut API 下載完整一週時程表
- 將時程表儲存到本地資料庫 (anime_weekly_schedule 表)
- 每小時檢查是否到達預定時刻，若到則進行實時 API 查詢確認新番
- 實時查詢成功後發送通知並標記該時刻已推送
- 大幅減少 API 呼叫頻率：從每天 288 次減少到每週 1 次（節省 99.65%）

此設計解決機器人重啟時可能錯過推送時刻的問題：
- 週表機制保證每個時刻只會被檢查一次
- 錯過的時刻會在機器人重啟時被標記為已推送（不進行實際推送）
- 避免重複嘗試同一時刻的推送
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import asyncio
import aiohttp
from .push_core import AnimeDatabase, ANIME_CHANNEL_ID, ANIME_DB_PATH, TW_TZ, API_ENDPOINT, API_TIMEOUT, ANIME_WEEKLY_SCHEDULE_TABLE

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

    def _extract_view_count_from_episode(self, episode: dict) -> int:
        """從 episode 資料中提取觀看數"""
        views = 0
        # 嘗試多個可能的欄位名
        for field in ['views', 'viewCount', 'playCount', 'popular']:
            if field in episode and isinstance(episode[field], (int, float)):
                views = int(episode[field])
                break
        return views

    def _get_weekday_name(self, weekday_num: int) -> str:
        """將 weekday數字轉換為中文名稱"""
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return weekdays[weekday_num - 1] if 1 <= weekday_num <= 7 else "未知"

    async def _get_anime_schedule(self) -> dict:
        """從 API 獲取日程表 (newAnimeSchedule)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as response:
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

        for day_offset, weekday in [(0, str(weekday_today)), (1, str(weekday_tomorrow))]:
            target_date = (now + timedelta(days=day_offset)).date()
            for anime_info in schedule.get(weekday, []):
                schedule_time = anime_info.get("scheduleTime", "")
                if schedule_time:
                    try:
                        scheduled_time = datetime.strptime(schedule_time, "%H:%M").time()
                        scheduled_dt = datetime.combine(target_date, scheduled_time, tzinfo=TW_TZ)
                        # 改用日期過濾：超過 1 天的時刻才篩除，同日所有時刻都保留
                        # 這防止凌晨時早晨時刻被篩除（例如: 凌公元 03:59 時 01:00 不應被篩除）
                        if scheduled_dt.date() >= (now - timedelta(days=1)).date():
                            check_times.append(scheduled_dt)
                    except ValueError as e:
                        logger.warning(f"⚠️ [_get_expected_check_times] 無法解析時間格式 '{schedule_time}': {e}")
                    except Exception as e:
                        logger.error(f"❌ [_get_expected_check_times] 處理時間時發生未預期錯誤 '{schedule_time}': {e}", exc_info=True)

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
                logger.debug(f"⏭️ [refresh_weekly_schedule] 跳過（非晚上 10 點）")
                return {'success': False, 'skipped': True}

            logger.info("🔄 [refresh_weekly_schedule] 開始拉取本週時程表...")

            # 拉取完整一週的時程表
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [refresh_weekly_schedule] 無法拉取時程表")
                return {'success': False, 'error': 'API 回傳空時程表'}

            # 🔑 修復：正確計算 week_start_date
            # newAnimeSchedule API 回傳的總是「下一個完整週」的時程表（週一~週日）
            # - 週一~週六呼叫：回傳本週的時程表 → week_start = 本週一
            # - 週日呼叫：回傳下週的時程表 → week_start = 下週一
            if now.weekday() == 6:  # 週日
                week_start = now + timedelta(days=1)  # 下週一
            else:
                week_start = now - timedelta(days=now.weekday())  # 本週一
            week_start_str = week_start.strftime("%Y-%m-%d")
            logger.info(f"📅 [refresh_weekly_schedule] 保存週起始日期: {week_start_str} (today={now.strftime('%Y-%m-%d %a')})")

            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)

                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get('scheduleTime', '')
                        if scheduled_time:
                            schedule_data.append({
                                'day_of_week': day_of_week,
                                'scheduled_time': scheduled_time,
                                'anime_data': anime
                            })

            # 全量覆蓋：先刪除該 week_start_date 的舊資料，再插入新資料
            # save_weekly_schedule 內部已做 UPSERT (保留 pushed=1) + pre-dedup
            if schedule_data:
                self.db.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(f"✅ [refresh_weekly_schedule] 週表全量覆蓋完成 ({len(schedule_data)} 個時刻)")

            # 清理孤兒記錄：週表刷新後，清理不在週表中的 anime_messages、anime_notified
            if hasattr(self.db, 'clean_orphaned_records'):
                orphan_stats = self.db.clean_orphaned_records(week_start_str)
                if orphan_stats.get('messages', 0) > 0 or orphan_stats.get('notified', 0) > 0:
                    logger.info(f"🧹 [refresh_weekly_schedule] 清理孤兒記錄: messages={orphan_stats.get('messages')}, notified={orphan_stats.get('notified')}")

            # 清理超過 2 週的舊週表記錄（2026-07-28 新增）
            if hasattr(self.db, 'cleanup_old_weeks'):
                deleted = self.db.cleanup_old_weeks(keep_weeks=2)
                if deleted > 0:
                    logger.info(f"🧹 [refresh_weekly_schedule] 清理舊週記錄: {deleted} 筆")

            # 取得今日時程（含 pushed 狀態）供上層檢查漏推
            today_schedule = self.get_today_schedule()

            return {
                'success': True,
                'week_start_date': week_start_str,
                'today_schedule': today_schedule,
                'total_count': len(schedule_data)
            }

        except Exception as e:
            logger.error(f"❌ [refresh_weekly_schedule] 失敗: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def get_today_schedule(self) -> list:
        """獲取今天的時程表（從週表中） - 委託給 AnimeDatabase"""
        return self.db.get_today_schedule()

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記某個時刻已推送過 - 委託給 AnimeDatabase"""
        return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)

    async def check_scheduled_push(self) -> None:
        """每小時檢查是否有預定推送時刻 - 供週表系統使用"""
        now = datetime.now(TW_TZ)
        current_time = now.strftime("%H:%M")

        try:
            # 獲取今天的時程表
            today_schedule = self.get_today_schedule()

            # 尋找符合現在時刻的項目（尚未推送的）
            # 支援補推機制：所有過去的未推送項目（防止 bot 重啟錯過時刻）
            matching = []
            for item in today_schedule:
                if item['pushed']:
                    continue
                scheduled = item['scheduled_time']
                try:
                    sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                    )
                    diff = (now - sched_dt).total_seconds()
                    # 只處理已過去或當前時刻的節目（diff >= 0）
                    if diff >= 0:
                        matching.append(item)
                except Exception:
                    pass

            if matching:
                # 按時間排序，依序推送所有未推送的時刻（防止一次推送過多訊息）
                matching_sorted = sorted(matching, key=lambda x: x['scheduled_time'])
                logger.info(f"📺 [check_scheduled_push] 發現 {len(matching_sorted)} 個未推送時刻，將依序推送（現在 {current_time}）")
                for item in matching_sorted:
                    # 這裡會調用 AnimeTracker 的 send_anime_push 方法
                    # 但由於這是個別類別，我們需要將實際的推送邏輯交給 AnimeTracker
                    # 這裡只記錄日誌，實際推送在 AnimeTracker 中完成
                    logger.info(f"📺 [check_scheduled_push] 準備推送時刻: {item['scheduled_time']}")
                    # 實際推送邏輯應該在 AnimeTracker 中由排程任務觸發
                    await asyncio.sleep(2)  # 避免短時間內連續發送太多訊息

        except Exception as e:
            logger.error(f"❌ [check_scheduled_push] 失敗: {e}", exc_info=True)

    async def send_anime_push(self, scheduled_time: str, channel_id: int = ANIME_CHANNEL_ID) -> bool:
        """在預定時刻推送動畫通知 - 查詢真實 API 確認已上架集

        此方法應該由 AnimeScheduler 或 AnimeTracker 實際調用，
        此處提供介面說明。

        Args:
            scheduled_time: 預定時刻，格式 "HH:MM"
            channel_id: Discord 頻道 ID

        Returns:
            bool: 是否成功發送通知
        """
        # 這個方法的實際實作應該在 AnimeTracker 類別中
        # 此處僅作為介面說明，實際邏輯參考原 anime_tracker.py 的 send_anime_push 方法
        raise NotImplementedError("此方法應由 AnimeTracker 實際實現")

    async def _check_and_send_anime(self, scheduled_time_str: str, channel) -> bool:
        """檢查新番集並發送通知（用於多窗口檢查）

        此方法的實際實作應該在 AnimeTracker 類別中。
        """
        raise NotImplementedError("此方法應由 AnimeTracker 實際實現")