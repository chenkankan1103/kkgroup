# -*- coding: utf-8 -*-
"""動畫推送 Components V2 版面（測試版，尚未接上推送路徑）

為什麼另開一支而不是直接改 push_embed.py：舊版 embed 還在線上跑，V2 得先在
測試頻道驗證外觀與互動，確認無痛之後才回頭覆蓋舊版。

與舊版的關係（刻意保持一致，切換時呼叫端才不用改語意）：
- 吃同一個 episode dict、同一組 push_mode 字串
- 沿用同一組按鈕 custom_id（anime_vote_{分數}_{videoSn} / anime_comment_{videoSn}），
  既有的投票寫入、發幣防重複、重啟重註冊都不用改
- 投票與留言的回調「整支沿用」AnimePushView 的實作，只覆蓋兩個重畫畫面的接縫。
  這兩支包辦 DB 寫入、發幣閘門與使用者回覆，抄一份出來早晚會漂移 ——
  尤其是發幣的 UNIQUE(user_id, message_id, reward_type) 閘門，抄漏一次就是印鈔。

沿用之所以接得起來，是因為舊實作把「更新畫面」寫成 embed 專屬的形式：
- _vote_callback 的更新段落包在 `if interaction.message.embeds:` 裡，
  V2 訊息的 embeds 是空的，整段自動跳過（不會噴錯，只是什麼都沒做）
- _comment_callback 的更新段落走 `await outer_self._refresh_comments_field(...)`
所以只要覆蓋那兩個接縫，其餘邏輯一行都不用動。

V2 與 embed 的三個關鍵差異（改版時必須記得）：
1. V2 訊息不能帶 content / embed / embeds / stickers / poll。轉換是「整則訊息重寫」，
   不是把 embed 換掉就好 —— discord.py 偵測到 V2 元件會自動補上
   flags.components_v2（http.py 的 handle_message_parameters），但不會幫你清掉
   content/embed，兩者同時送會被 API 擋下來。
2. 沒有「欄位」概念，也就沒有 1024 字元的欄位值上限 —— 留言可以多顯示幾則。
3. 但 LayoutView 有另一個全域預算：所有 TextDisplay 的內容加總上限 4000 字元
   （LayoutView.content_length 的 docstring）。比 embed 的單欄位上限寬鬆，
   卻比「每個 TextDisplay 各 4000」嚴格，所以放寬之餘仍要留預算給其他區塊。
"""

import logging
import re
from typing import Optional

import discord
from discord import ui

from cogs.ui.push_embed import (
    _DEFAULT_COLOR,
    _PUSH_MODE_COLORS,
    _format_count,
    _format_score,
    _truncate,
)
from shared.utils.embed_views import (
    COMMENTS_FIELD_NAME,
    CUMULATIVE_FIELD_NAME,
    EPISODE_FIELD_NAME,
    REWARD_HINT,
    VOTE_TYPE_LABELS,
    AnimePushView,
    format_comments,
)

logger = logging.getLogger(__name__)

# 版面變體
#   gallery   —— 底部放全寬大圖，忠實對應舊 embed 的 set_image
#   thumbnail —— 標題旁放小縮圖（Section + Thumbnail），省下大片垂直空間，
#                代價是失去大圖的視覺重量
# 兩者資訊完全相同，差別只在封面怎麼擺，留給測試頻道決定。
VARIANT_GALLERY = "gallery"
VARIANT_THUMBNAIL = "thumbnail"
DEFAULT_VARIANT = VARIANT_GALLERY

# 舊 embed 受欄位值 1024 字元所迫，簡介只留 200 字、留言只顯示 3 則 × 60 字。
# V2 沒有欄位上限，放寬之餘仍要留預算給標題、統計與 footer（見模組 docstring 第 3 點）。
DESCRIPTION_LIMIT = 500
COMMENT_DISPLAY_LIMIT = 6
COMMENT_MAX_LEN = 100

