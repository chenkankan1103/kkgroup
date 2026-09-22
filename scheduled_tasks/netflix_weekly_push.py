#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Netflix 台灣每週排行榜推送任務（Tudum 官方榜單）
- 爬取 https://www.netflix.com/tudum/top10/taiwan/tv 官方 TOP 10（Scrapling Fetcher，無需 JS 渲染）
- 以 (videoId, 上榜週數) 指紋比對，僅在官方榜單變更時推送
- 有變更時以靜音（silent）方式推送至指定 Discord 頻道
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Tuple

import discord
from discord.ext import commands

# 設定工作目錄和環境變數
BASE_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = BASE_DIR.parent
ENV_FILE = PROJECT_DIR / ".env"

# 載入環境變數
from dotenv import load_dotenv
load_dotenv(ENV_FILE)

# Discord 機器人 Token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
# Netflix 推送頻道 ID (可透過環境變數設定，預設使用動畫推送頻道)
NETFLIX_CHANNEL_ID = int(os.getenv("NETFLIX_CHANNEL_ID", "1252204317453324333"))  # 預設同動畫頻道

# Tudum 官方排行榜（server-rendered HTML 表格 + Apollo GraphQL 快取，單一請求即可取得全部資料）
TUDUM_TOP10_URL = "https://www.netflix.com/tudum/top10/taiwan/tv"

# 快取設定（比較上次推送資料；VM 為主，不進 Git）
CACHE_FILE = BASE_DIR / "netflix_top10_last.json"

# 日誌設定
LOG_PATH = BASE_DIR / "netflix_weekly_push.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 常數
MAX_EMBEDS_PER_MESSAGE = 10  # Discord 限制：單訊息最多 10 個 Embeds
NETFLIX_RED = 0xE50914  # Netflix 品牌紅


def _scrape_tudum_top10() -> Tuple[List[Dict[str, Any]], str]:
    """同步爬取 Tudum TOP 10（延遲匯入 scrapling，VM 尚未裝依賴時不影響模組載入）

    解析兩份 server-rendered 資料：
    1. HTML 表格：排名、標題、官方縮圖、上榜週數
    2. Apollo GraphQL 快取 JSON：以 weeklyRank 對應 videoId，並取 weekEndDate
    """
    fetcher = None
    try:
        from scrapling import Fetcher
        fetcher = Fetcher()

        page = fetcher.get(TUDUM_TOP10_URL)
        if page.status != 200:
            logger.error(f"Tudum 頁面請求失敗 HTTP {page.status}")
            return [], ""

        html = page.html_content

        # 1) HTML 表格：排名、標題、縮圖、上榜週數
        shows: List[Dict[str, Any]] = []
        for tr in page.css("tbody tr"):
            tds = tr.css("td")
            if len(tds) < 2:
                continue
            title_cell = tds[0]
            rank_el = title_cell.css("span.rank")
            btn_el = title_cell.css("button")
            if not rank_el or not btn_el:
                continue
            title = btn_el[0].text.strip()
            if not title:
                continue
            img_el = title_cell.css("img")
            poster_url = img_el[0].attrib.get("src", "") if img_el else ""
            weeks_txt = tds[1].text.strip()
            weeks = int(weeks_txt) if weeks_txt.isdigit() else 0
            shows.append({
                "rank": int(rank_el[0].text.strip()),
                "title": title,
                "id": None,  # 稍後由 Apollo JSON 對應 videoId
                "poster_url": poster_url,
                "weeks_in_top10": weeks,
            })

        if not shows:
            logger.error("Tudum 表格解析失敗：找不到排行資料列")
            return [], ""

        # 2) Apollo GraphQL 快取：括號配對取出完整 Top10Data 物件再解析
        #    （split 於 '"top10":{' 後，片段開頭即物件內容；配對失敗就略過，避免跨物件誤配）
        week_end = ""
        ids_by_rank: Dict[int, int] = {}
        for frag in html.split('"top10":{'):
            depth, end = 1, -1
            for i, ch in enumerate(frag):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end < 0:
                continue
            try:
                obj = json.loads("{" + frag[:end + 1])
            except (json.JSONDecodeError, ValueError):
                continue
            if obj.get("category") != "SERIES":
                continue  # 僅取影集榜，避免跨物件誤配
            if not week_end and obj.get("weekEndDate"):
                week_end = obj["weekEndDate"]
            if isinstance(obj.get("weeklyRank"), int) and isinstance(obj.get("videoId"), int):
                ids_by_rank[obj["weeklyRank"]] = obj["videoId"]

        for show in shows:
            show["id"] = ids_by_rank.get(show["rank"])
        matched = sum(1 for s in shows if s["id"])
        if matched < len(shows):
            logger.warning(f"videoId 對應不完整（{matched}/{len(shows)}），缺漏項改以標題比對")

        logger.info(
            f"Tudum 爬取成功：{len(shows)} 筆（weekEndDate={week_end or '未知'}，"
            f"videoId 對應 {matched}/{len(shows)}）"
        )
        return shows, week_end
    except Exception as e:
        logger.error(f"Tudum 爬蟲異常: {e}", exc_info=True)
        return [], ""
    finally:
        if fetcher is not None:
            try:
                fetcher.close()
            except Exception:
                pass


