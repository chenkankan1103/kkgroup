#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bangumi 每週近期注目推送任務
- 取官網「動畫 > 近期注目」（/anime/browser/?sort=trends）前 20 部，逐部補上在看人數
- 以單一 Embed 靜音推送至動畫推送頻道
- 排程：每週四 20:00（台灣時間）＝ 週四 12:00 UTC
"""

import asyncio
import logging
import math
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# 設定工作目錄和環境變數
BASE_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = BASE_DIR.parent
ENV_FILE = PROJECT_DIR / ".env"

load_dotenv(ENV_FILE)

# cron 的 sys.path[0] 是 scheduled_tasks/，專案根目錄要自己補上才匯得進 shared.*
sys.path.insert(0, str(PROJECT_DIR))

from shared.utils import bangumi_client as bgm  # noqa: E402

# Discord 機器人 Token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
# bangumi 推送頻道 ID（可透過環境變數覆寫，預設使用動畫推送頻道）
CHANNEL_ID = int(os.getenv("BANGUMI_CHANNEL_ID", "1252204317453324333"))

TOP_N = 20
BANGUMI_PINK = 0xF09199  # bangumi 品牌色
EMBED_DESC_LIMIT = 4096  # Discord Embed description 上限
BAR_CELLS = 12  # 熱度條格數（包在 inline code 內用等寬字型，跨行才對得齊）

# 分數色階：門檻由高到低，取第一個 >= 的色塊，越高分越醒目（紫 > 藍 > 綠 > 黃 > 橘 > 紅）。
#
# 用彩色 emoji 而非 ANSI 色碼是刻意的：ANSI 只作用在 ```ansi code block 內，一般訊息與
# embed 都不吃，而且手機版不支援（會退回沒顏色的等寬字），還會讓標題粗體失效。
# emoji 色塊全平台一致、不吃掉粗體，也不用把整份清單包進 code block。
SCORE_TIERS: tuple[tuple[float, str], ...] = (
    (8.0, "🟪"),
    (7.0, "🟦"),
    (6.0, "🟩"),
    (5.0, "🟨"),
    (4.0, "🟧"),
)
SCORE_CHIP_LOW = "🟥"  # 4 分以下
# 未評分色塊：⬜(U+2B1C) 的預設呈現方式是「文字」而非 emoji，部分平台會把它畫成單欄寬的
# 純文字字符（其他色塊是兩欄寬），那一行的片名起點就會自己歪掉。補一個 VS16 強制走 emoji
# 呈現，才會跟其他色塊同寬。
SCORE_CHIP_NA = "⬜️"
SCORE_LEGEND = f"分數色階：🟪≥8　🟦≥7　🟩≥6　🟨≥5　🟧≥4　🟥<4　{SCORE_CHIP_NA}未評分"

# 日誌設定
LOG_PATH = BASE_DIR / "bangumi_weekly_push.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _heat_bar(doing: int, peak: int) -> str:
    """畫相對熱度條：以榜上最多人在看的那部為滿格，一眼看出各部差多少。

    兩個刻意的選擇：

    1. **相對值而非絕對值** —— 每週的「正在看人數」基準會浮動，固定比例才看得出
       「這週第一名領先多少」。
    2. **平方根刻度而非線性** —— 這份資料是冪次分布（冠軍往往是末位的十幾倍），
       線性刻度下中後段全部塌成同一格，20 行看起來一模一樣，比不畫還糟。開根號
       壓縮高端的差距，中後段才分得出層次。
       （也刻意「不」再減掉最小值做正規化 —— 那會把尾段的差距再壓一次，等於白開根號。）

    滿格的是「這 20 部裡最多人在看」的那部，不一定是第 1 名 —— 榜單排的是近期注目，
    在看人數是另一個維度，第 5 名條比第 1 名長是正常且有意義的。

    包在 inline code 內也是刻意的：比例字型下 █ 與 ░ 寬度不一，只有等寬字型能讓
    20 行條圖左右對齊成一張圖表。
    """
    if peak <= 0:
        return f"`{'░' * BAR_CELLS}`"
    filled = max(1, round(math.sqrt(doing / peak) * BAR_CELLS))  # 至少一格，避免像 0
    return f"`{'█' * filled}{'░' * (BAR_CELLS - filled)}`"


def _score_cell(score) -> str:
    """分數欄：色塊 + 分數，色塊依 SCORE_TIERS 分級。

    這欄排在片名前面，所以**整欄寬度必須固定** —— 它只要寬一格，後面 20 行的片名起點
    就整排位移。分數因此包在 inline code 內：等寬字型每個字符的 advance 都一樣，`8.3`
    與 `-.-` 保證同寬。

    這件事不能靠「挑一個看起來差不多寬的字符」解決 —— Discord 在 Windows / macOS /
    Android / iOS 各用不同字型，比例字型下 `—` 這種字符的寬度從 0.49em 到 1.0em 都有，
    同一份清單在不同裝置上會歪得不一樣。只有等寬字型能跨平台對齊。

    未評分不留白、也不顯示 `0.0`（後者會被誤讀成最低分），而是補成跟 `8.3` 同寬的 `-.-`
    —— bangumi 對還沒有人評分的新番會回 0 或空字串，這種項目每季都有幾部，不能當例外處理。

    分數一律補到小數一位（bangumi 有些項目回 int 7、有些回 float 7.4），這樣 20 行的
    小數點才對得齊。未評分一律當「無分數」處理，不誤標成最低階。

    **先四捨五入再分級**，不是先分級再顯示：7.96 顯示出來是 8.0，色塊就得是 🟪。
    拿原值分級的話會出現「🟦 8.0 分」這種跟圖例自相矛盾的畫面。
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


