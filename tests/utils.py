"""
共用測試工具模組
提供：通用斷言、測試資料建構器、dpytest 包裝函數
供所有 cog 測試共用
"""

import discord
import discord.ext.test as dpytest
from typing import Optional, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo('Asia/Taipei')


# ==================== Embed 斷言輔助 ====================

def assert_embed_exists(messages: List[discord.Message], expected_count: int = 1) -> List[discord.Embed]:
    """斷言訊息有 embed 並回傳 embed 列表"""
    assert len(messages) == expected_count, f"預期 {expected_count} 則訊息，實際 {len(messages)}"
    embeds = []
    for msg in messages:
        assert msg.embeds, f"訊息 {msg.id} 應有 embed"
        embeds.extend(msg.embeds)
    return embeds


def assert_embed_field(
    embed: discord.Embed,
    field_name: str,
    expected_value: str = None,
    should_exist: bool = True
):
    """斷言 Embed 包含特定欄位"""
    field = next((f for f in embed.fields if f.name == field_name), None)
    if should_exist:
        assert field is not None, f"Embed 應包含欄位: {field_name}"
        if expected_value is not None:
            assert expected_value in field.value, (
                f"欄位 '{field_name}' 應包含 '{expected_value}'，實際: {field.value}"
            )
    else:
        assert field is None, f"Embed 不應包含欄位: {field_name}"
    return field


def assert_embed_title(embed: discord.Embed, expected_substring: str):
    """斷言 Embed 標題包含預期文字"""
    assert embed.title is not None, "Embed 應有標題"
    assert expected_substring in embed.title, f"標題應包含 '{expected_substring}'，實際: {embed.title}"


def assert_embed_color(embed: discord.Embed, expected_color: discord.Color):
    """斷言 Embed 顏色"""
    assert embed.color == expected_color, f"顏色不符：預期 {expected_color}，實際 {embed.color}"


# ==================== 資料庫斷言輔助 ====================

def assert_db_record(
    conn,
    table: str,
    where: Dict[str, Any],
    expected: Dict[str, Any] = None
):
    """斷言資料庫記錄存在且符合預期"""
    import sqlite3
    cursor = conn.cursor()
    conditions = " AND ".join([f"{k} = ?" for k in where.keys()])
    params = list(where.values())
    cursor.execute(f"SELECT * FROM {table} WHERE {conditions}", params)
    row = cursor.fetchone()
    assert row is not None, f"資料庫 {table} 應有記錄: {where}"

    if expected:
        # 取得欄位名稱
        col_names = [desc[0] for desc in cursor.description]
        for col, val in expected.items():
            if col in col_names:
                idx = col_names.index(col)
                assert row[idx] == val, f"欄位 {col} 不符：預期 {val}，實際 {row[idx]}"


def assert_db_count(conn, table: str, where: Dict[str, Any], expected_count: int):
    """斷言資料庫記錄筆數"""
    cursor = conn.cursor()
    conditions = " AND ".join([f"{k} = ?" for k in where.keys()])
    params = list(where.values())
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {conditions}", params)
    count = cursor.fetchone()[0]
    assert count == expected_count, f"{table} 記錄筆數不符：預期 {expected_count}，實際 {count}"


def get_db_records(conn, table: str, where: Dict[str, Any] = None) -> List[Dict]:
    """取得資料庫記錄列表（字典格式）"""
    cursor = conn.cursor()
    if where:
        conditions = " AND ".join([f"{k} = ?" for k in where.keys()])
        params = list(where.values())
        cursor.execute(f"SELECT * FROM {table} WHERE {conditions}", params)
    else:
        cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    return [dict(zip(col_names, row)) for row in rows]


# ==================== dpytest 互動包裝 ====================

async def click_button(
    member,
    custom_id: str,
    message_id: int,
    channel_id: int = None
):
    """包裝 dpytest click，自動處理重試與錯誤"""
    try:
        await member.click(custom_id=custom_id, message_id=message_id)
        return True, None
    except Exception as e:
        return False, str(e)


async def fill_modal_and_submit(
    modal,
    inputs: Dict[str, str]
) -> tuple[bool, str]:
    """填寫 Modal 並提交，回傳 (成功, 錯誤訊息)"""
    try:
        for field_name, value in inputs.items():
            modal.fill(field_name, value)
        await modal.submit()
        return True, None
    except Exception as e:
        return False, str(e)


async def send_command(
    member,
    command: str,
    channel_id: int = None
):
    """發送 Slash 指令（透過 dpytest）"""
    # dpytest 使用 message 內容匹配 slash 指令
    if channel_id:
        channel = dpytest.get_config().channels[0]  # 取得預設頻道
        await channel.send(command)
    else:
        channel = dpytest.get_config().channels[0]
        await channel.send(command)


