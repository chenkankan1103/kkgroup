"""
pytest 配置與 dpytest 設定
提供：模擬 Discord 環境、資料庫隔離、API Mock、測試後自動清理
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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

# 確保專案根目錄在路徑中
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ==================== 全域事件循環 ====================

@pytest.fixture(scope="session")
def event_loop():
    """建立 session 級事件循環供 dpytest 使用"""
    loop = asyncio.new_event_loop()
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
    from cogs.ui.push_core import AnimeDatabase
    db = AnimeDatabase(temp_db_path)
    yield db
    # 測試結束，連接會自動關閉


# ==================== dpytest Discord 環境 ====================

@pytest_asyncio.fixture(autouse=True, scope="function")
async def dpytest_setup(event_loop, temp_db_path):
    """
    每個測試自動配置 dpytest
    - 建立模擬 guild、channel、member
    - 載入 AnimeTracker cog
    - 測試後清理 dpytest 狀態
    """
    # 匯入 bot 與 cog
    import bots.bot as bot_module
    print(f"DEBUG: bots.bot module = {bot_module}")
    print(f"DEBUG: bots.bot.client = {bot_module.client}")
    bot = bot_module.client
    from cogs.ui.anime_tracker import AnimeTracker

    # 配置 dpytest (同步函數，不需要 await)
    dpytest.configure(bot)

    # 手動設定 bot ready 狀態 (dpytest v0.7 沒有 run() 函數)
    bot._ready = asyncio.Event()
    bot._ready.set()

    # 建立測試用 guild、channel
    guild = dpytest.get_config().guilds[0]
    channel = dpytest.get_config().channels[0]  # 預設文字頻道

    # 將頻道 ID 設為 ANIME_CHANNEL_ID 以便測試
    import cogs.ui.push_core as push_core_mod
    original_channel_id = push_core_mod.ANIME_CHANNEL_ID
    push_core_mod.ANIME_CHANNEL_ID = channel.id

    # 修改 bot 的資料庫路徑指向臨時資料庫
    import cogs.ui.anime_tracker as anime_tracker_mod
    original_db_path = anime_tracker_mod.ANIME_DB_PATH
    anime_tracker_mod.ANIME_DB_PATH = Path(temp_db_path)

    # 載入 cog
    await bot.add_cog(AnimeTracker(bot))

    # 等待 cog_load 完成（包含 _init_weekly_schedule_if_empty）
    await asyncio.sleep(0.5)

    # 提供測試上下文
    ctx = {
        "bot": bot,
        "guild": guild,
        "channel": channel,
        "channel_id": channel.id,
        "temp_db_path": temp_db_path,
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


# ==================== Bahamut API Mock ====================

class MockBahamutAPI:
    """模擬 Bahamut 動畫瘋 API 回應"""

    def __init__(self):
        self.schedule_data = self._default_schedule()
        self.new_anime_data = self._default_new_anime()
        self.video_details = {}
        self.call_count = {"schedule": 0, "new_anime": 0, "details": 0}

    def _default_schedule(self):
        """預設週表資料（模擬 newAnimeSchedule API）"""
        # 週一=1 ... 週日=7
        return {
            "1": [  # 週一
                {"title": "Spy×Family", "scheduleTime": "00:00", "videoSn": 1001, "animeSn": 5001, "cover": "https://example.com/spy.jpg"},
                {"title": "Jujutsu Kaisen", "scheduleTime": "01:00", "videoSn": 1002, "animeSn": 5002, "cover": "https://example.com/jjk.jpg"},
            ],
            "2": [  # 週二
                {"title": "Frieren", "scheduleTime": "22:00", "videoSn": 1003, "animeSn": 5003, "cover": "https://example.com/frieren.jpg"},
            ],
            "3": [],  # 週三
            "4": [  # 週四
                {"title": "One Piece", "scheduleTime": "21:00", "videoSn": 1004, "animeSn": 5004, "cover": "https://example.com/op.jpg"},
            ],
            "5": [],  # 週五
            "6": [  # 週六
                {"title": "Attack on Titan", "scheduleTime": "23:30", "videoSn": 1005, "animeSn": 5005, "cover": "https://example.com/aot.jpg"},
            ],
            "7": [],  # 週日
        }

    def _default_new_anime(self):
        """預設新番資料（模擬 newAnime.date API）"""
        # upTime 格式：MM/DD
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today_str = datetime.now(ZoneInfo('Asia/Taipei')).strftime("%m/%d")

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
        """模擬 newAnime.date API"""
        self.call_count["new_anime"] += 1
        return {"data": {"newAnime": {"date": self.new_anime_data, "popular": []}}}

    def get_video_details(self, video_sn):
        """模擬 video.php API"""
        self.call_count["details"] += 1
        return self.video_details.get(video_sn, {
            "data": {"anime": {
                "content": f"這是 videoSn={video_sn} 的動画簡介",
                "score": 4.5,
                "tags": ["奇幻", "冒陷"]
            }}})


@pytest.fixture
def mock_bahamut_api():
    """提供可自訂的 Bahamut API Mock"""
    return MockBahamutAPI()


@pytest.fixture(autouse=True)
def patch_bahamut_api(mock_bahamut_api):
    """
    自動打補釘所有 Bahamut API 呼叫
    適用於：AnimePushCore、AnimeScheduleTracker、AnimeTracker
    """
    import aiohttp

    async def mock_get(url, *args, **kwargs):
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

        if "newAnimeSchedule" in url or ("anime/v3/index.php" in url and "schedule" not in url):
            # 週表 API
            return MockResponse(mock_bahamut_api.get_schedule())
        elif "newAnime" in url or "anime/v3/index.php" in url:
            # 新番 API
            return MockResponse(mock_bahamut_api.get_new_anime())
        elif "video.php" in url:
            # 詳細資訊 API
            video_sn = int(url.split("sn=")[-1].split("&")[0]) if "sn=" in url else 0
            return MockResponse(mock_bahamut_api.get_video_details(video_sn))
        elif "animeVideo.php" in url:
            # 網頁爬蟲 fallback
            return MockResponse({"status": 200, "text": "<html></html>"}, status=200)

        return MockResponse({}, status=404)

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        yield mock_bahamut_api


# ==================== 時間控制 ====================

@pytest.fixture
def frozen_time():
    """
    凍結時間用於測試特定時刻的邏輯
    使用 unittest.mock.patch 正確模擬各模組的 datetime.now
    """
    from datetime import datetime as real_datetime
    from zoneinfo import ZoneInfo
    from unittest.mock import patch

    class TimeFreezer:
        def __init__(self):
            self.patches = []
            self.frozen_dt = None

        def freeze(self, dt: real_datetime):
            """凍結到指定時間"""
            import cogs.ui.push_core as pc
            import cogs.ui.anime_tracker as at
            import cogs.ui.schedule_tracker as st

            self.frozen_dt = dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo('Asia/Taipei'))

            # 建立一個模擬 datetime 類別，其 now classmethod 回傳固定時間
            class FrozenDatetime(real_datetime):
                @classmethod
                def now(cls, tz=None):
                    return self.frozen_dt

            # Patch 各模組的 datetime 參考
            for mod in [pc, at, st]:
                p = patch.object(mod, 'datetime', FrozenDatetime)
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
        pushed: bool = False
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
            up_time = datetime.now(ZoneInfo('Asia/Taipei')).strftime("%m/%d")

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
        assert len(messages) == expected_count, f"預期 {expected_count} 則訊息，實際 {len(messages)}"
        return messages
    return _assert


@pytest.fixture
def assert_db_state(isolated_db):
    """驗證資料庫狀態"""
    def _assert_weekly_schedule(week_start: str, day: int, time: str, pushed: bool = None):
        conn = isolated_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pushed FROM anime_weekly_schedule WHERE weekStartDate=? AND dayOfWeek=? AND scheduledTime=?",
            (week_start, day, time)
        )
        row = cursor.fetchone()
        if pushed is not None:
            assert row is not None, "週表記錄不存在"
            assert bool(row[0]) == pushed, f"pushed 狀態不符：預期 {pushed}，實際 {bool(row[0])}"
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

    return type("DBAssert", (), {
        "weekly_schedule": _assert_weekly_schedule,
        "notified": _assert_notified,
    })()


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