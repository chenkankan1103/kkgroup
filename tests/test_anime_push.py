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
from cogs.ui.schedule_tracker import AnimeScheduleTracker


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

    def test_save_weekly_schedule_keeps_same_slot_different_anime(self, db):
        """同一時刻的多部番都必須保留。

        原本 pre-dedup 用 (dayOfWeek, scheduledTime) 當 key，同時刻只留第一筆。
        巴哈首頁週表 53 筆因此只存進 44 筆，被吃掉的 9 部永遠沒有週表列、
        只能一直靠輪詢推（2026-10-22 實測）。表約束本來就是
        UNIQUE(weekStartDate, dayOfWeek, scheduledTime, videoSn)，同時刻多部不衝突。
        """
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
        assert count == 2, "同時刻的不同番都應保留，不可整批丟掉"

    def test_save_weekly_schedule_dedups_exact_duplicate(self, db):
        """完全相同的 (dayOfWeek, scheduledTime, videoSn) 才是真重複，只留一列"""
        week, _ = _now_week_and_day(db)
        entry = {
            "day_of_week": 1,
            "scheduled_time": "21:00",
            "anime_data": {"videoSn": 1},
        }
        db.save_weekly_schedule(week, [entry, dict(entry)])

        conn = db._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM anime_weekly_schedule "
            "WHERE weekStartDate=? AND dayOfWeek=1 AND scheduledTime='21:00'",
            (week,),
        )
        count = c.fetchone()[0]
        conn.close()
        assert count == 1, "完全相同的列只應保留一列"

    def test_upcoming_schedules_expose_anime_sn(self, db):
        """輪詢閘門必須拿得到 animeSn，否則攔不住新集。

        週表列記的 videoSn 是 02:00 抓到的「上一集」，新集上架後 videoSn 就不同，
        只比 videoSn 的閘門會放行 → 輪詢提前把新集推走（實測最多提前 10034 分鐘）。
        """
        week, day = _now_week_and_day(db)
        db.save_weekly_schedule(
            week,
            [
                {
                    "day_of_week": day,
                    "scheduled_time": "23:59",
                    "anime_data": {"videoSn": 111, "animeSn": 42, "title": "某番"},
                }
            ],
        )

        upcoming = db.get_upcoming_schedules()
        assert any(s["animeSn"] == 42 for s in upcoming), (
            "get_upcoming_schedules 必須回傳 animeSn，否則閘門無法比對新集"
        )

    def test_upcoming_schedules_keeps_row_without_video_sn(self, db):
        """只有 animeSn、沒有 videoSn 的列仍算未來排程，不可被略過"""
        week, day = _now_week_and_day(db)
        db.save_weekly_schedule(
            week,
            [
                {
                    "day_of_week": day,
                    "scheduled_time": "23:58",
                    "anime_data": {"animeSn": 77, "title": "無 videoSn 番"},
                }
            ],
        )

        upcoming = db.get_upcoming_schedules()
        assert any(s["animeSn"] == 77 for s in upcoming)


class TestLearnedSlots:
    """換季橋接：輪詢觀察到的官方時刻，連續兩週後升級為排程推送

    巴哈週表在換季初期常還沒收錄新番，那些番只能靠輪詢。輪詢推送時把 index API
    的 week/upTimeHours 記進 anime_learned_slots，同一時刻觀察滿 2 次就補進週表，
    之後改由排程路徑準時推送。
    """

    def test_single_observation_not_promoted(self, db):
        db.record_learned_slot(114191, "3", "23:30", "某番", 51947, "第1集")
        assert db.get_learned_slots(min_observations=2) == []

    def test_two_observations_same_slot_promoted(self, db):
        db.record_learned_slot(114191, "3", "23:30", "某番", 51947, "第1集")
        db.record_learned_slot(114191, "3", "23:30", "某番", 51949, "第2集")

        slots = db.get_learned_slots(min_observations=2)
        assert len(slots) == 1
        slot = slots[0]
        assert slot["animeSn"] == 114191
        assert slot["dayOfWeek"] == 3
        assert slot["scheduledTime"] == "23:30"
        # videoSn/episode 應更新為最新一次觀察
        assert slot["videoSn"] == 51949

    def test_slot_change_resets_count(self, db):
        """時刻變動就整列重置，避免同時補進新舊兩個時刻"""
        db.record_learned_slot(114191, "3", "23:30", "某番", 51947, "")
        db.record_learned_slot(114191, "3", "23:30", "某番", 51949, "")
        assert len(db.get_learned_slots(min_observations=2)) == 1

        # 時刻改了 → 計數歸 1，不再達門檻
        db.record_learned_slot(114191, "4", "22:00", "某番", 51950, "")
        assert db.get_learned_slots(min_observations=2) == []

        # 新時刻再看一次才達門檻，且只有一列（舊時刻已被取代）
        db.record_learned_slot(114191, "4", "22:00", "某番", 51951, "")
        slots = db.get_learned_slots(min_observations=2)
        assert len(slots) == 1
        assert slots[0]["dayOfWeek"] == 4
        assert slots[0]["scheduledTime"] == "22:00"

    def test_rejects_unscheduled_and_bad_values(self, db):
        """week='0' 表示巴哈自己也沒排時刻（如 animeSn 114107），不可學"""
        assert db.record_learned_slot(114107, "0", "23:30", "某番", 51310, "") is False
        assert db.record_learned_slot(0, "3", "23:30", "某番", 1, "") is False
        assert db.record_learned_slot(1, "3", "", "某番", 1, "") is False
        assert db.record_learned_slot(1, "3", "25:99", "某番", 1, "") is False
        assert db.record_learned_slot(1, None, "23:30", "某番", 1, "") is False
        assert db.get_learned_slots(min_observations=1) == []


class TestMergeLearnedSlots:
    """`AnimeScheduleTracker._merge_learned_slots` 把學習結果併進週表資料"""

    @pytest.fixture
    def tracker(self, db):
        t = AnimeScheduleTracker(db_path=":memory:")
        t.db = db
        return t

    def test_merges_learned_slot_into_schedule(self, tracker, db):
        for _ in range(2):
            db.record_learned_slot(114191, "3", "23:30", "某番", 51947, "第1集")

        schedule_data = []
        added = tracker._merge_learned_slots(schedule_data)

        assert added == 1
        assert len(schedule_data) == 1
        item = schedule_data[0]
        assert item["day_of_week"] == 3
        assert item["scheduled_time"] == "23:30"
        assert item["anime_data"]["animeSn"] == 114191
        assert item["anime_data"]["videoSn"] == 51947
        assert item["anime_data"]["scheduleTime"] == "23:30"

    def test_official_entry_wins(self, tracker, db):
        """官方週表已收錄的番不補，避免蓋掉官方時刻"""
        for _ in range(2):
            db.record_learned_slot(114191, "3", "23:30", "某番", 51947, "")

        schedule_data = [
            {
                "day_of_week": 3,
                "scheduled_time": "22:00",
                "anime_data": {"animeSn": 114191, "videoSn": 51947},
            }
        ]
        added = tracker._merge_learned_slots(schedule_data)

        assert added == 0
        assert len(schedule_data) == 1
        assert schedule_data[0]["scheduled_time"] == "22:00"

    def test_below_threshold_not_merged(self, tracker, db):
        db.record_learned_slot(114191, "3", "23:30", "某番", 51947, "")
        assert tracker._merge_learned_slots([]) == 0

    def test_missing_db_method_is_tolerated(self, tracker):
        """db 沒有 get_learned_slots（舊版/替代實作）時不應爆"""
        tracker.db = object()
        assert tracker._merge_learned_slots([]) == 0


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
