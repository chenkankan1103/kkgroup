"""
動畫推送 Embed 格式模組
專門負責生成動畫推送的 Embed 格式和 View (按鈕)
"""

import logging
import discord
import re
from typing import Optional, Dict
from shared.utils.embed_views import create_anime_push_view

logger = logging.getLogger(__name__)

# 依推送模式配色的主題色 (提供視覺上的區隔)
_PUSH_MODE_COLORS = {
    "排程推送": 0x7C4DFF,        # 紫色：精準排程
    "輪詢 (備案模式)": 0xF39C12,  # 橙色：備案輪詢
}
_DEFAULT_COLOR = 0x7289DA  # Discord blurple 作為預設

_DESCRIPTION_LIMIT = 200  # 描述截斷長度


def _format_count(value) -> str:
    """將大數字格式化為中文易讀格式（萬 / 億）。

    例如 12345 -> 「1.2萬」、150000000 -> 「1.5億」。
    非數值或非正數直接回傳空字串，交由呼叫端決定是否顯示。
    """
    try:
        num = int(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return ""
    if num <= 0:
        return ""

    if num >= 100_000_000:
        return f"{num / 100_000_000:.1f}億"
    if num >= 10_000:
        return f"{num / 10_000:.1f}萬"
    return str(num)


def _truncate(text: str, limit: int) -> str:
    """截斷過長文字並加上省略號，避免 embed 描述過於冗長。"""
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_score(score) -> str:
    """將評分格式化為小數點後一位，無效值回傳空字串。"""
    try:
        val = float(score)
    except (ValueError, TypeError):
        return ""
    if val <= 0:
        return ""
    return f"{val:.1f}"


async def generate_anime_view(episode: dict) -> Optional[discord.ui.View]:
    """
    生成動畫推送視圖 (按鈕)

    Args:
        episode: 動畫資訊字典

    Returns:
        discord.ui.View: 生成的 view 物件，失敗則返回 None
    """
    try:
        # 使用共用的 AnimePushView 創建函數
        return create_anime_push_view(episode)
    except Exception as e:
        logger.error(f"生成 view 失敗: {e}")
        return None


async def generate_anime_embed(episode: dict, push_mode: str = "unknown") -> Optional[discord.Embed]:
    """
    生成動畫推送 embed（美化版）

    依序呈現：標題 → 描述（截斷）→ 人氣/評分/集數資訊欄 → 縮圖 → footer。
    依推送模式使用不同主題色，並在 footer 標記時間戳。

    Args:
        episode: 動畫資訊字典
        push_mode: 推送模式 ("排程推送" or "輪詢 (備案模式)")

    Returns:
        discord.Embed: 生成的 embed 物件，失敗則返回 None
    """
    try:
        title = episode.get("title", "") or "未知標題"
        cover = episode.get("cover", "")
        description = _truncate(
            episode.get("description") or episode.get("content") or "",
            _DESCRIPTION_LIMIT,
        )
        volume = episode.get("volume", "")
        logger.debug(f"[PushEmbed] Generating embed for videoSn={episode.get('videoSn', 'unknown')} cover={cover}")

        color = _PUSH_MODE_COLORS.get(push_mode, _DEFAULT_COLOR)

        # 標題若已含集數資訊則直接沿用，否則依需求附加集數資訊
        display_title = title
        if volume:
            vol_text = str(volume).strip()
            # 只在標題中未出現明顯的集數模式時才附加
            episode_pattern = r'第\s*\d+\s*[集話]|\\d+\s*話|Ep\s*\d+'
            if vol_text and not re.search(episode_pattern, title, re.IGNORECASE):
                # 以「·」分隔，避免與標題本身的文字混淆
                display_title = f"{title} · {vol_text}"

        embed = discord.Embed(
            title=display_title,
            description=description or "（無簡介）",
            color=color,
        )

        # 資訊欄：人氣 / 評分 / 推送方式
        popular_text = _format_count(episode.get("popular", 0))
        score_text = _format_score(episode.get("score", 0))

        if popular_text:
            embed.add_field(name="👁️ 觀看次數", value=popular_text, inline=True)
        if score_text:
            embed.add_field(name="⭐ 評分", value=score_text, inline=True)

        embed.add_field(name="📡 推送方式", value=push_mode, inline=True)

        if cover:
            embed.set_image(url=cover)

        embed.set_footer(text="KKGroup 動畫推送")
        embed.timestamp = discord.utils.utcnow()

        return embed
    except Exception as e:
        logger.error(f"生成 embed 失敗: {e}")
        return None