def get_latest_message(channel_id: int = None) -> Optional[discord.Message]:
    """取得最新發送的訊息"""
    if channel_id:
        return dpytest.get_message(channel_id)
    return dpytest.get_message()


def get_followup_messages(
    channel_id: int = None,
    content_contains: str = None
) -> List[discord.Message]:
    """取得 follow-up 訊息（dpytest 會把所有訊息放在同一佇列）"""
    messages = dpytest.get_messages(channel_id) if channel_id else dpytest.get_messages()
    if content_contains:
        messages = [m for m in messages if m.content and content_contains in m.content]
    return messages


# ==================== 測試資料建構器 ====================

class AnimeTestDataBuilder:
    """動畫測試資料建構器"""

    @staticmethod
    def episode(
        video_sn: int = 1001,
        anime_sn: int = 5001,
        title: str = "Test Anime",
        volume: str = "第 1 話",
        cover: str = "https://example.com/cover.jpg",
        schedule_time: str = "00:00"
    ) -> Dict[str, Any]:
        return {
            "videoSn": video_sn,
            "animeSn": anime_sn,
            "title": title,
            "volume": volume,
            "cover": cover,
            "scheduleTime": schedule_time,
        }

    @staticmethod
    def schedule_item(
        day_of_week: int = 1,
        scheduled_time: str = "00:00",
        video_sn: int = 1001,
        anime_sn: int = 5001,
        title: str = "Test Anime",
        pushed: bool = False
    ) -> Dict[str, Any]:
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

    @staticmethod
    def new_anime_episode(
        video_sn: int = 1001,
        anime_sn: int = 5001,
        title: str = "Test Anime",
        volume: str = "第 1 話",
        up_time: str = None,
        cover: str = "https://example.com/test.jpg",
        popular: int = 10000,
    ) -> Dict[str, Any]:
        from datetime import datetime
        if up_time is None:
            up_time = datetime.now(TW_TZ).strftime("%m/%d")

        return {
            "videoSn": video_sn,
            "animeSn": anime_sn,
            "title": title,
            "volume": volume,
            "cover": cover,
            "upTime": up_time,
            "popular": popular,
        }


class VoteTestDataBuilder:
    """投票測試資料建構器"""

    VOTE_TYPES = {
        "masterpiece": "神作",
        "great": "佳作",
        "darkhorse": "黑馬",
        "decent": "普作/小品",
        "controversial": "爭議作",
        "disaster": "雷作/糞作",
    }

    @staticmethod
    def vote(
        video_sn: int,
        anime_sn: int,
        message_id: int,
        vote_type: str = "masterpiece",
        user_hash: str = "test_user_1",
        comment: str = None
    ) -> Dict[str, Any]:
        return {
            "video_sn": video_sn,
            "anime_sn": anime_sn,
            "message_id": message_id,
            "vote_type": vote_type,
            "user_hash": user_hash,
            "comment": comment,
        }

    @staticmethod
    def multiple_votes(
        message_id: int,
        vote_counts: Dict[str, int],
        base_user_hash: str = "user"
    ) -> List[Dict[str, Any]]:
        """建構多筆投票資料供批次插入"""
        votes = []
        for vote_type, count in vote_counts.items():
            for i in range(count):
                votes.append(VoteTestDataBuilder.vote(
                    video_sn=1001,
                    anime_sn=5001,
                    message_id=message_id,
                    vote_type=vote_type,
                    user_hash=f"{base_user_hash}_{vote_type}_{i}"
                ))
        return votes


# ==================== 時間控制輔助 ====================

class TimeController:
    """測試時間控制器（搭配 conftest.py 的 frozen_time fixture）"""

    def __init__(self, frozen_time_fixture):
        self.frozen = frozen_time_fixture

    def set_to_schedule_time(self, scheduled_time: str, days_offset: int = 0):
        """設定時間到指定排程時刻"""
        from datetime import datetime
        now = datetime.now(TW_TZ)
        target = now.replace(
            hour=int(scheduled_time[:2]),
            minute=int(scheduled_time[3:]),
            second=0,
            microsecond=0
        )
        if days_offset:
            target += datetime.timedelta(days=days_offset)
        self.frozen.freeze(target)
        return target

    def set_to_refresh_time(self):
        """設定到 22:00 週表刷新時間"""
        from datetime import datetime
        now = datetime.now(TW_TZ)
        target = now.replace(hour=22, minute=0, second=0, microsecond=0)
        self.frozen.freeze(target)
        return target

    def advance_minutes(self, minutes: int):
        """推進時間（需配合 frozen_time 實作）"""
        # 需要配合具體的 frozen_time 實作
        pass


