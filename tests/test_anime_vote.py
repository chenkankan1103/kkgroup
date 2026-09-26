# -*- coding: utf-8 -*-
"""AnimePushView 投票 / 留言互動測試。

歷史沿革（為何本檔與舊版不同）：
- 舊版測試的 `AnimeVoteView` 已併入 `shared/utils/embed_views.AnimePushView`，
  不再是 `AnimeTracker` 的類別屬性。
- 舊版的 KK 幣獎勵斷言（投票 +2000 / 留言 +3000）與 `_update_message_stats`
  皆已移除，本檔不再測試不存在的方法。
- 資料庫改用生產同款的 `AnimePushDB`（`AnimeTracker.set_dependencies` 傳入的
  就是它），而非測試專用的 wrapper。
"""

from unittest.mock import MagicMock

import discord
import pytest

from cogs.ui.push_core_simple import AnimePushDB
from shared.utils.embed_views import (
    CUMULATIVE_FIELD_NAME,
    EPISODE_FIELD_NAME,
    AnimePushView,
)
from tests.utils import create_mock_interaction, create_mock_message

VIDEO_SN = 12345
ANIME_SN = 67890
MESSAGE_ID = 999999999


@pytest.fixture
def db(temp_db_path):
    """生產同款資料庫（AnimePushDB）"""
    return AnimePushDB(temp_db_path)


def _make_view(db) -> AnimePushView:
    return AnimePushView(
        {"videoSn": VIDEO_SN, "animeSn": ANIME_SN, "title": "測試動漫"},
        db_adapter=db,
    )


def _find_button(view: AnimePushView, custom_id: str) -> discord.ui.Button:
    button = next(
        (
            item
            for item in view.children
            if isinstance(item, discord.ui.Button) and item.custom_id == custom_id
        ),
        None,
    )
    assert button is not None, f"應找到按鈕 {custom_id}"
    return button


async def _click(view, db, custom_id, user_id, message_id=MESSAGE_ID):
    """點擊指定按鈕並回傳 mock interaction"""
    button = _find_button(view, custom_id)
    interaction = create_mock_interaction(user_id=user_id, message_id=message_id)
    interaction.custom_id = button.custom_id
    await button.callback(interaction)
    return interaction


class TestAnimeVoteInteraction:
    """投票按鈕 callback 的資料庫寫入與回應行為"""

    @pytest.mark.asyncio
    async def test_vote_button_records_vote(self, db):
        """點擊「神作」→ 立即 defer → 寫入 DB → follow-up 確認"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        interaction = await _click(
            view, db, f"anime_vote_masterpiece_{VIDEO_SN}", user_id=111111
        )

        # defer() 必須先於任何耗時操作（Discord 3 秒超時）
        interaction.response.defer.assert_awaited()

        stats = db.get_vote_stats(VIDEO_SN, MESSAGE_ID)
        assert stats["masterpiece"] == 1, f"預期 masterpiece=1，實際 {stats}"
        assert "投票成功" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_multiple_votes_accumulate_independently(self, db):
        """不同用戶投不同類型 → 各自獨立累加"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_masterpiece_{VIDEO_SN}", user_id=1001)
        await _click(view, db, f"anime_vote_great_{VIDEO_SN}", user_id=1002)

        stats = db.get_vote_stats(VIDEO_SN, MESSAGE_ID)
        assert stats["masterpiece"] == 1
        assert stats["great"] == 1

    @pytest.mark.asyncio
    async def test_same_user_cannot_vote_twice(self, db):
        """同一用戶同一訊息重複投票 → 只記第一票"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_masterpiece_{VIDEO_SN}", user_id=2001)
        await _click(view, db, f"anime_vote_great_{VIDEO_SN}", user_id=2001)

        stats = db.get_vote_stats(VIDEO_SN, MESSAGE_ID)
        assert sum(stats.values()) == 1, f"同用戶重複投票應只記一票，實際 {stats}"

    @pytest.mark.asyncio
    async def test_vote_rebuilds_episode_and_cumulative_fields(self, db):
        """投票成功後，「本集」與「全系列累計」兩個欄位都必須被重建。

        只重建其中一個會讓兩欄數字互相矛盾，故兩者都要驗。
        """
        # 先塞一筆同系列其他集數的歷史票，讓「全系列累計」有非零數字
        db.record_vote(
            video_sn=VIDEO_SN - 1,
            anime_sn=ANIME_SN,
            message_id=None,
            vote_type="great",
            user_hash="hist_user",
        )

        view = _make_view(db)
        button = _find_button(view, f"anime_vote_masterpiece_{VIDEO_SN}")

        embed = discord.Embed(title="測試動漫")
        embed.add_field(name=EPISODE_FIELD_NAME, value="舊資料", inline=False)
        embed.add_field(name=CUMULATIVE_FIELD_NAME, value="舊資料", inline=False)
        message = create_mock_message(message_id=MESSAGE_ID, embeds=[embed])

        interaction = create_mock_interaction(user_id=3001, message_id=MESSAGE_ID)
        interaction.custom_id = button.custom_id
        # create_mock_interaction 一律以 MagicMock 覆蓋 interaction.message，
        # 故此處顯式指定，才能真的走到 embed 重建路徑
        interaction.message = message

        await button.callback(interaction)

        message.edit.assert_awaited()
        updated = message.edit.call_args.kwargs["embed"]
        fields = {f.name: f.value for f in updated.fields}
        assert EPISODE_FIELD_NAME in fields, f"應重建本集欄位: {list(fields)}"
        assert CUMULATIVE_FIELD_NAME in fields, f"應重建累計欄位: {list(fields)}"
        assert "神作" in fields[EPISODE_FIELD_NAME]
        assert "佳作" in fields[CUMULATIVE_FIELD_NAME], "累計應含其他集數的票"


class TestAnimeCommentInteraction:
    """留言按鈕 / Modal 行為"""

    @pytest.mark.asyncio
    async def test_comment_button_opens_modal_and_records(self, db):
        """點擊留言 → 開啟 Modal → 提交 → DB 記錄 + 確認訊息"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        interaction = await _click(view, db, f"anime_comment_{VIDEO_SN}", user_id=4001)

        interaction.response.send_modal.assert_called()
        modal = interaction.response.send_modal.call_args[0][0]
        assert modal.title == "留下匿名評論"

        modal_interaction = create_mock_interaction(user_id=4001, message_id=MESSAGE_ID)
        modal.comment_input = MagicMock()
        modal.comment_input.__str__ = MagicMock(return_value="這部動畫真好看！")
        await modal.on_submit(modal_interaction)

        assert "評論已保存" in str(modal_interaction.response.send_message.call_args)

        comments = db.get_vote_comments(VIDEO_SN)
        assert len(comments) >= 1
        assert any("好看" in c["comment"] for c in comments), comments

    @pytest.mark.asyncio
    async def test_comment_modal_empty_submission_rejected(self, db):
        """空留言提交 → 拒絕且不寫入 DB"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        interaction = await _click(view, db, f"anime_comment_{VIDEO_SN}", user_id=7001)
        modal = interaction.response.send_modal.call_args[0][0]

        modal_interaction = create_mock_interaction(user_id=7001, message_id=MESSAGE_ID)
        modal.comment_input = MagicMock()
        modal.comment_input.__str__ = MagicMock(return_value="")
        await modal.on_submit(modal_interaction)

        assert "不能為空" in str(modal_interaction.response.send_message.call_args)
        assert db.get_vote_comments(VIDEO_SN) == [], "空留言不應寫入資料庫"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
