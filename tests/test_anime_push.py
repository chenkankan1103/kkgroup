# -*- coding: utf-8 -*-
"""動畫推送系統測試 —— 對齊現行輪詢架構。

歷史沿革（為何本檔與舊版完全不同）：
舊版測試 11 個案例全部打已移除的內部：
  - `AnimeTracker.scheduler` / `_reschedule_push_jobs`（APScheduler 已整個移除）
  - `AnimeTracker._push_anime_task`（逐任務推送已改為每分鐘輪詢）
  - `tracker.db.db`（`self.db` 現在直接就是 `AnimePushDB`，無 wrapper）
  - `tracker.push_core`（已更名 `polling_core`）
現行架構：`AnimeTracker.push_check_loop`（tasks.loop 每分鐘）→
`SimpleAnimePushCore._check_and_push`，排程閘門為 `anime_weekly_schedule.pushed`
與 `anime_notified` 兩道防重複。
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from discord.ext import tasks

from cogs.ui.anime_tracker import AnimeTracker
from cogs.ui.push_core_simple import TW_TZ, AnimePushDB, SimpleAnimePushCore


@pytest.fixture
def db(temp_db_path):
    """生產同款資料庫（AnimeTracker.set_dependencies 傳入的就是 AnimePushDB）"""
    return AnimePushDB(temp_db_path)


def _now_week_and_day(db: AnimePushDB) -> tuple[str, int]:
    """回傳「現在」所屬的週起始日與資料庫用星期編號（1=週一 … 7=週日）"""
    now = datetime.now(TW_TZ)
    return db._get_week_start_date(now), now.weekday() + 1


def _pushed_flag(db: AnimePushDB, week: str, day: int, time_str: str) -> int:
    conn = db._get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT pushed FROM anime_weekly_schedule "
        "WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?",
        (week, day, time_str),
    )
    row = c.fetchone()
    conn.close()
    assert row is not None, "排程列應存在"
    return row[0]


class TestNotifiedGate:
    """`anime_notified` 防重複閘門 —— 靜默重複推送的根因所在"""

    def test_is_notified_transitions(self, db):
        assert db.is_notified(555) is False
        assert db.add_notified(video_sn=555, anime_sn=1, title="測試番") is True
        assert db.is_notified(555) is True

    def test_get_notified_video_sns_and_info(self, db):
        db.add_notified(video_sn=777, anime_sn=42, title="某番")
        assert 777 in db.get_notified_video_sns()
        info = db.get_notified_info(777)
        assert info is not None and info[0] == 42

    def test_get_notified_info_missing_returns_none(self, db):
        assert db.get_notified_info(999999) is None


class TestWeeklyScheduleGate:
    """`anime_weekly_schedule.pushed` 排程閘門"""

    def test_today_schedule_only_returns_unpushed(self, db):
        week, day = _now_week_and_day(db)
        db.save_weekly_schedule(
            week,
            [
                {
                    "day_of_week": day,
                    "scheduled_time": "23:59",
                    "anime_data": {"videoSn": 777, "title": "今日番"},
                }
            ],
        )

        schedule = db.get_today_schedule()
        assert any(s["videoSn"] == 777 for s in schedule)
        assert all(s["pushed"] is False for s in schedule)

    def test_mark_time_pushed_removes_from_today_schedule(self, db):
        week, day = _now_week_and_day(db)
        db.save_weekly_schedule(
            week,
            [
                {
                    "day_of_week": day,
                    "scheduled_time": "23:59",
                    "anime_data": {"videoSn": 888, "title": "今日番"},
                }
            ],
        )

        assert db.mark_time_pushed(day, "23:59", 888) is True
        assert _pushed_flag(db, week, day, "23:59") == 1
        assert not any(s["videoSn"] == 888 for s in db.get_today_schedule())

    def test_save_weekly_schedule_preserves_pushed_flag(self, db):
        """週表重刷（每日 02:00）後 pushed=1 必須保留，否則同一集會被重複推送"""
        week, day = _now_week_and_day(db)
        entry = {
            "day_of_week": day,
            "scheduled_time": "23:58",
            "anime_data": {"videoSn": 111, "title": "A"},
        }
        db.save_weekly_schedule(week, [entry])
        assert db.mark_time_pushed(day, "23:58", 111) is True

        # 模擬每日 02:00 的週表全量覆蓋
        db.save_weekly_schedule(week, [entry])

        assert _pushed_flag(db, week, day, "23:58") == 1

    def test_save_weekly_schedule_dedups_same_slot(self, db):
        week, _ = _now_week_and_day(db)
        db.save_weekly_schedule(
            week,
            [
                {
                    "day_of_week": 1,
                    "scheduled_time": "21:00",
                    "anime_data": {"videoSn": 1},
                },
                {
                    "day_of_week": 1,
                    "scheduled_time": "21:00",
                    "anime_data": {"videoSn": 2},
                },
            ],
        )

        conn = db._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM anime_weekly_schedule "
            "WHERE weekStartDate=? AND dayOfWeek=1 AND scheduledTime='21:00'",
            (week,),
        )
        count = c.fetchone()[0]
        conn.close()
        assert count == 1, "同一 (dayOfWeek, scheduledTime) 只應保留一列"


class TestPushArchitecture:
    """推送循環架構的迴歸守門"""

    def test_push_check_loop_is_minute_polling(self):
        """推送必須是 tasks.loop 每分鐘輪詢。

        2026-09 曾用 asyncio.create_task 建立智能睡眠循環，task 的例外被困在
        無人讀取的 task 物件中（self._task 強引用阻擋 GC），「Task exception
        was never retrieved」永不觸發 → 推送循環靜默死亡 44 小時、零日誌零推送。
        tasks.loop 每圈接例外並自癒，故此設計不可回退。
        """
        loop = AnimeTracker.push_check_loop
        assert isinstance(loop, tasks.Loop), "推送循環必須是 tasks.loop"
        assert loop.minutes == 1

        # APScheduler 與逐任務推送皆已移除，不得復辟
        assert not hasattr(AnimeTracker, "scheduler")
        assert not hasattr(AnimeTracker, "_reschedule_push_jobs")
        assert not hasattr(AnimeTracker, "_push_anime_task")

    def test_simple_push_core_uses_injected_db(self, db):
        """SimpleAnimePushCore 必須共用外部注入的 DB 連線，不自建第二個"""
        core = SimpleAnimePushCore(db)
        assert core.db is db
        assert core._running is False

        bot = MagicMock()
        core.set_bot(bot)
        assert core.bot is bot


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