async def fetch_tudum_top10() -> Tuple[List[Dict[str, Any]], str]:
    """以執行緒池執行同步爬蟲，避免阻塞事件迴圈"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _scrape_tudum_top10)


def load_last_data() -> Dict[str, Any]:
    """載入上次推送資料（新格式為 dict；舊格式 list 視為無基準，首跑會推送一次）"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                logger.info(
                    f"載入上次推送資料：week_end={data.get('week_end', '?')}，"
                    f"{len(data.get('shows', []))} 筆"
                )
                return data
            logger.info("快取為舊格式（list），視為無基準")
        except Exception as e:
            logger.error(f"載入上次推送資料失敗: {e}")
    else:
        logger.info("尚未有上次推送資料檔案")
    return {}


def save_last_data(week_end: str, shows: List[Dict[str, Any]]) -> None:
    """儲存最後推送資料，供下週變更偵測比對"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"week_end": week_end, "shows": shows}, f, ensure_ascii=False, indent=2)
        logger.info(f"已儲存最後推送資料：week_end={week_end}，{len(shows)} 筆")
    except Exception as e:
        logger.error(f"儲存最後推送資料失敗: {e}")


async def create_show_embeds(
    shows: List[Dict[str, Any]], week_end: str, max_shows: int = 10
) -> List[discord.Embed]:
    """建立排行榜 Embeds：首張為標題卡（帶 weekEndDate），其後每張顯示縮圖 + 排名 + 上榜週數"""
    shows = shows[:max_shows]
    if not shows:
        return [discord.Embed(
            title="無法取得資料",
            description="暫時無法取得 Netflix Tudum 排行榜資料，請稍後再試。",
            colour=discord.Color.dark_grey(),
        )]

    medals = ["🥇", "🥈", "🥉"]
    embeds = []

    # 標題卡：帶出「每週排行」識別與官方榜單週期
    desc = "台灣 Netflix 官方排行榜"
    if week_end:
        desc += f" · 榜單週末 {week_end}"
    header = discord.Embed(
        title=f"🎬 Netflix 每週排行 TOP {max_shows}",
        description=desc,
        colour=discord.Color(NETFLIX_RED),
    )
    header.set_footer(text="資料來源 Netflix Tudum 官方排行榜")
    embeds.append(header)

    for rank, show in enumerate(shows, start=1):
        title = show.get("title", "未知標題")
        poster_url = show.get("poster_url", "")
        weeks = show.get("weeks_in_top10", 0)

        # 排名徽章：前三名用獎牌，其餘用數字
        badge = medals[rank - 1] if rank <= 3 else f"{rank}."
        embed = discord.Embed(
            title=f"{badge} {title}",
            colour=discord.Color(NETFLIX_RED),
        )
        if weeks > 0:
            embed.description = f"🔥 上榜 {weeks} 週"
        if poster_url and poster_url.startswith("http"):
            embed.set_thumbnail(url=poster_url)
        embed.set_footer(text="Netflix 每週排行")
        embeds.append(embed)

    return embeds


async def send_silent_embeds(channel: discord.TextChannel, embeds: List[discord.Embed]) -> None:
    """以靜音模式推送 Embeds（不觸發成員通知）"""
    for batch in [embeds[i:i + MAX_EMBEDS_PER_MESSAGE]
                  for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)]:
        await channel.send(embeds=batch, silent=True)
        logger.info(f"已推送靜音訊息批次，包含 {len(batch)} 個 Embeds")


async def main() -> None:
    """主要執行流程"""
    logger.info("=" * 60)
    logger.info("🚀 開始執行 Netflix 週推送檢查（Tudum 官方榜單）")
    logger.info("=" * 60)

    if not TOKEN:
        logger.error("❌ 缺少 Discord Bot Token，無法執行")
        return

    # 初始化 Bot
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"✅ Bot 已上線: {bot.user}")
        try:
            # 取得頻道
            channel = bot.get_channel(NETFLIX_CHANNEL_ID)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.error(f"❌ 找不到有效文字頻道 ID: {NETFLIX_CHANNEL_ID}")
                await bot.close()
                return

            logger.info(f"📍 將推送至頻道: {channel.name} (ID: {channel.id})")

            # 爬取最新的 Tudum 排行資料
            logger.info("🔍 正在爬取 Netflix Tudum 排行榜資料...")
            shows, week_end = await fetch_tudum_top10()

            if not shows:
                logger.warning("⚠️ 未能取得任何 Tudum 排行資料，本週不推送")
                await bot.close()
                return

            # 載入上次推送資料（舊格式視為無基準 → 首跑推送一次）
            last = load_last_data()
            last_shows = last.get("shows", [])

            # 變更偵測：以 (videoId, 上榜週數) 指紋比較（無 videoId 時退回標題）
            fingerprint = [
                (s.get("id") or s.get("title"), s.get("weeks_in_top10")) for s in shows
            ]
            last_fingerprint = [
                (s.get("id") or s.get("title"), s.get("weeks_in_top10")) for s in last_shows
            ]

            if fingerprint == last_fingerprint:
                logger.info("✅ Tudum 官方榜單無變更，本週不推送")
            else:
                logger.info("🔄 Tudum 官方榜單有變更，準備推送更新")
                embeds = await create_show_embeds(shows, week_end, max_shows=10)
                await send_silent_embeds(channel, embeds)
                save_last_data(week_end, shows)
                logger.info("✅ Tudum 排行榜推送完成")

        except Exception as e:
            logger.error(f"❌ 執行過程中發生錯誤: {e}", exc_info=True)
        finally:
            await bot.close()

    try:
        await asyncio.wait_for(bot.start(TOKEN), timeout=15)
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
