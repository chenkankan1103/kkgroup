"""bangumi 每週近期注目 Components V2 版面。

對應 scheduled_tasks/bangumi_weekly_push.py 的 build_embed()，資訊 1:1：
20 行等寬對齊表格（名次籤、熱度條、分數色塊、人在看、片名）+ 分數色階圖例，
只是從 embed description 搬進 TextDisplay、外層換成 V2 Container。

排版工程的完整理由（等寬字型跨平台對齊、相對熱度條開根號、色階門檻先四捨五入
再分級……）都在 scheduled_tasks/bangumi_weekly_push.py 的原始 docstring 裡，
下面只保留實作。**改表格任何一行之前，先回去讀那份 docstring** —— 這份表格
每一格的寬度都是刻意設計的，憑感覺改很容易在別的裝置上整排歪掉。

三個刻意保留的差異：
- 舊版「前三名不掛獎牌」是為了等寬對齊，V2 版照樣不掛 —— 表格邏輯一行都不動
- 截斷預算從 embed 的 4096 降為 V2 的 4000（TextDisplay 總預算），扣掉
  標題/圖例/頁尾後表格可用約 3600 字 —— 實測 20 行約 1400 字，永遠用不到
- 片名超過 TITLE_MAX_UNITS 顯示寬度就截尾補 …（V2 Container 較窄，長片名
  會折行把表格弄亂；舊 embed 時代描述區寬，沒這問題）
"""

import logging
import math
import time

import discord
from discord import ui

logger = logging.getLogger(__name__)

# bangumi 品牌色（與舊版同一個值）
BANGUMI_PINK = 0xF09199

BAR_CELLS = 12  # 熱度條格數（包在 inline code 內用等寬字型，跨行才對得齊）

# 分數色階：門檻由高到低，取第一個 >= 的色塊，越高分越醒目（紫 > 藍 > 綠 > 黃 > 橘 > 紅）。
# 用彩色 emoji 而非 ANSI 色碼是刻意的：ANSI 只作用在 ```ansi code block 內，一般訊息
# 與 embed 都不吃，手機版還會退回沒顏色的等寬字。emoji 色塊全平台一致、不吃掉粗體。
SCORE_TIERS: tuple[tuple[float, str], ...] = (
    (8.0, "🟪"),
    (7.0, "🟦"),
    (6.0, "🟩"),
    (5.0, "🟨"),
    (4.0, "🟧"),
)
SCORE_CHIP_LOW = "🟥"  # 4 分以下
# 未評分色塊：⬜(U+2B1C) 預設是「文字」而非 emoji，部分平台畫成單欄寬會讓片名起點歪掉；
# 補 VS16 強制走 emoji 呈現才會跟其他色塊同寬。
SCORE_CHIP_NA = "⬜️"
SCORE_LEGEND = f"分數色階：🟪≥8　🟦≥7　🟩≥6　🟨≥5　🟧≥4　🟥<4　{SCORE_CHIP_NA}未評分"

# V2 版面預算：整則訊息所有 TextDisplay 加總 ≤ 4000。
# 標題（約 40）+ 圖例（約 50）+ 頁尾（約 60）+ 時間戳（約 30）+ 安全餘裕 ≈ 400。
V2_TOTAL_LIMIT = 4000
_CHROME_RESERVE = 400

# 片名截斷上限（顯示寬度單位：全形 1、半形 0.5）。V2 Container 比 embed 的
# 描述區窄，超過這個長度的片名會折到第二行，折行後下一行從最左邊開始，
# 視�上就跟下一部的進度條黏在一起（2026-11-05 測試卡實測回饋）。截尾補 …。
TITLE_MAX_UNITS = 16


def _display_title(title: str) -> str:
    """片名截斷：全形字算 1 單位、半形算 0.5，超過 TITLE_MAX_UNITS 砍尾補 …。

    名次/熱度條/分數/人數欄都在片名「前面」，折行推不歪它們 —— 被弄亂的是
    這一行自己往下掉，跟下一部黏在一起。所以寧可截尾，讓每行都是剛好一行。
    """
    units = 0.0
    for i, ch in enumerate(title):
        # U+2E80 起為 CJK 部首/標點/方塊字區，全形算 1 單位；之前的拉丁、
        # 數字、空白算 0.5（‧、& 這類半形符號也落在這邊）
        units += 0.5 if ord(ch) < 0x2E80 else 1.0
        if units > TITLE_MAX_UNITS - 1:  # 留 1 單位給 …
            return title[:i] + "…"
    return title


