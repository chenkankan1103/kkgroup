"""
pytest 配置與 dpytest 設定
提供：模擬 Discord 環境、資料庫隔離、API Mock、測試後自動清理
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

# ==================== 環境變數 Mock (必須在匯入 bots.bot 之前) ====================
# bots.bot 模組在匯入時會檢查 DISCORD_BOT_TOKEN，測試時需提供假值
# uibot 使用 UI_DISCORD_ 前綴
os.environ.setdefault("DISCORD_BOT_TOKEN", "test_token_fake")
os.environ.setdefault("DISCORD_GUILD_ID", "123456789012345678")
os.environ.setdefault("DISCORD_SYS_CHANNEL_ID", "987654321098765432")
os.environ.setdefault("UI_DISCORD_BOT_TOKEN", "test_token_fake")
os.environ.setdefault("UI_DISCORD_GUILD_ID", "123456789012345678")
os.environ.setdefault("UI_DISCORD_SYS_CHANNEL_ID", "987654321098765432")

import discord.ext.test as dpytest
import pytest
import pytest_asyncio


# ==================== Pytest 標記 ====================
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: 需外部資源 (DB、API、Discord) 的整合測試"
    )
    config.addinivalue_line("markers", "unit: 純單元測試，無外部依賴，執行快速")


TW_TZ = ZoneInfo("Asia/Taipei")


def find_unpushed_items(
    today_schedule: list, now: datetime = None, future_only: bool = False
) -> list:
    """
    從今日時程表中找出未推送的項目 (測試版，同 push_core.py)

    Args:
        today_schedule: 今日時程表列表 (含 pushed, scheduled_time 欄位)
        now: 當前時間，預設為當前台灣時間
        future_only: True=只回傳時間尚未到達的項目, False=回傳所有已過/當前時間的未推送項目

    Returns:
        list: 符合條件的未推送項目列表，按時間排序
    """
    if now is None:
        now = datetime.now(TW_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TW_TZ)

    matching = []
    for item in today_schedule:
        if item.get("pushed"):
            continue
        scheduled = item.get("scheduled_time", "")
        try:
            sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
            )
            diff = (now - sched_dt).total_seconds()
            if future_only:
                if diff < 0:  # 時間尚未到達
                    matching.append(item)
            else:
                if diff >= 0:  # 已過或當前時刻
                    matching.append(item)
        except Exception:
            pass

    return sorted(matching, key=lambda x: x.get("scheduled_time", ""))


# 確保專案根目錄在路徑中
sys.path.insert(0, str(Path(__file__).parent.parent))


# ==================== 全域事件循環 ====================


@pytest.fixture(scope="session")
def event_loop():
    """建立 session 級事件循環供 dpytest 使用"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ==================== 測試資料庫隔離 ====================


@pytest.fixture(scope="function")
def temp_db_path(tmp_path):
    """
    每個測試函數獨立的臨時資料庫檔案
    測試結束自動刪除
    """
    db_file = tmp_path / "test_user_data.db"
    yield str(db_file)
    # 清理由 tmp_path 自動處理


@pytest.fixture(scope="function")
def isolated_db(temp_db_path):
    """
    使用臨時資料庫的 AnimeDatabase 實例
    直接操作 SQLite，不經過 bot
    """
    from cogs.ui.push_core import AnimeDatabase, AnimeDBImpl

    db_impl = AnimeDBImpl(temp_db_path)
    db = AnimeDatabase(db_impl)
    yield db
    # 測試結束，連接會自動關閉


# ==================== dpytest Discord 環境 ====================


