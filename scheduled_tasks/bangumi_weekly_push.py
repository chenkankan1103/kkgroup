#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bangumi 每週熱門排行推送任務
- 取 bangumi 放送表中「正在看人數」（collection.doing）最多的前 20 部當季動畫
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

# 日誌設定
LOG_PATH = BASE_DIR / "bangumi_weekly_push.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _heat_bar(doing: int, peak: int) -> str:
    """畫相對熱度條：以本週冠軍為滿格，一眼看出各名次差多少。

    兩個刻意的選擇：

    1. **相對值而非絕對值** —— 每週的「正在看人數」基準會浮動，固定比例才看得出
       「這週第一名領先多少」。
    2. **平方根刻度而非線性** —— 這份資料是冪次分布（冠軍 16,253 是末位 852 的 19 倍），
       線性刻度下第 6 名之後全部塌成同一格，20 行看起來一模一樣，比不畫還糟。開根號
       壓縮高端的差距，中後段才分得出層次。
       （也刻意「不」再減掉最小值做正規化 —— 那會把尾段的差距再壓一次，等於白開根號。）

    包在 inline code 內也是刻意的：比例字型下 █ 與 ░ 寬度不一，只有等寬字型能讓
    20 行條圖左右對齊成一張圖表。
    """
    if peak <= 0:
        return f"`{'░' * BAR_CELLS}`"
    filled = max(1, round(math.sqrt(doing / peak) * BAR_CELLS))  # 至少一格，避免像 0
    return f"`{'█' * filled}{'░' * (BAR_CELLS - filled)}`"


def build_embed(items: list[dict]) -> discord.Embed:
    """把熱門清單組成單一 Embed。

    排版取捨：Discord 沒有原生表格，一般文字又是比例字型，靠空白對齊欄位在手機上
    必歪。所以改用「行首名次固定寬度 + 等寬熱度條」製造視覺節奏 —— 名次與熱度用眼
    睛掃就好，分數與人數當補充資訊。前三名掛獎牌，其餘用等寬名次籤（寬度與獎牌
    不同，但換來 4～20 名彼此對齊）。
    """
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    peak = max((item.get("doing") or 0) for item in items) if items else 0

    lines = []
    for rank, item in enumerate(items, start=1):
        badge = medals.get(rank, f"`{rank:>2}.`")
        score = item.get("score")
        score_txt = f"**{score}** 分" if score else "— 分"
        doing = item.get("doing") or 0
        lines.append(
            f"{badge} **{item.get('title')}** {_heat_bar(doing, peak)} "
            f"{score_txt} · {doing:,} 人在看"
        )

    desc = "\n".join(lines)
    if len(desc) > EMBED_DESC_LIMIT:
        desc = desc[: EMBED_DESC_LIMIT - 3] + "..."

    embed = discord.Embed(
        title=f"🏆 bangumi 本週熱門 TOP {len(items)}",
        description=desc,
        colour=discord.Color(BANGUMI_PINK),
        timestamp=discord.utils.utcnow(),  # Discord 會自動換算成讀者所在時區
    )
    embed.set_footer(text="資料來源：bangumi（bgm.tv）· 依「正在看人數」排序")
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
    logger.info(f"🔍 正在取得 bangumi 熱門 TOP {TOP_N}...")
    items = await bgm.get_popular(TOP_N)
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