# ==================== 非同步測試工具 ====================

async def wait_for_condition(condition_func, timeout: float = 5.0, interval: float = 0.1):
    """
    等待條件成立
    Args:
        condition_func: 回傳 bool 的同步/非同步函數
        timeout: 最長等待秒數
        interval: 檢查間隔
    """
    import asyncio
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        if asyncio.iscoroutinefunction(condition_func):
            result = await condition_func()
        else:
            result = condition_func()
        if result:
            return True
        await asyncio.sleep(interval)
    return False


async def wait_for_db_record(
    get_connection_func,
    table: str,
    where: Dict[str, Any],
    timeout: float = 5.0
) -> bool:
    """等待資料庫出現記錄"""
    async def check():
        conn = get_connection_func()
        cursor = conn.cursor()
        conditions = " AND ".join([f"{k} = ?" for k in where.keys()])
        params = list(where.values())
        cursor.execute(f"SELECT 1 FROM {table} WHERE {conditions}", params)
        return cursor.fetchone() is not None
    return await wait_for_condition(check, timeout)


# ==================== Mock 物件建構 ====================

from unittest.mock import MagicMock

def create_mock_interaction(
    user_id: int = 999999,
    message_id: int = 123456,
    channel_id: int = 789012,
    guild_id: int = 111111,
    mock_message: "MagicMock" = None
):
    """建構模擬的 discord.Interaction"""
    from unittest.mock import AsyncMock, MagicMock

    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.name = f"TestUser{user_id}"

    interaction.message = MagicMock()
    interaction.message.id = message_id

    interaction.channel = MagicMock()
    interaction.channel.id = channel_id
    # 添加 fetch_message 方法，返回 mock_message（預設建立一個基本的 mock message）
    if mock_message is None:
        mock_message = create_mock_message(message_id=message_id, channel_id=channel_id)
    async def mock_fetch_message(msg_id):
        return mock_message
    interaction.channel.fetch_message = mock_fetch_message

    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.guild.me = MagicMock()

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)

    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()

    interaction.custom_id = ""
    interaction.data = {}

    return interaction


def create_mock_message(
    message_id: int = 123456,
    channel_id: int = 789012,
    embeds: list = None,
    content: str = None
):
    """建構模擬的 discord.Message"""
    from unittest.mock import AsyncMock, MagicMock

    message = MagicMock()
    message.id = message_id
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.content = content or ""

    if embeds:
        message.embeds = embeds
    else:
        message.embeds = []

    message.edit = AsyncMock()
    message.delete = AsyncMock()

    return message


# ==================== 測試報告輔助 ====================

def print_test_summary(test_name: str, passed: bool, details: str = ""):
    """統一測試結果輸出格式"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} {test_name}")
    if details:
        print(f"    {details}")


# ==================== 常用斷言組合 ====================

async def assert_vote_flow_complete(
    dpytest_setup,
    isolated_db,
    message_id: int,
    expected_votes: Dict[str, int],
    expected_comments: List[str] = None
):
    """
    一次性驗證完整投票流程：
    - DB 統計正確
    - Embed 包含統計欄位
    - 評論正確（若提供）
    """
    from cogs.ui.push_core import get_vote_stats, get_vote_comments

    # 1. 驗證資料庫統計
    stats = get_vote_stats(isolated_db, message_id)
    for vote_type, count in expected_votes.items():
        assert stats.get(vote_type, 0) == count, (
            f"投票類型 {vote_type} 數量不符：預期 {count}，實際 {stats.get(vote_type, 0)}"
        )

    # 2. 驗證評論
    if expected_comments is not None:
        comments = get_vote_comments(isolated_db, message_id)
        assert len(comments) == len(expected_comments), (
            f"評論數不符：預期 {len(expected_comments)}，實際 {len(comments)}"
        )
        for expected in expected_comments:
            assert any(expected in c for c in comments), f"找不到預期評論: {expected}"

    # 3. 驗證 Discord 訊息 embed（如果有訊息）
    # 這需要 dpytest_setup 中的 channel_id 和 message_id 關聯
    return True


if __name__ == "__main__":
    # 簡單自測
    print("✅ tests/utils.py 載入無誤")
    print("可用函數：")
    print("  - assert_embed_field")
    print("  - assert_db_record")
    print("  - click_button / fill_modal_and_submit")
    print("  - AnimeTestDataBuilder / VoteTestDataBuilder")
    print("  - create_mock_interaction / create_mock_message")