@pytest_asyncio.fixture(scope="function")
async def dpytest_setup(event_loop, temp_db_path, frozen_time):
    """
    基礎 dpytest Discord 環境配置
    - 建立模擬 guild、channel、member
    - 測試後清理 dpytest 狀態
    - 不載入特定 cog，不打補釘 API
    """
    import discord
    from discord.ext import commands
    from datetime import datetime
    from zoneinfo import ZoneInfo

    TW_TZ = ZoneInfo("Asia/Taipei")

    # 預設凍結時間：週一 2026-08-10 12:00:00
    default_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=TW_TZ)
    frozen_time.freeze(default_time)

    # 建立新的 Bot 實例給 dpytest 使用
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot._loop = event_loop
    bot.loop = event_loop

    # 配置 dpytest
    dpytest.configure(bot)

    # 手動設定 bot ready 狀態
    bot._ready = asyncio.Event()
    bot._ready.set()

    # 建立測試用 guild、channel
    guild = dpytest.get_config().guilds[0]
    channel = dpytest.get_config().channels[0]

    ctx = {
        "bot": bot,
        "guild": guild,
        "channel": channel,
        "channel_id": channel.id,
        "temp_db_path": temp_db_path,
    }

    yield ctx

    # ===== 測試後清理 =====
    # 清空 dpytest 內部隊列
    await dpytest.empty_queue()

    # 重置 dpytest 配置
    try:
        dpytest.unconfigure()
    except Exception:
        pass

    # 解凍時間
    frozen_time.unfreeze()


@pytest_asyncio.fixture(scope="function")
async def anime_dpytest_setup(event_loop, temp_db_path, frozen_time, patch_bahamut_api):
    """
    完整的動畫測試環境
    - 包含 dpytest 基礎環境
    - 載入 AnimeTracker cog
    - 打補釘 Bahamut API
    - 設定 ANIME_CHANNEL_ID 和資料庫路徑
    """
    import discord
    from discord.ext import commands
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from pathlib import Path

    TW_TZ = ZoneInfo("Asia/Taipei")

    # 預設凍結時間：週一 2026-08-10 12:00:00 (避開 00:00 觸發 catchup)
    default_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=TW_TZ)
    frozen_time.freeze(default_time)

    # 建立新的 Bot 實例給 dpytest 使用
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot._loop = event_loop
    bot.loop = event_loop

    # 配置 dpytest
    dpytest.configure(bot)

    # 手動設定 bot ready 狀態
    bot._ready = asyncio.Event()
    bot._ready.set()

    from cogs.ui.anime_tracker import AnimeTracker

    # 建立測試用 guild、channel
    guild = dpytest.get_config().guilds[0]
    channel = dpytest.get_config().channels[0]

    # 將頻道 ID 設為 ANIME_CHANNEL_ID 以便測試
    import cogs.ui.push_core as push_core_mod

    original_channel_id = push_core_mod.ANIME_CHANNEL_ID
    push_core_mod.ANIME_CHANNEL_ID = channel.id

    # 修改 bot 的資料庫路徑指向臨時資料庫
    import cogs.ui.anime_tracker as anime_tracker_mod

    original_db_path = anime_tracker_mod.ANIME_DB_PATH
    anime_tracker_mod.ANIME_DB_PATH = Path(temp_db_path)

    # 取得 mock 實例
    mock_bahamut_api = patch_bahamut_api

    # Patch background task startup to avoid loop issues in test
    async def patched_cog_load(self):
        """Patched cog_load that skips background tasks, init, and catchup"""
        try:
            await self._restore_old_message_views()
        except Exception:
            pass

        # SKIP init and catchup during fixture setup - tests will initialize at their own frozen time

        # Skip starting background tasks in tests

    with patch.object(AnimeTracker, "cog_load", patched_cog_load):
        # 載入 cog
        await bot.add_cog(AnimeTracker(bot))

        # 等待 cog_load 完成
        await asyncio.sleep(0.1)

        # 提供測試上下文
        ctx = {
            "bot": bot,
            "guild": guild,
            "channel": channel,
            "channel_id": channel.id,
            "temp_db_path": temp_db_path,
            "mock_bahamut_api": mock_bahamut_api,
        }

        yield ctx

    # ===== 測試後清理 =====
    # 1. 卸載 cog
    await bot.remove_cog("AnimeTracker")

    # 2. 還原全域配置
    push_core_mod.ANIME_CHANNEL_ID = original_channel_id
    anime_tracker_mod.ANIME_DB_PATH = original_db_path

    # 3. 清空 dpytest 內部隊列 (async)
    await dpytest.empty_queue()

    # 4. 重置 dpytest 配置 (同步函數，不需要 await)
    try:
        dpytest.unconfigure()
    except Exception:
        pass

    # 5. 解凍時間
    frozen_time.unfreeze()


