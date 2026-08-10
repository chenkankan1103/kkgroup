import asyncio
import sys
sys.path.insert(0, r'C:\Users\88697\Desktop\kkgroup')
from tests.conftest import MockBahamutAPI
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

TW_TZ = ZoneInfo('Asia/Taipei')
mock_api = MockBahamutAPI()

class TimeFreezer:
    def __init__(self):
        self.patches = []
        self.frozen_dt = None

    def freeze(self, dt):
        frozen_dt = dt if dt.tzinfo else dt.replace(tzinfo=TW_TZ)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return self.frozen_dt

        # 建立 FrozenDatetime 實例
        self.frozen_dt = FrozenDatetime(
            frozen_dt.year, frozen_dt.month, frozen_dt.day,
            frozen_dt.hour, frozen_dt.minute, frozen_dt.second,
            frozen_dt.microsecond, frozen_dt.tzinfo
        )
        self._FrozenDatetime = FrozenDatetime

        p1 = patch('datetime.datetime', FrozenDatetime)
        p1.start()
        self.patches.append(p1)

        import cogs.ui.push_core as pc
        p2 = patch.object(pc, 'datetime', FrozenDatetime)
        p2.start()
        self.patches.append(p2)
        import cogs.ui.anime_tracker as at
        p3 = patch.object(at, 'datetime', FrozenDatetime)
        p3.start()
        self.patches.append(p3)
        import cogs.ui.schedule_tracker as st
        p4 = patch.object(st, 'datetime', FrozenDatetime)
        p4.start()
        self.patches.append(p4)

    def unfreeze(self):
        for p in self.patches:
            p.stop()
        self.patches.clear()

freezer = TimeFreezer()
target_time = datetime(2026, 8, 10, 1, 0, 0, tzinfo=TW_TZ)
freezer.freeze(target_time)

now = freezer.frozen_dt
today_str = now.strftime('%m/%d')
print(f'凍結時間: {now}')
print(f'today_str: {today_str}')

result = mock_api.get_new_anime()
print(f'get_new_anime 回傳: {len(result["data"]["newAnime"]["date"])} 筆')
for ep in result['data']['newAnime']['date']:
    print(f'  videoSn={ep["videoSn"]}, title={ep["title"]}, upTime={ep["upTime"]}')

freezer.unfreeze()