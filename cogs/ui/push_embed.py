"""
動畫推送 Embed 格式模組
專門負責生成動畫推送的 Embed 格式和 View (按鈕)
"""

import logging
import discord
import re
from typing import Optional, Dict, Any
from shared.utils.embed_views import (
    COMMENTS_FIELD_NAME,
    CUMULATIVE_FIELD_NAME,
    EPISODE_FIELD_NAME,
    REWARD_HINT,
    create_anime_push_view,
    format_vote_stats,
)

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


def _format_comments(comments: list, limit: int = 3, max_len: int = 60) -> str:
    """把留言列表格式化為 embed 欄位文字（每則一行、匿名呈現）。

    embed 欄位值上限 1024 字元，故同時限制則數與單則長度；留言寫入時雖已
    限制 200 字，但多則並列時仍會過長，這裡再截一次才讀得下去。
    """
    lines = []
    for item in comments[:limit]:
        text = _truncate(item.get("comment", ""), max_len)
        if text:
            lines.append(f"> {text} — 匿名")
    return "\n".join(lines)


def _format_score(score) -> str:
    """將評分格式化為小數點後一位，無效值回傳空字串。"""
    try:
        val = float(score)
    except (ValueError, TypeError):
        return ""
    if val <= 0:
        return ""
    return f"{val:.1f}"


async def generate_anime_view(episode: dict, db=None) -> Optional[discord.ui.View]:
    """
    生成動畫推送視圖 (按鈕)

    Args:
        episode: 動畫資訊字典
        db: AnimePushDB 實例，用於記錄投票（可選，不傳則投票無法寫入）

    Returns:
        discord.ui.View: 生成的 view 物件，失敗則返回 None
    """
    try:
        # 使用共用的 AnimePushView 創建函數（務必轉傳 db，否則投票無法寫入資料庫）
        return create_anime_push_view(episode, db_adapter=db)
    except Exception as e:
        logger.error(f"生成 view 失敗: {e}")
        return None


async def generate_anime_embed(episode: dict, push_mode: str = "unknown", db: Optional["AnimePushDB"] = None) -> Optional[discord.Embed]:
    """
    生成動畫推送 embed（美化版）

    依序呈現：標題 → 描述（截斷）→ 人氣/評分/集數資訊欄 → 投票統計 → 縮圖 → footer。
    依推送模式使用不同主題色，並在 footer 標記時間戳。

    Args:
        episode: 動畫資訊字典
        push_mode: 推送模式 ("排程推送" or "輪詢 (備案模式)")
        db: AnimePushDB 實例，用於獲取投票統計（可選）

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
            # 原本寫成 r'第\\s*...'（raw string 內多一層跳脫），實際比對的是「反斜線 + s」，
            # 永遠不會命中，volume 一律被附加成「標題 · 第N集」。補上 detail title 的
            # 「[N]」形式，兩條推送路徑的標題才會一致
            episode_pattern = r"第\s*\d+\s*[集話]|\d+\s*話|Ep\s*\d+|\[\s*\d+\s*\]"
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

        # Calculate total views and average views if we have multiple episodes data
        total_views = episode.get("total_views", 0)
        episode_count = episode.get("episode_count", 1)
        if total_views > 0 and episode_count > 0:
            avg_views = total_views // episode_count  # Integer division for whole number
            popular_text = f"{_format_count(total_views)} (平均 {_format_count(avg_views)}/集)"
        elif popular_text:
            popular_text = f"{popular_text} 總觀看"

        if popular_text:
            embed.add_field(name="👁️ 觀看次數", value=popular_text, inline=True)
        if score_text:
            embed.add_field(name="⭐ 評分", value=score_text, inline=True)

        embed.add_field(name="📡 推送方式", value=push_mode, inline=True)

        # 投票統計欄位：本集（單則 embed）+ 全系列累計（跨集數以 animeSn 加總）
        if db and episode.get("videoSn"):
            try:
                video_sn = int(episode.get("videoSn"))
                embed.add_field(
                    name=EPISODE_FIELD_NAME,
                    value=format_vote_stats(db.get_vote_stats(video_sn)),
                    inline=False,
                )

                # 全系列累計：讓新一集的 embed 顯示先前所有集數的加總，而非從 0 開始。
                # animeSn 是系列層級的鍵（videoSn 則是單集），故累計須以 animeSn 聚合。
                anime_sn = episode.get("animeSn")
                if anime_sn and hasattr(db, "get_vote_stats_by_anime"):
                    embed.add_field(
                        name=CUMULATIVE_FIELD_NAME,
                        value=format_vote_stats(
                            db.get_vote_stats_by_anime(int(anime_sn))
                        ),
                        inline=False,
                    )

                # 觀眾留言：同樣以 animeSn 跨集數取最新幾則，讓新一集的推播
                # 也看得到先前集數的留言（與「全系列累計」同一套語意）。
                # 沒有留言就不加欄位，不留一個空殼欄位佔版面。
                if anime_sn and hasattr(db, "get_comments_by_anime"):
                    comments_text = _format_comments(
                        db.get_comments_by_anime(int(anime_sn))
                    )
                    if comments_text:
                        embed.add_field(
                            name=COMMENTS_FIELD_NAME, value=comments_text, inline=False
                        )
            except Exception as e:
                logger.error(f"❌ 獲取投票統計失敗 videoSn={episode.get('videoSn')}: {e}")

        # 獎勵提示：放 description 尾端而非獨立欄位，免得 embed 欄位過多
        # 把統計與留言擠出視野
        if embed.description:
            embed.description = f"{embed.description}\n\n{REWARD_HINT}"

        if cover:
            embed.set_image(url=cover)

        embed.set_footer(text="KKGroup 動畫推送")
        embed.timestamp = discord.utils.utcnow()

        return embed
    except Exception as e:
        logger.error(f"生成 embed 失敗: {e}")
        return None