class MockBahamutAPI:
    """模擬 Bahamut 動畫瘋 API 回應"""

    def __init__(self):
        self.schedule_data = self._default_schedule()
        self.new_anime_data = None  # 延遲初始化，改由 get_new_anime 動態生成 upTime
        self.video_details = {}
        self.call_count = {"schedule": 0, "new_anime": 0, "details": 0}

    def _default_schedule(self):
        """預設週表資料（模擬 newAnimeSchedule API）"""
        # 週一=1 ... 週日=7
        return {
            "1": [  # 週一
                {
                    "title": "Spy×Family",
                    "scheduleTime": "00:00",
                    "videoSn": 1001,
                    "animeSn": 5001,
                    "cover": "https://example.com/spy.jpg",
                },
                {
                    "title": "Jujutsu Kaisen",
                    "scheduleTime": "01:00",
                    "videoSn": 1002,
                    "animeSn": 5002,
                    "cover": "https://example.com/jjk.jpg",
                },
            ],
            "2": [  # 週二
                {
                    "title": "Frieren",
                    "scheduleTime": "22:00",
                    "videoSn": 1003,
                    "animeSn": 5003,
                    "cover": "https://example.com/frieren.jpg",
                },
            ],
            "3": [],  # 週三
            "4": [  # 週四
                {
                    "title": "One Piece",
                    "scheduleTime": "21:00",
                    "videoSn": 1004,
                    "animeSn": 5004,
                    "cover": "https://example.com/op.jpg",
                },
            ],
            "5": [],  # 週五
            "6": [  # 週六
                {
                    "title": "Attack on Titan",
                    "scheduleTime": "23:30",
                    "videoSn": 1005,
                    "animeSn": 5005,
                    "cover": "https://example.com/aot.jpg",
                },
            ],
            "7": [  # 週日
                {
                    "title": "Sunday Early Anime",
                    "scheduleTime": "00:00",
                    "videoSn": 1007,
                    "animeSn": 5007,
                    "cover": "https://example.com/sun_early.jpg",
                },
            ],
        }

    def _build_new_anime_data(self):
        """動態構建新番資料，使用當前系統時間（會被 frozen_time 影響）"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today_str = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%m/%d")

        return [
            {
                "videoSn": 1001,
                "animeSn": 5001,
                "title": "Spy×Family",
                "volume": "第 1 話",
                "cover": "https://example.com/spy.jpg",
                "upTime": today_str,
                "popular": 12345,
            },
            {
                "videoSn": 1002,
                "animeSn": 5002,
                "title": "Jujutsu Kaisen",
                "volume": "第 2 話",
                "cover": "https://example.com/jjk.jpg",
                "upTime": today_str,
                "popular": 9876,
            },
            {
                "videoSn": 1003,
                "animeSn": 5003,
                "title": "Frieren",
                "volume": "第 3 話",
                "cover": "https://example.com/frieren.jpg",
                "upTime": today_str,
                "popular": 15000,
            },
        ]

    def get_schedule(self):
        """模擬 newAnimeSchedule API"""
        self.call_count["schedule"] += 1
        return {"data": {"newAnimeSchedule": self.schedule_data}}

    def get_new_anime(self):
        """模擬 newAnime.date API - 每次呼叫動態生成 upTime 以符合凍結時間"""
        self.call_count["new_anime"] += 1
        # 如果測試有手動設定 new_anime_data，優先使用；否則動態生成
        data = (
            self.new_anime_data
            if self.new_anime_data is not None
            else self._build_new_anime_data()
        )
        return {"data": {"newAnime": {"date": data, "popular": []}}}

    def get_video_details(self, video_sn):
        """模擬 video.php API"""
        self.call_count["details"] += 1
        return self.video_details.get(
            video_sn,
            {
                "data": {
                    "anime": {
                        "content": f"這是 videoSn={video_sn} 的動画簡介",
                        "score": 4.5,
                        "tags": ["奇幻", "冒陷"],
                    }
                }
            },
        )


@pytest.fixture
def mock_bahamut_api():
    """提供可自訂的 Bahamut API Mock"""
    return MockBahamutAPI()


@pytest.fixture
def patch_bahamut_api(mock_bahamut_api):
    """
    打補釘所有 Bahamut API 呼叫
    適用於：AnimePushCore、AnimeScheduleTracker、AnimeTracker
    """
    from unittest.mock import patch

    class MockResponse:
        """正確實現 async context manager 的 Mock Response"""

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
        """模擬 ClientSession，其 get 返回 async context manager"""

        def __init__(self, mock_api):
            self.mock_api = mock_api
            self.call_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, url, *args, **kwargs):
            self.call_count += 1
            # 處理不同的 API endpoint
            if "video.php" in url:
                # 動畫詳細資訊 endpoint: /video.php?sn={video_sn}
                import re

                match = re.search(r"sn=(\d+)", url)
                video_sn = int(match.group(1)) if match else 1001
                return MockResponse(self.mock_api.get_video_details(video_sn))
            else:
                # 主 endpoint (/index.php): 返回 schedule + newAnime
                return MockResponse(
                    {
                        "data": {
                            "newAnimeSchedule": self.mock_api.get_schedule()["data"][
                                "newAnimeSchedule"
                            ],
                            "newAnime": self.mock_api.get_new_anime()["data"][
                                "newAnime"
                            ],
                            "popular": [],
                        }
                    }
                )

    # Patch aiohttp.ClientSession to return a MockSession instance directly
    class MockClientSession:
        def __init__(self, *args, **kwargs):
            self._session = MockSession(mock_bahamut_api)

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *args):
            pass

    with patch("aiohttp.ClientSession", MockClientSession):
        yield mock_bahamut_api


# ==================== 時間控制 ====================


@pytest.fixture
def frozen_time():
    """
    凍結時間用於測試特定時刻的邏輯
    使用 unittest.mock.patch 正確模擬 datetime.datetime.now
    """
    from datetime import datetime as real_datetime
    from zoneinfo import ZoneInfo

    class TimeFreezer:
        def __init__(self):
            self.patches = []
            self.frozen_dt = None

        def freeze(self, dt: real_datetime):
            """凍結到指定時間"""
            # 先清理舊的 patch（支援重複呼叫 freeze）
            self.unfreeze()

            frozen_dt = dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))

            # 建立一個模擬 datetime 類別，其 now classmethod 回傳固定時間
            class FrozenDatetime(real_datetime):
                @classmethod
                def now(cls, tz=None):
                    return self.frozen_dt

            # 將傳入的真實 datetime 轉換為 FrozenDatetime 實例
            # 這樣 now() 返回的就是 FrozenDatetime 實例，能通過 isinstance 檢查
            self.frozen_dt = FrozenDatetime(
                frozen_dt.year,
                frozen_dt.month,
                frozen_dt.day,
                frozen_dt.hour,
                frozen_dt.minute,
                frozen_dt.second,
                frozen_dt.microsecond,
                frozen_dt.tzinfo,
            )
            self._FrozenDatetime = FrozenDatetime

            # Patch datetime.datetime 在 builtins 全域生效
            # 這對於使用 `from datetime import datetime` 的代碼有效
            p1 = patch("datetime.datetime", FrozenDatetime)
            p1.start()
            self.patches.append(p1)

            # 也 patch 各模組的 datetime 參考（雙重保險）
            import cogs.ui.push_core as pc
            import cogs.ui.anime_tracker as at
            import cogs.ui.schedule_tracker as st

            for mod in [pc, at, st]:
                p = patch.object(mod, "datetime", FrozenDatetime)
                p.start()
                self.patches.append(p)

        def unfreeze(self):
            """恢復真實時間"""
            for p in self.patches:
                p.stop()
            self.patches.clear()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.unfreeze()

    freezer = TimeFreezer()
    yield freezer
    freezer.unfreeze()


# ==================== 測試資料建構器 ====================


@pytest.fixture
def sample_schedule_item():
    """單一週表項目建構器"""

    def _build(
        day_of_week: int = 1,
        scheduled_time: str = "00:00",
        video_sn: int = 1001,
        anime_sn: int = 5001,
        title: str = "Test Anime",
        pushed: bool = False,
    ):
        return {
            "day_of_week": day_of_week,
            "scheduled_time": scheduled_time,
            "anime_data": {
                "videoSn": video_sn,
                "animeSn": anime_sn,
                "title": title,
                "volume": "第 1 話",
                "cover": "https://example.com/test.jpg",
                "scheduleTime": scheduled_time,
            },
            "pushed": pushed,
        }

    return _build


@pytest.fixture
def sample_anime_episode():
    """單一新番資料建構器"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    def _build(
        video_sn: int = 1001,
        anime_sn: int = 5001,
        title: str = "Test Anime",
        volume: str = "第 1 話",
        up_time: str = None,
        cover: str = "https://example.com/test.jpg",
    ):
        if up_time is None:
            up_time = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%m/%d")

        return {
            "videoSn": video_sn,
            "animeSn": anime_sn,
            "title": title,
            "volume": volume,
            "cover": cover,
            "upTime": up_time,
            "popular": 10000,
        }

    return _build


