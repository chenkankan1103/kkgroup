import asyncio
import sys
sys.path.insert(0, r'C:\Users\88697\Desktop\kkgroup')

async def test_debug():
    import discord.ext.test as dpytest
    from discord.ext import commands
    import discord
    from unittest.mock import AsyncMock, MagicMock, patch
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    import sqlite3
    import tempfile
    from pathlib import Path
    import json

    TW_TZ = ZoneInfo('Asia/Taipei')

    # Create temp DB
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / 'test.db'

    # Setup bot
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix='!', intents=intents)
    loop = asyncio.get_event_loop()
    bot._loop = loop
    bot.loop = loop

    dpytest.configure(bot)
    bot._ready = asyncio.Event()
    bot._ready.set()

    guild = dpytest.get_config().guilds[0]
    channel = dpytest.get_config().channels[0]
    channel_id = channel.id

    # Patch ANIME_CHANNEL_ID
    import cogs.ui.push_core as push_core_mod
    push_core_mod.ANIME_CHANNEL_ID = channel_id

    import cogs.ui.anime_tracker as anime_tracker_mod
    anime_tracker_mod.ANIME_DB_PATH = db_path

    # Create frozen time manually
    from datetime import datetime as real_datetime
    from unittest.mock import patch as mock_patch

    class TimeFreezer:
        def __init__(self):
            self.patches = []
            self.frozen_dt = None

        def freeze(self, dt):
            self.frozen_dt = dt if dt.tzinfo else dt.replace(tzinfo=TW_TZ)
            class FrozenDatetime(real_datetime):
                @classmethod
                def now(cls, tz=None):
                    return TimeFreezer.frozen_dt
            TimeFreezer.frozen_dt = self.frozen_dt
            p1 = mock_patch('datetime.datetime', FrozenDatetime)
            p1.start()
            self.patches.append(p1)
            import cogs.ui.push_core as pc
            p2 = mock_patch.object(pc, 'datetime', FrozenDatetime)
            p2.start()
            self.patches.append(p2)
            import cogs.ui.anime_tracker as at
            p3 = mock_patch.object(at, 'datetime', FrozenDatetime)
            p3.start()
            self.patches.append(p3)
            import cogs.ui.schedule_tracker as st
            p4 = mock_patch.object(st, 'datetime', FrozenDatetime)
            p4.start()
            self.patches.append(p4)

        def unfreeze(self):
            for p in self.patches:
                p.stop()
            self.patches.clear()

    freezer = TimeFreezer()
    default_time = datetime(2026, 8, 10, 0, 0, 0, tzinfo=TW_TZ)
    freezer.freeze(default_time)

    # Load cog
    from cogs.ui.anime_tracker import AnimeTracker

    async def patched_cog_load(self):
        try:
            await self._restore_old_message_views()
        except Exception:
            pass
        try:
            await self._init_weekly_schedule_if_empty()
        except Exception:
            pass
        try:
            await self._catchup_missed_pushes()
        except Exception:
            pass

    with patch.object(AnimeTracker, 'cog_load', patched_cog_load):
        await bot.add_cog(AnimeTracker(bot))
        await asyncio.sleep(0.1)

    cog = bot.get_cog('AnimeTracker')

    # Now freeze to test time
    target_time = datetime(2026, 8, 10, 0, 30, 0, tzinfo=TW_TZ)
    freezer.freeze(target_time)

    now = freezer.frozen_dt
    print(f'Test frozen time: {now}')

    # Check schedule after cog_load
    today_schedule = cog.db.get_today_schedule()
    print(f'Schedule after cog_load: {len(today_schedule)} items')
    for item in today_schedule:
        print(f'  {item["scheduled_time"]} - {item["anime_data"].get("title")} videoSn={item["anime_data"].get("videoSn")} pushed={item["pushed"]}')

    # Manually set pushed=0 for 00:00
    from cogs.ui.anime_tracker import ANIME_WEEKLY_SCHEDULE_TABLE
    week_start = now - timedelta(days=now.weekday())
    week_start_str = week_start.strftime('%Y-%m-%d')
    day_of_week = (now.weekday() + 1) % 7 or 7

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
        SET pushed=0
        WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?
    ''', (week_start_str, day_of_week, '00:00'))
    conn.commit()
    conn.close()
    print('Set pushed=0 for 00:00')

    # Set mock API data
    from tests.conftest import MockBahamutAPI
    mock_api = MockBahamutAPI()
    mock_api.new_anime_data = [
        {'videoSn': 1001, 'animeSn': 5001, 'title': 'Catchup Anime', 'volume': '第 1 話', 'cover': 'https://example.com/ca.jpg', 'upTime': now.strftime('%m/%d'), 'popular': 5000},
    ]

    # Patch the API
    import cogs.ui.push_core as pc

    class MockResponse:
        def __init__(self, data, status=200):
            self._data = data
            self.status = status
        async def json(self):
            return self._data
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class MockSession:
        def __init__(self, mock_api):
            self.mock_api = mock_api
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def get(self, url, *args, **kwargs):
            print(f'  >>> API CALL: {url}')
            if 'video.php' in url:
                import re
                match = re.search(r'sn=(\d+)', url)
                video_sn = int(match.group(1)) if match else 1001
                return MockResponse(self.mock_api.get_video_details(video_sn))
            else:
                return MockResponse({
                    'data': {
                        'newAnimeSchedule': self.mock_api.get_schedule()['data']['newAnimeSchedule'],
                        'newAnime': self.mock_api.get_new_anime()['data']['newAnime'],
                        'popular': []
                    }
                })

    class MockClientSession:
        def __init__(self, *args, **kwargs):
            self._session = MockSession(mock_api)
        async def __aenter__(self):
            return self._session
        async def __aexit__(self, *args):
            pass

    with patch('aiohttp.ClientSession', MockClientSession):
        print('\n=== Calling _catchup_missed_pushes ===')
        await cog._catchup_missed_pushes()

    # Check messages
    messages = []
    while not dpytest.sent_queue.empty():
        try:
            msg = dpytest.sent_queue.get_nowait()
            if hasattr(msg, 'channel') and msg.channel.id == channel_id:
                messages.append(msg)
        except:
            break
    print(f'Messages sent: {len(messages)}')
    for msg in messages:
        print(f'  Embed title: {msg.embeds[0].title if msg.embeds else "No embed"}')

    # Check pushed status
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f'''
        SELECT pushed FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
        WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?
    ''', (week_start_str, day_of_week, '00:00'))
    row = cursor.fetchone()
    conn.close()
    print(f'Pushed status after catchup: {row}')

    freezer.unfreeze()
    await bot.remove_cog('AnimeTracker')
    dpytest.empty_queue()
    try:
        dpytest.unconfigure()
    except:
        pass

asyncio.run(test_debug())