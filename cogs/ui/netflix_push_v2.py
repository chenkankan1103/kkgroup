"""Netflix 每週排行 Components V2 版面。

對應 scheduled_tasks/netflix_weekly_push.py 的 create_show_embeds()，但不再是
「標題卡 + 10 部劇卡共 11 張 embed 拆兩批送」，而是合成**單一訊息**：
V2 的 Section（文字 + 右側縮圖）正好是排行條目的原生形狀，一個 Container
裝得下全部，頻道裡也只佔一格。

資訊與舊版 1:1：排名徽章（前三名獎牌）、片名、上榜週數、官方縮圖、
榜單週末日期、資料來源，一項不少。

V2 硬限制（動畫卡那邊踩過的）：
- 整則訊息所有 TextDisplay 加總 ≤ 4000 字元 —— 每部片就一行標題 + 一行週數，
  十部加起來不到 500 字，用不到一半
- 元件總數上限 40，且 discord.py 把 **Section 算 3 個**（本體 + 文字 + 縮圖）：
  本版面計數 1 + 1 + 1 + 1 + 10×3 + 1 = 35，所以**不能**再給每部之間加
  Separator（加 3 條就爆，add_item 當場擋）
"""

import logging

import discord
from discord import ui

logger = logging.getLogger(__name__)

# Netflix 品牌紅（與舊版同一個值，cutover 前後卡片色一致）
NETFLIX_RED = 0xE50914

MEDALS = ("🥇", "🥈", "🥉")


def _show_line(rank: int, title: str, weeks: int) -> str:
    """單部劇的文字：排名徽章 + 片名，上榜週數 > 0 才補第二行（與舊版一致）。"""
    badge = MEDALS[rank - 1] if rank <= 3 else f"{rank}."
    text = f"**{badge} {title}**"
    if weeks > 0:
        text += f"\n🔥 上榜 {weeks} 週"
    return text


def generate_netflix_layout(
    shows: list, week_end: str = "", max_shows: int = 10
) -> ui.LayoutView:
    """生成 Netflix 週排行的 V2 版面（單一 LayoutView，含全部 10 部）。

    Args:
        shows: _scrape_tudum_top10() 的結果，每筆
               {rank, title, id, poster_url, weeks_in_top10}
        week_end: Tudum 榜單週末日期字串（可空）
        max_shows: 最多顯示幾部（與舊版同一個上限）

    Returns:
        ui.LayoutView —— 呼叫端 channel.send(view=layout, silent=True) 即可
    """
    shows = shows[:max_shows]

    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color(NETFLIX_RED))

    if not shows:
        # 舊版在拿不到資料時回一張「無法取得資料」卡，行為照搬
        container.add_item(ui.TextDisplay("## 🎬 Netflix 每週排行"))
        container.add_item(
            ui.TextDisplay("暫時無法取得 Netflix Tudum 排行榜資料，請稍後再試。")
        )
        view.add_item(container)
        return view

    container.add_item(ui.TextDisplay(f"## 🎬 Netflix 每週排行 TOP {len(shows)}"))
    desc = "台灣 Netflix 官方排行榜"
    if week_end:
        desc += f" · 榜單週末 {week_end}"
    container.add_item(ui.TextDisplay(desc))
    container.add_item(ui.Separator())

    # 元件計數提醒：discord.py 把 Section 算 3 個（本體+文字+縮圖），10 部 = 30。
    # 本版面 1+1+1+1+30+1 = 35，若再加每部之間的 Separator 就會撞 40 上限
    # （discord.py 在 add_item 當場擋，發送前就會爆 ValueError）。
    for rank, show in enumerate(shows, start=1):
        text = ui.TextDisplay(
            _show_line(rank, show.get("title", "未知標題"), show.get("weeks_in_top10", 0))
        )
        poster_url = show.get("poster_url", "")
        if poster_url and poster_url.startswith("http"):
            container.add_item(
                ui.Section(text, accessory=ui.Thumbnail(poster_url, description="官方縮圖"))
            )
        else:
            # 舊版對沒有縮圖的劇也是只放文字，行為一致
            container.add_item(text)

    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay("-# 資料來源 Netflix Tudum 官方排行榜"))
    view.add_item(container)
    return view
