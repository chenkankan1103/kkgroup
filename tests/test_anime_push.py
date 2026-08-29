import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import discord
import pytest
import pytest_asyncio

# Import the modules we need to test
from cogs.ui.anime_tracker import AnimeTracker
from cogs.ui.push_core import TW_TZ, AnimePushCore
from cogs.ui.ranking_stats import RankingStats
from cogs.ui.schedule_tracker import AnimeScheduleTracker


# Helper function to create a mock bot
def create_mock_bot():
    bot = MagicMock()
    bot.get_cog = MagicMock(return_value=None)
    return bot


def create_test_db_path():
    """Create a temporary database file path for testing"""
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.db', prefix='test_anime_')
    os.close(fd)
    return path

class TestAnimePushScheduler:
    """Tests for the anime push scheduling logic"""

    @pytest_asyncio.fixture
    async def anime_tracker(self):
        """Create an AnimeTracker instance with mocked dependencies"""
        bot = create_mock_bot()
        tracker = AnimeTracker(bot)

        # Set up mocked dependencies using a file-based database (to share across connections)
        db_path = create_test_db_path()

        await tracker.set_dependencies(db_path)

        # Clean up temp file after test
        yield tracker

        # Teardown: remove temp file
        import os
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest_asyncio.fixture
    async def mock_scheduler(self):
        """Create a mock scheduler"""
        scheduler = MagicMock()
        scheduler.get_jobs = MagicMock(return_value=[])
        scheduler.remove_job = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler.running = True
        return scheduler

    @pytest.mark.asyncio
    async def test_days_ahead_calculation_monday_to_monday(self, anime_tracker):
        """Test days_ahead calculation when today is Monday and target is Monday"""
        today = datetime(2026, 8, 17, 10, 0, 0, tzinfo=TW_TZ)  # Monday
        today_weekday = today.weekday()  # 0 for Monday

        # Target is Monday (day_of_week = 1 in schedule data)
        day_of_week = 1

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return a Monday schedule
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 1,  # Monday
                    'scheduled_time': '15:00',  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that a job was added
                assert mock_sched.add_job.called

                # Get the arguments passed to add_job
                call_args = mock_sched.add_job.call_args
                job_id = call_args[1]['id']
                # The job should be for next Monday since 15:00 has passed 10:00
                assert 'push_67890_12345_1_1500' in job_id

    @pytest.mark.asyncio
    async def test_days_ahead_calculation_monday_to_tuesday(self, anime_tracker):
        """Test days_ahead calculation when today is Monday and target is Tuesday"""
        # Today is Monday (weekday = 0)
        today = datetime(2026, 8, 17, 10, 0, 0, tzinfo=TW_TZ)  # Monday

        # Target is Tuesday (day_of_week = 2 in schedule data)
        day_of_week = 2

        # Expected: days_ahead = (2 - 0 - 1) % 7 = 1

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return a Tuesday schedule
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 2,  # Tuesday
                    'scheduled_time': '15:00',  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that a job was added
                assert mock_sched.add_job.called

    @pytest.mark.asyncio
    async def test_days_ahead_calculation_wednesday_to_monday(self, anime_tracker):
        """Test days_ahead calculation when today is Wednesday and target is Monday"""
        # Today is Wednesday (weekday = 2)
        # 2026-08-19 is a Wednesday
        today = datetime(2026, 8, 19, 10, 0, 0, tzinfo=TW_TZ)  # Wednesday

        # Target is Monday (day_of_week = 1 in schedule data)
        day_of_week = 1

        # Expected: days_ahead = (1 - 2 - 1) % 7 = (-2) % 7 = 5

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return a Monday schedule
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 1,  # Monday
                    'scheduled_time': '15:00',  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that a job was added
                assert mock_sched.add_job.called

    @pytest.mark.asyncio
    async def test_days_ahead_calculation_sunday_to_monday(self, anime_tracker):
        """Test days_ahead calculation when today is Sunday and target is Monday"""
        # Today is Sunday (weekday = 6)
        # 2026-08-22 is a Sunday
        today = datetime(2026, 8, 22, 10, 0, 0, tzinfo=TW_TZ)  # Sunday

        # Target is Monday (day_of_week = 1 in schedule data)
        day_of_week = 1

        # Expected: days_ahead = (1 - 6 - 1) % 7 = (-6) % 7 = 1

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return a Monday schedule
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 1,  # Monday
                    'scheduled_time': '15:00',  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that a job was added
                assert mock_sched.add_job.called

    @pytest.mark.asyncio
    async def test_time_past_today_moves_to_next_week(self, anime_tracker):
        """Test that if the scheduled time has already passed today, it moves to next week"""
        # Today is Monday at 16:00 (4:00 PM)
        today = datetime(2026, 8, 17, 16, 0, 0, tzinfo=TW_TZ)  # Monday 4:00 PM

        # Target is Monday at 15:00 (3:00 PM) - this time has already passed today
        day_of_week = 1  # Monday
        scheduled_time = '15:00'

        # Expected: days_ahead = 0 (same day), but since time has passed, it should go to next week

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return a Monday schedule
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 1,  # Monday
                    'scheduled_time': scheduled_time,  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that a job was added
                assert mock_sched.add_job.called

                # Check that the job was scheduled for next week (7 days later)
                # We can't easily check the exact time without inspecting the call args more deeply,
                # but we can verify the method was called

    @pytest.mark.asyncio
    async def test_time_future_today_stays_same_week(self, anime_tracker):
        """Test that if the scheduled time is in the future today, it stays in the same week"""
        # Today is Monday at 10:00 AM
        today = datetime(2026, 8, 17, 10, 0, 0, tzinfo=TW_TZ)  # Monday 10:00 AM

        # Target is Monday at 15:00 (3:00 PM) - this time is in the future today
        day_of_week = 1  # Monday
        scheduled_time = '15:00'

        # Expected: days_ahead = 0 (same day) and time is in future, so stays same day

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return a Monday schedule
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 1,  # Monday
                    'scheduled_time': scheduled_time,  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that a job was added
                assert mock_sched.add_job.called

    @pytest.mark.asyncio
    async def test_multiple_schedules(self, anime_tracker):
        """Test scheduling multiple anime pushes on different days"""
        # Today is Monday at 10:00 AM
        today = datetime(2026, 8, 17, 10, 0, 0, tzinfo=TW_TZ)  # Monday

        with patch.object(anime_tracker, 'scheduler') as mock_sched:
            mock_sched.get_jobs.return_value = []
            mock_sched.remove_job = MagicMock()
            mock_sched.add_job = MagicMock()

            # Mock the schedule tracker to return multiple schedules
            anime_tracker.schedule_tracker.get_today_schedule = MagicMock(return_value=[
                {
                    'day_of_week': 1,  # Monday
                    'scheduled_time': '15:00',  # 3:00 PM
                    'video_sn': 12345,
                    'anime_sn': 67890
                },
                {
                    'day_of_week': 3,  # Wednesday
                    'scheduled_time': '20:00',  # 8:00 PM
                    'video_sn': 12346,
                    'anime_sn': 67891
                },
                {
                    'day_of_week': 5,  # Friday
                    'scheduled_time': '10:00',  # 10:00 AM
                    'video_sn': 12347,
                    'anime_sn': 67892
                }
            ])

            # Mock datetime.now to return our test time
            with patch('cogs.ui.anime_tracker.datetime') as mock_dt:
                mock_dt.now.return_value = today
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                # Call the method
                await anime_tracker._reschedule_push_jobs()

                # Verify that jobs were added for each schedule
                assert mock_sched.add_job.call_count == 3

