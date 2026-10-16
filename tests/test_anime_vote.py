# -*- coding: utf-8 -*-
"""AnimePushView 投票 / 留言互動測試。

歷史沿革（為何本檔與舊版不同）：
- 舊版測試的 `AnimeVoteView` 已併入 `shared/utils/embed_views.AnimePushView`，
  不再是 `AnimeTracker` 的類別屬性。
- 舊版的 `_update_message_stats` 已移除，本檔不再測試不存在的方法。
- 投票（+2000）與留言（+10000）KK 幣獎勵共用 `AnimePushView._grant_reward`，
  兩者都套用「每人每則一次 + 24 小時時窗」兩道閘門。留言不像投票會被
  record_vote 的 DELETE 擋掉，少了第一道閘門就等於無限印鈔。
- 投票選項於 2026-10-16 由「神作/佳作/…」改為分數 5-1，`vote_type` 同步改為
  分數字串；本檔的 custom_id 與統計鍵一併跟著改。
- 資料庫改用生產同款的 `AnimePushDB`（`AnimeTracker.set_dependencies` 傳入的
  就是它），而非測試專用的 wrapper。
"""

from unittest.mock import MagicMock

import discord
import pytest

from cogs.ui.push_core_simple import AnimePushDB
from shared.utils.embed_views import (
    COMMENT_REWARD_AMOUNT,
    CUMULATIVE_FIELD_NAME,
    EPISODE_FIELD_NAME,
    VOTE_REWARD_AMOUNT,
    VOTE_REWARD_WINDOW_HOURS,
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


def _backdate_notified(db, video_sn: int, hours: int) -> None:
    """把 notified_at 往前挪，模擬「很久以前推播的舊訊息」"""
    conn = db._get_conn()
    conn.execute(
        "UPDATE anime_notified SET notified_at = datetime('now', ?) WHERE videoSn=?",
        (f"-{hours} hours", video_sn),
    )
    conn.commit()
    conn.close()


async def _submit_comment(view, db, user_id, text, message_id=MESSAGE_ID):
    """點留言按鈕 → 開 Modal → 送出文字，回傳 modal interaction"""
    interaction = await _click(view, db, f"anime_comment_{VIDEO_SN}", user_id=user_id)
    modal = interaction.response.send_modal.call_args[0][0]

    modal_interaction = create_mock_interaction(user_id=user_id, message_id=message_id)
    modal.comment_input = MagicMock()
    modal.comment_input.__str__ = MagicMock(return_value=text)
    await modal.on_submit(modal_interaction)
    return modal_interaction


class TestAnimeVoteInteraction:
    """投票按鈕 callback 的資料庫寫入與回應行為"""

    @pytest.mark.asyncio
    async def test_vote_button_records_vote(self, db):
        """點擊「5分」→ 立即 defer → 寫入 DB → follow-up 確認"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        interaction = await _click(
            view, db, f"anime_vote_5_{VIDEO_SN}", user_id=111111
        )

        # defer() 必須先於任何耗時操作（Discord 3 秒超時）
        interaction.response.defer.assert_awaited()

        stats = db.get_vote_stats(VIDEO_SN, MESSAGE_ID)
        assert stats["5"] == 1, f"預期 5分=1，實際 {stats}"
        assert "投票成功" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_multiple_votes_accumulate_independently(self, db):
        """不同用戶投不同類型 → 各自獨立累加"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=1001)
        await _click(view, db, f"anime_vote_4_{VIDEO_SN}", user_id=1002)

        stats = db.get_vote_stats(VIDEO_SN, MESSAGE_ID)
        assert stats["5"] == 1
        assert stats["4"] == 1

    @pytest.mark.asyncio
    async def test_same_user_cannot_vote_twice(self, db):
        """同一用戶同一訊息重複投票 → 只記第一票"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=2001)
        await _click(view, db, f"anime_vote_4_{VIDEO_SN}", user_id=2001)

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
            vote_type="4",
            user_hash="hist_user",
        )

        view = _make_view(db)
        button = _find_button(view, f"anime_vote_5_{VIDEO_SN}")

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
        assert "5分" in fields[EPISODE_FIELD_NAME]
        assert "4分" in fields[CUMULATIVE_FIELD_NAME], "累計應含其他集數的票"


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

        modal_interaction = await _submit_comment(
            view, db, user_id=4001, text="這部動畫真好看！"
        )

        # 發幣要寫 user_data.db，超過 3 秒會被判定「應用程式沒有回應」，
        # 故 on_submit 必須先 defer 再 followup（不能走 response.send_message）
        modal_interaction.response.defer.assert_awaited()
        assert "評論已保存" in str(modal_interaction.followup.send.call_args)

        comments = db.get_vote_comments(VIDEO_SN)
        assert len(comments) >= 1
        assert any("好看" in c["comment"] for c in comments), comments

    @pytest.mark.asyncio
    async def test_comment_shows_up_on_later_episode_embed(self, db):
        """留言以 animeSn 聚合 → 同系列其他集數的 embed 也看得到"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _submit_comment(view, db, user_id=4002, text="這部必看")

        # 不同 videoSn、同 animeSn 的後續集數應查得到這則留言
        later = db.get_comments_by_anime(ANIME_SN)
        assert any("必看" in c["comment"] for c in later), later
        assert db.get_comments_by_anime(ANIME_SN + 1) == [], "不應跨系列外洩"

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

        # 空留言不動用 DB，也就不需要 defer，仍走 response.send_message
        assert "不能為空" in str(modal_interaction.response.send_message.call_args)
        assert db.get_vote_comments(VIDEO_SN) == [], "空留言不應寫入資料庫"


class TestAnimeInteractionReward:
    """投票（+2000）與留言（+10000）KK幣獎勵。

    兩者共用 `_grant_reward`，閘門一致：每人每則一次，且只獎勵剛推播的集數。
    """

    @pytest.fixture
    def kkcoin_awards(self, monkeypatch):
        """攔截 KK幣發放，回傳 (user_id, amount) 清單"""
        from shared.db import async_adapter

        awards: list = []

        async def fake_update_user_kkcoin(user_id, amount):
            awards.append((user_id, amount))
            return True

        monkeypatch.setattr(async_adapter, "update_user_kkcoin", fake_update_user_kkcoin)
        return awards

    @pytest.mark.asyncio
    async def test_first_vote_awards_2000_kkcoin(self, db, kkcoin_awards):
        """首次投票 → 發 2000 KK幣，且 follow-up 有告知"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        interaction = await _click(
            view, db, f"anime_vote_5_{VIDEO_SN}", user_id=5001
        )

        assert kkcoin_awards == [(5001, VOTE_REWARD_AMOUNT)], kkcoin_awards
        assert "2000" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_revote_does_not_award_again(self, db, kkcoin_awards):
        """同用戶同訊息改票 → 只發一次（record_vote 會 DELETE 再 INSERT）"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=5002)
        await _click(view, db, f"anime_vote_4_{VIDEO_SN}", user_id=5002)

        assert len(kkcoin_awards) == 1, f"改票不應重複發幣，實際 {kkcoin_awards}"

    @pytest.mark.asyncio
    async def test_other_user_same_message_still_awarded(self, db, kkcoin_awards):
        """不同用戶投同一則 → 各自都拿得到"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=5003)
        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=5004)

        assert kkcoin_awards == [(5003, VOTE_REWARD_AMOUNT), (5004, VOTE_REWARD_AMOUNT)]

    @pytest.mark.asyncio
    async def test_vote_outside_window_does_not_award(self, db, kkcoin_awards):
        """超過時窗的舊推播 → 不發幣（防止回頭翻訊息刷幣）"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        _backdate_notified(db, VIDEO_SN, VOTE_REWARD_WINDOW_HOURS + 1)

        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=5005)

        assert kkcoin_awards == [], "超過時窗的舊訊息不應發幣"

    @pytest.mark.asyncio
    async def test_unnotified_video_does_not_award(self, db, kkcoin_awards):
        """未曾推播的集數（無 anime_notified 紀錄）→ 不發幣"""
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=5006)

        assert kkcoin_awards == [], "未曾推播的集數不應發幣"

    @pytest.mark.asyncio
    async def test_first_comment_awards_10000_kkcoin(self, db, kkcoin_awards):
        """首次留言 → 發 10000 KK幣，且 follow-up 有告知"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        modal_interaction = await _submit_comment(view, db, user_id=6001, text="頭香")

        assert kkcoin_awards == [(6001, COMMENT_REWARD_AMOUNT)], kkcoin_awards
        assert "10000" in str(modal_interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_repeated_comment_does_not_award_again(self, db, kkcoin_awards):
        """同一則訊息重複留言 → 只發一次。

        留言不像投票會被 record_vote 的 DELETE 擋掉，若沒有 anime_rewards 的
        UNIQUE(user_id, message_id, reward_type)，就是無限印鈔。
        """
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _submit_comment(view, db, user_id=6002, text="第一次")
        await _submit_comment(view, db, user_id=6002, text="第二次")
        await _submit_comment(view, db, user_id=6002, text="第三次")

        assert len(kkcoin_awards) == 1, f"重複留言不應重複發幣，實際 {kkcoin_awards}"

    @pytest.mark.asyncio
    async def test_comment_outside_window_does_not_award(self, db, kkcoin_awards):
        """超過時窗的舊推播留言 → 不發幣"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        _backdate_notified(db, VIDEO_SN, VOTE_REWARD_WINDOW_HOURS + 1)

        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _submit_comment(view, db, user_id=6003, text="考古")

        assert kkcoin_awards == [], "超過時窗的舊訊息不應發幣"

    @pytest.mark.asyncio
    async def test_vote_and_comment_rewards_are_independent(self, db, kkcoin_awards):
        """同一則訊息先投票再留言 → 兩筆各自成立（reward_type 不同）"""
        db.add_notified(VIDEO_SN, ANIME_SN, "測試動漫", volume="1")
        view = _make_view(db)
        view.message_id = MESSAGE_ID

        await _click(view, db, f"anime_vote_5_{VIDEO_SN}", user_id=6004)
        await _submit_comment(view, db, user_id=6004, text="投完順便留個言")

        assert kkcoin_awards == [
            (6004, VOTE_REWARD_AMOUNT),
            (6004, COMMENT_REWARD_AMOUNT),
        ], kkcoin_awards


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