def build_embed(items: list[dict]) -> discord.Embed:
    """把熱門清單組成單一 Embed。

    排版取捨：Discord 沒有原生表格，一般文字又是比例字型，靠空白對齊欄位在手機上
    必歪。唯一的解法是讓每一行「可變寬的東西全部往後排」，前面只留寬度固定的欄位：

        ` 1.` `████████████` 🟪 `8.3` 分 `  4,000` 人在看 **標題**
        ` 2.` `█████████░░░` 🟦 `7.0` 分 `  8,763` 人在看 **標題**
        ^^^^^  ^^^^^^^^^^^^  ^^^^^^^  ^^^^^^^^  ^^^^^^
        名次籤   熱度條       分數欄   人數欄    片名起點

    名次籤是 3 個 ASCII 字元包在 inline code 裡（等寬，``1`` 與 ``20`` 同寬），熱度條
    固定 BAR_CELLS 格，分數欄固定「色塊 + 三個等寬字元 + 分」（見 _score_cell），人數欄
    右靠齊到這批資料最寬的人數（見下方 doing_width），所以名次、熱度條、分數、人數、
    片名起點這五欄每一行都對得齊。

    片名前那四欄之所以全部塞進 inline code，是因為等寬字型是**唯一能跨平台**保證同寬的
    做法：Discord 在 Windows / macOS / Android / iOS 各用不同字型，靠比例字型「目測等寬」
    的字符，同一份清單在不同裝置會歪得不一樣。

    **所有固定寬度的欄位都排在片名前面**：片名長度不可控，只要它前面還有欄位，那些欄位
    就會被它推歪。片名擺在最後一欄，它自己尾巴參差也無所謂 —— 後面已經沒有東西可以推歪。

    （為什麼不用 embed 欄位排？embed 上限 25 欄是官方硬限制，20 部 × 3 欄的表格要 60 欄，
    塞不下。改成「三個欄位各塞 20 行」也不行 —— inline 欄位並排與欄寬是各平台客戶端自己的
    排版行為，不是 API 規格（官方只把 inline 定義成「是否並排」的提示），桌面版實測大約
    三個一列各佔 1/3，但加縮圖會變兩個一列，手機版更常直接把每個欄位疊成獨立區塊。欄寬
    既不可控又隨裝置變，長片名一折行整排就錯位，反而比現在更亂。）

    **前三名刻意不掛獎牌**：🥇 是 emoji，實測寬度約等於 2.3 個等寬字元，跟 `` 4.`` 對
    不齊；一掛上去，前三行的熱度條就整排往右位移，正是這份清單最該避免的視覺噪音。
    名次本身就是排名資訊，獎牌只是裝飾，拿裝飾換 20 行整齊划得來。

    兩個維度各有各的視覺編碼，刻意不重疊：熱度條（長度）講「多少人看」，色塊（顏色）
    講「好不好看」。所以掃一眼就能看出「這部很多人看但評價普通」這種落差。
    色階說明放在清單最後一行，六階光看顏色猜不出門檻。
    """
    peak = max((item.get("doing") or 0) for item in items) if items else 0
    # 人數欄也排在片名前面，寬度同樣得固定：先量出這批最寬的人數，其餘右靠齊補空白。
    # 補空白一定得包在 inline code 內 —— 一般文字是比例字型，空白寬度不可靠，連續空白還有
    # 被壓縮的風險；只有等寬字型能保證 20 行的片名起點落在同一欄。
    doing_width = max((len(f"{item.get('doing') or 0:,}") for item in items), default=1)

    lines = []
    for rank, item in enumerate(items, start=1):
        doing = item.get("doing") or 0
        lines.append(
            f"`{rank:>2}.` {_heat_bar(doing, peak)} "
            f"{_score_cell(item.get('score'))} `{doing:>{doing_width},}` 人在看 "
            f"**{item.get('title')}**"
        )

    desc = "\n".join(lines)
    reserve = len(SCORE_LEGEND) + 2  # 先扣掉色階說明要佔的位，免得截斷把說明砍掉
    if len(desc) > EMBED_DESC_LIMIT - reserve:
        desc = desc[: EMBED_DESC_LIMIT - reserve - 3] + "..."
    desc += f"\n\n{SCORE_LEGEND}"

    embed = discord.Embed(
        title=f"🏆 bangumi 近期注目 TOP {len(items)}",
        description=desc,
        colour=discord.Color(BANGUMI_PINK),
        timestamp=discord.utils.utcnow(),  # Discord 會自動換算成讀者所在時區
    )
    embed.set_footer(text="資料來源：bangumi（bgm.tv）· 依官網「動畫 › 近期注目」排序")
    return embed