# 標題已含集數標記時就不再附加 volume，避免出現「第5集 · 第5集」。
# 與 push_embed.py 的 episode_pattern 同一條規則。
_EPISODE_PATTERN = re.compile(
    r"第\s*\d+\s*[集話]|\d+\s*話|Ep\s*\d+|\[\s*\d+\s*\]", re.IGNORECASE
)


def _display_title(episode: dict) -> str:
    """組出顯示用標題；集數已在標題裡就不重複附加。"""
    title = episode.get("title") or "未知標題"
    volume = str(episode.get("volume") or "").strip()
    if volume and not _EPISODE_PATTERN.search(title):
        return f"{title} · {volume}"
    return title


def _popular_text(episode: dict) -> str:
    """觀看次數文字：有當季總數就顯示總數與每集平均，否則退回本集觀看數。"""
    total_views = episode.get("total_views", 0) or 0
    episode_count = episode.get("episode_count", 1) or 1
    if total_views > 0 and episode_count > 0:
        avg = _format_count(total_views // episode_count)
        return f"{_format_count(total_views)} (平均 {avg}/集)"
    text = _format_count(episode.get("popular", 0))
    return f"{text} 總觀看" if text else ""


def _info_line(episode: dict, push_mode: str) -> str:
    """把 embed 的三個行內欄位收成一行。

    embed 的行內欄位在手機上會各自折行、讀起來像三段碎片；V2 沒有行內欄位，
    索性收成一行，桌機手機都讀得下去。
    """
    parts = []
    popular = _popular_text(episode)
    score = _format_score(episode.get("score", 0))
    if popular:
        parts.append(f"👁️ {popular}")
    if score:
        parts.append(f"⭐ {score}")
    parts.append(f"📡 {push_mode}")
    return " ・ ".join(parts)


class AnimePushLayout(ui.LayoutView):
    """動畫推送的 V2 版面（同時承載按鈕）。

    與 AnimePushView 最大的差別：按鈕不再自成一個 View，而是長在版面裡面
    （Container → ActionRow）。這是 V2 的硬性要求 —— 一則訊息只能帶一組
    components，embed + View 的雙軌模式在 V2 不存在。

    timeout=None 是持久化的必要條件；搭配每個按鈕都有明確 custom_id，
    bot.add_view() 才會接受。上層的 Container 不覆寫 is_dispatchable，
    所以 view.is_persistent() 會直接回 True 而不往下檢查按鈕 ——
    也就是說「add_view 沒報錯」不等於按鈕註冊成功，custom_id 一定要自己盯。
    """

    # 投票類型對照表。沿用過來的 _vote_callback 會讀 self.VOTE_TYPES，
    # 少了這行會在點擊當下才噴 AttributeError。
    VOTE_TYPES = VOTE_TYPE_LABELS

    # 整支沿用 production 的實作，只覆蓋下面標了「V2 版」的接縫。
    _grant_reward = AnimePushView._grant_reward
    _build_vote_stats_text = AnimePushView._build_vote_stats_text
    _build_cumulative_stats_text = AnimePushView._build_cumulative_stats_text
    _comment_callback = AnimePushView._comment_callback

    def __init__(
        self,
        episode: dict,
        push_mode: str = "unknown",
        db_adapter=None,
        variant: str = DEFAULT_VARIANT,
        message_id: Optional[int] = None,
    ):
        super().__init__(timeout=None)
        self.episode = episode
        self.push_mode = push_mode
        self.variant = variant
        self.db = db_adapter
        self.video_sn = episode.get("videoSn")
        self.anime_sn = episode.get("animeSn")
        # 先有 message_id 才組版面，統計才會以「這一則訊息」精準查詢；
        # 順序顛倒的話重畫會退回用 videoSn 查，數字與舊版不一致。
        self.message_id = message_id

        self.add_item(self._build_container())

    # ---------------------------------------------------------------- 版面

    def _build_container(self) -> ui.Container:
        """組出整張卡片（含按鈕列）。"""
        colour = _PUSH_MODE_COLORS.get(self.push_mode, _DEFAULT_COLOR)
        container = ui.Container(accent_colour=colour)

        title = _display_title(self.episode)
        cover = self.episode.get("cover", "")
        description = _truncate(
            self.episode.get("description") or self.episode.get("content") or "",
            DESCRIPTION_LIMIT,
        )

        # 標題區：縮圖版把封面掛在 Section 右側；大圖版留到最下面用 MediaGallery 呈現。
        # 刻意不同時放兩份 —— 同一張圖出現兩次看起來像 bug。
        if self.variant == VARIANT_THUMBNAIL and cover:
            container.add_item(
                ui.Section(
                    ui.TextDisplay(f"# {title}"),
                    ui.TextDisplay(description or "（無簡介）"),
                    accessory=ui.Thumbnail(cover, description="封面"),
                )
            )
        else:
            container.add_item(ui.TextDisplay(f"# {title}"))
            container.add_item(ui.TextDisplay(description or "（無簡介）"))

        container.add_item(ui.Separator())

        # 資訊列 + 獎勵提示。舊版把獎勵提示接在簡介尾端，混在內文裡容易被讀過去，
        # 這裡獨立成一行讓它自己站著。
        container.add_item(ui.TextDisplay(_info_line(self.episode, self.push_mode)))
        container.add_item(ui.TextDisplay(REWARD_HINT))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))

        # 統計區。標題沿用同一組常數，重畫時才比對得到
        # （舊版靠 embed_views._set_embed_field 用同一個名字定位欄位）。
        episode_stats = self._build_vote_stats_text()
        if episode_stats:
            container.add_item(ui.TextDisplay(f"### {EPISODE_FIELD_NAME}"))
            container.add_item(ui.TextDisplay(episode_stats))

        cumulative_stats = self._build_cumulative_stats_text()
        if cumulative_stats:
            container.add_item(ui.TextDisplay(f"### {CUMULATIVE_FIELD_NAME}"))
            container.add_item(ui.TextDisplay(cumulative_stats))

        # 留言：沒有留言就整塊不放，不留空殼佔版面（與舊版行為一致）
        comments_text = self._build_comments_text()
        if comments_text:
            container.add_item(ui.TextDisplay(f"### {COMMENTS_FIELD_NAME}"))
            container.add_item(ui.TextDisplay(comments_text))

        # 大圖版：封面放最後，位置對應舊 embed 的 set_image
        if self.variant == VARIANT_GALLERY and cover:
            container.add_item(ui.Separator())
            container.add_item(
                ui.MediaGallery(discord.MediaGalleryItem(cover, description="封面"))
            )

        for row in self._build_action_rows():
            container.add_item(row)

        container.add_item(ui.Separator())
        container.add_item(
            ui.TextDisplay(
                f"-# KKGroup 動畫推送 ・ <t:{int(discord.utils.utcnow().timestamp())}:f>"
            )
        )
        return container

    def _build_action_rows(self) -> list:
        """組出投票列與留言／連結列。"""
        rows = []

        # 五顆評分鈕。custom_id 與 AnimePushView 完全一致，DB 的 vote_type 才對得上。
        vote_row = ui.ActionRow()
        for vote_key, (vote_label, colour_emoji) in VOTE_TYPE_LABELS.items():
            button = ui.Button(
                label=f"{colour_emoji} {vote_label}",
                custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                style=discord.ButtonStyle.secondary,
            )
            button.callback = self._vote_callback
            vote_row.add_item(button)
        rows.append(vote_row)

        action_row = ui.ActionRow()
        comment_button = ui.Button(
            label="💬 留言",
            custom_id=f"anime_comment_{self.video_sn}",
            style=discord.ButtonStyle.secondary,
        )
        comment_button.callback = self._comment_callback
        action_row.add_item(comment_button)
        action_row.add_item(
            ui.Button(
                label="▶️ 觀看第一集",
                url=f"https://ani.gamer.com.tw/animeRef.php?sn={self.anime_sn}",
                style=discord.ButtonStyle.link,
            )
        )
        action_row.add_item(
            ui.Button(
                label="▶️ 觀看",
                url=f"https://ani.gamer.com.tw/animeVideo.php?sn={self.video_sn}",
                style=discord.ButtonStyle.link,
            )
        )
        rows.append(action_row)

        return rows

    # -------------------------------------------------- 覆蓋沿用實作的接縫

    def _build_comments_text(self) -> Optional[str]:
        """V2 版的留言文字：顯示 6 則、每則 100 字。

        舊版受 embed 欄位 1024 字元所迫只能 3 則 × 60 字；V2 額度寬鬆，
        但 get_comments_by_anime 預設只回 3 筆，limit 必須一起放大，
        否則放寬 format_comments 也只是把同樣那三則寫得更長而已。
        """
        try:
            if (
                not self.db
                or not hasattr(self.db, "get_comments_by_anime")
                or not self.anime_sn
            ):
                return None
            comments = self.db.get_comments_by_anime(
                int(self.anime_sn), limit=COMMENT_DISPLAY_LIMIT
            )
            return format_comments(
                comments, limit=COMMENT_DISPLAY_LIMIT, max_len=COMMENT_MAX_LEN
            )
        except Exception as e:
            logger.error(f"❌ 重建觀眾留言失敗: {e}")
            return None

    async def _refresh_comments_field(self, interaction, message=None) -> None:
        """V2 版：留言後整組重畫（舊版是覆蓋 embed 的留言欄位，V2 沒有欄位可改）。

        這個方法名是沿用實作的接縫 —— AnimePushView._comment_callback 會呼叫它，
        在這裡覆蓋就等於接管了留言後的畫面更新。
        """
        await self._refresh_display(interaction, message)

    async def _refresh_display(self, interaction, message=None) -> None:
        """把整張卡片重新組一次並 edit 回原訊息。

        舊版是複製 embed、覆蓋欄位再 edit；V2 沒有欄位可改，只能整組重建。
        按鈕的 custom_id 不變，所以重畫不會讓按鈕失效 —— discord.py 在
        Message.edit(view=...) 之後會自動把新 view 註冊進 view store。
        """
        message = message or interaction.message
        if message is None and self.message_id and interaction.channel:
            message = await interaction.channel.fetch_message(self.message_id)
        if message is None:
            return

        fresh = AnimePushLayout(
            self.episode,
            push_mode=self.push_mode,
            db_adapter=self.db,
            variant=self.variant,
            message_id=message.id,
        )
        await message.edit(view=fresh)

    async def _vote_callback(self, interaction: discord.Interaction):
        """投票：沿用 AnimePushView 的實作，再補上 V2 的畫面重畫。

        沿用的那支會 defer、寫 DB、發幣、回覆使用者；它的 embed 更新段落因為
        V2 訊息沒有 embeds 而自動跳過，所以在這裡補一次重畫。
        """
        await AnimePushView._vote_callback(self, interaction)
        try:
            await self._refresh_display(interaction)
        except Exception as e:
            logger.error(f"❌ 更新 V2 投票統計失敗: {e}")


async def generate_anime_layout(
    episode: dict,
    push_mode: str = "unknown",
    db=None,
    variant: str = DEFAULT_VARIANT,
) -> Optional[ui.LayoutView]:
    """生成動畫推送的 V2 版面。

    對應舊版的 generate_anime_embed，但回傳的是已經含按鈕的 LayoutView ——
    呼叫端只需要 channel.send(view=layout, silent=True)，
    不再有 generate_anime_view 那個獨立步驟。

    Args:
        episode: 動畫資訊字典
        push_mode: 推送模式（"排程推送" / "輪詢 (備案模式)"）
        db: AnimePushDB 實例，用於取投票統計
        variant: 版面變體（gallery / thumbnail）

    Returns:
        LayoutView，失敗則回傳 None
    """
    try:
        return AnimePushLayout(
            episode, push_mode=push_mode, db_adapter=db, variant=variant
        )
    except Exception as e:
        logger.error(f"生成 V2 版面失敗: {e}")
        return None