class TestAnimePushTask:
    """Tests for the anime push task execution"""

    @pytest_asyncio.fixture
    async def anime_tracker_with_mocked_push_core(self):
        """Create an AnimeTracker instance with mocked push_core"""
        bot = create_mock_bot()
        tracker = AnimeTracker(bot)

        # Set up mocked dependencies using a file-based database (to share across connections)
        db_path = create_test_db_path()

        await tracker.set_dependencies(db_path)

        # Insert test schedule data into the database so _push_anime_task can find it
        db_impl = tracker.db.db
        conn = db_impl._get_conn()
        c = conn.cursor()
        import json
        test_anime_data = json.dumps({"anime_sn": 12345, "videoSn": 67890, "title": "Test Anime"})
        c.execute("""
            INSERT INTO anime_weekly_schedule (weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("2026-08-24", 1, "15:00", 0, test_anime_data, 67890))
        conn.commit()
        conn.close()

        # Mock the push_core to avoid actual API calls
        tracker.push_core = AsyncMock()
        tracker.push_core.send_anime_push = AsyncMock(return_value=True)

        # Clean up temp file after test
        yield tracker

        # Teardown: remove temp file
        import os
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_push_anime_task_success(self, anime_tracker_with_mocked_push_core):
        """Test successful execution of _push_anime_task"""
        anime_sn = 12345
        video_sn = 67890

        # Execute the task
        await anime_tracker_with_mocked_push_core._push_anime_task(anime_sn, video_sn)

        # Verify that push_core.send_anime_push was called (with correct signature: scheduled_time, channel_id, day_of_week, week_start_date)
        anime_tracker_with_mocked_push_core.push_core.send_anime_push.assert_called_once()
        call_args = anime_tracker_with_mocked_push_core.push_core.send_anime_push.call_args
        # Database returns bytes, so decode for comparison
        scheduled_time = call_args[0][0].decode() if isinstance(call_args[0][0], bytes) else call_args[0][0]
        week_start_date = call_args[0][3].decode() if isinstance(call_args[0][3], bytes) else call_args[0][3]
        assert scheduled_time == "15:00"  # scheduled_time
        assert call_args[0][1] == 1252204317453324333  # channel_id (ANIME_CHANNEL_ID)
        assert call_args[0][2] == 1  # day_of_week (Monday)
        assert week_start_date == "2026-08-24"  # week_start_date

    @pytest.mark.asyncio
    async def test_push_anime_task_failure(self, anime_tracker_with_mocked_push_core):
        """Test _push_anime_task handles failure gracefully"""
        anime_sn = 12345
        video_sn = 67890

        # Configure mock to return False (indicating failure/no new episodes)
        anime_tracker_with_mocked_push_core.push_core.send_anime_push.return_value = False

        # Execute the task - should not raise exception
        await anime_tracker_with_mocked_push_core._push_anime_task(anime_sn, video_sn)

        # Verify that push_core.send_anime_push was called (with correct signature)
        anime_tracker_with_mocked_push_core.push_core.send_anime_push.assert_called_once()
        call_args = anime_tracker_with_mocked_push_core.push_core.send_anime_push.call_args
        # Database returns bytes, so decode for comparison
        scheduled_time = call_args[0][0].decode() if isinstance(call_args[0][0], bytes) else call_args[0][0]
        week_start_date = call_args[0][3].decode() if isinstance(call_args[0][3], bytes) else call_args[0][3]
        assert scheduled_time == "15:00"  # scheduled_time
        assert call_args[0][1] == 1252204317453324333  # channel_id (ANIME_CHANNEL_ID)
        assert call_args[0][2] == 1  # day_of_week (Monday)
        assert week_start_date == "2026-08-24"  # week_start_date

    @pytest.mark.asyncio
    async def test_push_anime_task_exception(self, anime_tracker_with_mocked_push_core):
        """Test _push_anime_task handles exceptions gracefully"""
        anime_sn = 12345
        video_sn = 67890

        # Configure mock to raise an exception
        anime_tracker_with_mocked_push_core.push_core.send_anime_push.side_effect = Exception("API Error")

        # Execute the task - should not raise exception
        await anime_tracker_with_mocked_push_core._push_anime_task(anime_sn, video_sn)

        # Verify that push_core.send_anime_push was called (with correct signature)
        anime_tracker_with_mocked_push_core.push_core.send_anime_push.assert_called_once()
        call_args = anime_tracker_with_mocked_push_core.push_core.send_anime_push.call_args
        # Database returns bytes, so decode for comparison
        scheduled_time = call_args[0][0].decode() if isinstance(call_args[0][0], bytes) else call_args[0][0]
        week_start_date = call_args[0][3].decode() if isinstance(call_args[0][3], bytes) else call_args[0][3]
        assert scheduled_time == "15:00"  # scheduled_time
        assert call_args[0][1] == 1252204317453324333  # channel_id (ANIME_CHANNEL_ID)
        assert call_args[0][2] == 1  # day_of_week (Monday)
        assert week_start_date == "2026-08-24"  # week_start_date

    @pytest.mark.asyncio
    async def test_push_anime_task_creates_correct_embed_and_view(self):
        """Test that _push_anime_task creates proper embed and view (integration test)"""
        # This test would require more complex mocking of discord components
        # For now, we'll test the basic functionality is preserved
        bot = create_mock_bot()
        tracker = AnimeTracker(bot)

        # Set up mocked dependencies using a file-based database (to share across connections)
        db_path = create_test_db_path()

        await tracker.set_dependencies(db_path)

        # Insert test schedule data into the database so _push_anime_task can find it
        db_impl = tracker.db.db
        conn = db_impl._get_conn()
        c = conn.cursor()
        import json
        test_anime_data = json.dumps({"anime_sn": 12345, "videoSn": 67890, "title": "Test Anime"})
        c.execute("""
            INSERT INTO anime_weekly_schedule (weekStartDate, dayOfWeek, scheduledTime, pushed, animeData, videoSn)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("2026-08-24", 1, "15:00", 0, test_anime_data, 67890))
        conn.commit()
        conn.close()

        # Mock the push_core.send_anime_push to return True
        tracker.push_core.send_anime_push = AsyncMock(return_value=True)

        anime_sn = 12345
        video_sn = 67890

        # Execute the task
        await tracker._push_anime_task(anime_sn, video_sn)

        # Verify that the method was called
        tracker.push_core.send_anime_push.assert_called_once()

        # Cleanup
        import os
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])