# ==================== 斷言輔助 ====================


@pytest.fixture
def assert_push_sent():
    """驗證是否成功推送訊息到頻道"""

    def _assert(channel_id: int, expected_count: int = 1):
        messages = dpytest.get_messages(channel_id)
        assert (
            len(messages) == expected_count
        ), f"預期 {expected_count} 則訊息，實際 {len(messages)}"
        return messages

    return _assert


@pytest.fixture
def assert_db_state(isolated_db):
    """驗證資料庫狀態"""

    def _assert_weekly_schedule(
        week_start: str, day: int, time: str, pushed: bool = None
    ):
        conn = isolated_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pushed FROM anime_weekly_schedule WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?",
            (week_start, day, time),
        )
        row = cursor.fetchone()
        if pushed is not None:
            assert row is not None, "週表記錄不存在"
            assert (
                bool(row[0]) == pushed
            ), f"pushed 狀態不符：預期 {pushed}，實際 {bool(row[0])}"
        return row

    def _assert_notified(video_sn: int, exists: bool = True):
        conn = isolated_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM anime_notified WHERE videoSn=?", (video_sn,))
        row = cursor.fetchone()
        if exists:
            assert row is not None, f"videoSn={video_sn} 應在 anime_notified 中"
        else:
            assert row is None, f"videoSn={video_sn} 不應在 anime_notified 中"

    return type(
        "DBAssert",
        (),
        {
            "weekly_schedule": _assert_weekly_schedule,
            "notified": _assert_notified,
        },
    )()