def _heat_bar(doing: int, peak: int) -> str:
    """畫相對熱度條：以榜上最多人在看的那部為滿格，一眼看出各部差多少。

    相對值而非絕對值（每週基準會浮動，固定比例才看得出第一名領先多少）、
    平方根刻度而非線性（這份資料是冪次分布，線性刻度下中後段全部塌成同一格）。
    滿格的不一定是第 1 名 —— 榜單排的是近期注目，在看人數是另一個維度。
    """
    if peak <= 0:
        return f"`{'░' * BAR_CELLS}`"
    filled = max(1, round(math.sqrt(doing / peak) * BAR_CELLS))  # 至少一格，避免像 0
    return f"`{'█' * filled}{'░' * (BAR_CELLS - filled)}`"


def _score_cell(score) -> str:
    """分數欄：色塊 + 分數，色塊依 SCORE_TIERS 分級。

    整欄寬度必須固定（排在片名前面，寬一格後面 20 行就整排位移），所以包在
    inline code 內。未評分顯示 `-.-`（與 `8.3` 同寬），不顯示 0.0 免得被誤讀成
    最低分。**先四捨五入再分級**：7.96 顯示 8.0，色塊就得是 🟪，否則圖例自相矛盾。
    """
    try:
        value = float(score)
    except (TypeError, ValueError):
        return f"{SCORE_CHIP_NA} `-.-` 分"
    if value <= 0:
        return f"{SCORE_CHIP_NA} `-.-` 分"
    value = round(value, 1)
    for threshold, chip in SCORE_TIERS:
        if value >= threshold:
            return f"{chip} `{value:.1f}` 分"
    return f"{SCORE_CHIP_LOW} `{value:.1f}` 分"


def build_table_lines(items: list) -> str:
    """把熱門清單排成等寬對齊的表格文字。

    每行的欄位順序（可變寬的東西全部往後排，片名永遠最後）：

        ` 1.` `████████████` 🟪 `8.3` 分 `  4,000` 人在看 **標題**

    名次籤 3 個 ASCII 字元、熱度條固定 BAR_CELLS 格、分數欄固定寬、人數欄右靠
    齊到這批最寬的人數 —— 五個欄位的起點每一行都對得齊（等寬字型保證）。
    """
    peak = max((item.get("doing") or 0) for item in items) if items else 0
    doing_width = max((len(f"{item.get('doing') or 0:,}") for item in items), default=1)

    lines = []
    for rank, item in enumerate(items, start=1):
        doing = item.get("doing") or 0
        lines.append(
            f"`{rank:>2}.` {_heat_bar(doing, peak)} "
            f"{_score_cell(item.get('score'))} `{doing:>{doing_width},}` 人在看 "
            f"**{_display_title(item.get('title') or '')}**"
        )
    return "\n".join(lines)


def generate_bangumi_layout(items: list) -> ui.LayoutView:
    """生成 bangumi 近期注目的 V2 版面（單一 LayoutView）。

    Args:
        items: bangumi_client.get_trending() 的結果，每筆
               {id, title, name, name_cn, score, doing}

    Returns:
        ui.LayoutView —— 呼叫端 channel.send(view=layout, silent=True) 即可
    """
    items = items[:20]
    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color(BANGUMI_PINK))

    if not items:
        container.add_item(ui.TextDisplay("## 🏆 bangumi 近期注目"))
        container.add_item(
            ui.TextDisplay("暫時無法取得 bangumi 排行資料，請稍後再試。")
        )
        view.add_item(container)
        return view

    container.add_item(ui.TextDisplay(f"## 🏆 bangumi 近期注目 TOP {len(items)}"))

    table = build_table_lines(items)
    budget = V2_TOTAL_LIMIT - _CHROME_RESERVE
    if len(table) > budget:
        table = table[: budget - 3] + "..."
    container.add_item(ui.TextDisplay(table))

    container.add_item(ui.TextDisplay(SCORE_LEGEND))
    container.add_item(ui.Separator())
    container.add_item(
        ui.TextDisplay(
            "-# 資料來源：bangumi（bgm.tv）・依官網「動畫 › 近期注目」排序"
            f" ・ <t:{int(time.time())}:f>"
        )
    )
    view.add_item(container)
    return view


async def setup(bot):
    """uibot 會把 cogs/ui/ 下每個 .py 當 extension 載入；本檔是版面模組不是 cog，
    補空 setup 讓載入成功，不再每次重啟噴「no setup function」。"""
