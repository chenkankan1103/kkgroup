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
import os
import sys
from datetime import datetime
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

# 日誌設定
LOG_PATH = BASE_DIR / "bangumi_weekly_push.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def build_embed(items: list[dict]) -> discord.Embed:
    """把熱門清單組成單一 Embed（前三名掛獎牌，其餘標數字名次）。"""
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for rank, item in enumerate(items, start=1):
        badge = medals[rank - 1] if rank <= 3 else f"`{rank:>2}.`"
        score = item.get("score")
        score_txt = f"{score} 分" if score else "尚未評分"
        doing = item.get("doing") or 0
        lines.append(
            f"{badge} **{item.get('title')}** · {score_txt} · {doing:,} 人在看"
        )

    desc = "\n".join(lines)
    if len(desc) > EMBED_DESC_LIMIT:
        desc = desc[: EMBED_DESC_LIMIT - 3] + "..."

    embed = discord.Embed(
        title=f"🏆 bangumi 本週熱門 TOP {len(items)}",
        description=desc,
        colour=discord.Color(BANGUMI_PINK),
    )
    embed.set_footer(
        text=f"資料來源：bangumi（bgm.tv）· 依「正在看人數」排序 · {datetime.now():%Y-%m-%d}"
    )
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