async def main() -> None:
    """主要執行流程"""
    logger.info("=" * 60)
    logger.info("🚀 開始執行 bangumi 每週熱門推送")
    logger.info("=" * 60)

    if not TOKEN:
        logger.error("❌ 缺少 DISCORD_BOT_TOKEN，無法執行")
        return

    # 先抓資料再連 Discord：連線階段才不會被 bot.start() 的 timeout 夾住
    logger.info(f"🔍 正在取得 bangumi 近期注目 TOP {TOP_N}...")
    items = await bgm.get_trending(TOP_N)
    if not items:
        logger.warning("⚠️ 未取得 bangumi 熱門資料，本週不推送")
        return

    logger.info(f"✅ 取得 {len(items)} 筆，第一名：{items[0].get('title')}")
    embed = build_embed(items)

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"✅ Bot 已上線: {bot.user}")
        try:
            channel = bot.get_channel(CHANNEL_ID)
            if not isinstance(channel, discord.TextChannel):
                logger.error(f"❌ 找不到有效文字頻道 ID: {CHANNEL_ID}")
                return
            await channel.send(embed=embed, silent=True)
            logger.info(f"✅ 已推送至 {channel.name}（{channel.id}）")
        except Exception as e:
            logger.error(f"❌ 推送失敗: {e}", exc_info=True)
        finally:
            await bot.close()

    try:
        await asyncio.wait_for(bot.start(TOKEN), timeout=30)
    except asyncio.TimeoutError:
        logger.error("⏱️ Bot 啟動超時")
    except Exception as e:
        logger.error(f"❌ Bot 啟動失敗: {e}")


if __name__ == "__main__":
    try:
        # 設定環境變數 (crontab 需要)
        os.environ.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("收到中斷信號，程式結束")
    except Exception as e:
        logger.error(f"程式執行異常: {e}")