# ==================== uibot 專用測試環境 (可選) ====================
# 如果需要測試 uibot 專用的 AutoShardedBot 行為，可使用此 fixture


@pytest_asyncio.fixture(autouse=False, scope="function")
async def uibot_dpytest_setup(event_loop, temp_db_path):
    """
    使用 uibot 的 AutoShardedBot 進行測試 (可選)
    注意：AutoShardedBot 在測試環境可能需要額外配置
    大多數情況下使用標準的 dpytest_setup 即可，因為 AnimeTracker 邏輯相同
    """
    # 匯入 uibot
    import bots.uibot as uibot_module

    bot = uibot_module.client  # AutoShardedBot 實例
    from cogs.ui.anime_tracker import AnimeTracker

    # 配置 dpytest (同步函數，不需要 await)
    dpytest.configure(bot)

    # 建立測試用 guild、channel
    guild = dpytest.get_config().guilds[0]
    channel = dpytest.get_config().channels[0]

    # 將頻道 ID 設為 ANIME_CHANNEL_ID 以便測試
    import cogs.ui.push_core as push_core_mod

    original_channel_id = push_core_mod.ANIME_CHANNEL_ID
    push_core_mod.ANIME_CHANNEL_ID = channel.id

    # 修改資料庫路徑
    import cogs.ui.anime_tracker as anime_tracker_mod

    original_db_path = anime_tracker_mod.ANIME_DB_PATH
    anime_tracker_mod.ANIME_DB_PATH = Path(temp_db_path)

    # 載入 cog
    await bot.add_cog(AnimeTracker(bot))

    # 等待 cog_load 完成
    await asyncio.sleep(0.5)

    ctx = {
        "bot": bot,
        "guild": guild,
        "channel": channel,
        "channel_id": channel.id,
        "temp_db_path": temp_db_path,
    }

    yield ctx

    # 測試後清理
    await bot.remove_cog("AnimeTracker")
    push_core_mod.ANIME_CHANNEL_ID = original_channel_id
    anime_tracker_mod.ANIME_DB_PATH = original_db_path
    dpytest.empty_queue()
    try:
        dpytest.unconfigure()
    except Exception:
        pass
