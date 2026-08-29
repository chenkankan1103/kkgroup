"""
Netflix 台灣熱門排行榜 Cog
使用 JustWatch Popular Titles GraphQL API（無需 API Key、無配額限制）
提供 /netflix_top10 指令查詢台灣 Netflix 電影/影集熱門排行
顯示實際海報圖片（標題已嵌入海報中）
"""
import logging
import asyncio
import time
from typing import Optional, List, Dict
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# JustWatch GraphQL API 設定
JUSTWATCH_GRAPHQL_ENDPOINT = "https://apis.justwatch.com/graphql"
DEFAULT_HEADERS = {
    "User-Agent": "KKGroup-Discord-Bot/1.0 (https://github.com/kkgroup)",
    "Content-Type": "application/json",
}

# 簡單記憶體快取（key: f"{country}_{content_type}", value: (data, timestamp)）
_cache: Dict[str, tuple] = {}
CACHE_TTL = 7200  # 2 小時（熱門榜變動不大）

# 常數
MAX_EMBEDS_PER_MESSAGE = 10  # Discord 限制：單訊息最多 10 個 Embeds
POSTER_WIDTH = 400  # 海報顯示寬度（Discord 會自動調整高度保持比例）
POSTER_HEIGHT_ESTIMATE = 600  # 預估海報高度（用於計算快取大小）


class NetflixTop10Cog(commands.Cog):
    """台灣 Netflix 熱門排行榜（資料來源：JustWatch GraphQL）"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 載入中文字體（用於備用顯示，不過海報圖片本身已有標題）
        self._font = None
        font_path = Path(__file__).parent.parent.parent / "fonts" / "NotoSansCJKtc-Regular.otf"
        if font_path.exists():
            try:
                self._font = ImageFont.truetype(str(font_path), 18)
                logger.debug(f"載入字體成功: {font_path}")
            except Exception as e:
                logger.warning(f"載入字體失敗，將使用預設字體: {e}")
        else:
            logger.warning(f"字體檔案不存在: {font_path}")

    def _get_font(self) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """取得字體，失敗時回退到預設字體"""
        return self._font or ImageFont.load_default()

    async def _fetch_popular_netflix(
        self,
        content_type: str,  # "movie" or "show"
        country: str = "TW",
        page_size: int = 20,
    ) -> List[Dict]:
        """
        從 JustWatch GraphQL 取得熱門排行

        Returns:
            list[dict]: 每筆包含 title, object_type (SHOW/MOVIE), id, poster_url
        """
        cache_key = f"{country}_{content_type}"
        now = time.time()

        # 檢查快取
        cached = _cache.get(cache_key)
        if cached and (now - cached[1]) < CACHE_TTL:
            logger.debug(f"JustWatch 快取命中: {cache_key}")
            return cached[0]

        # GraphQL 查詢
        graphql_query = """
        query PopularTitles($country: Country!, $first: Int!) {
          popularTitles(country: $country, first: $first) {
            edges {
              node {
                __typename
                id
                objectType
                content(country: $country, language: "zh-TW") {
                  title
                  posterUrl
                }
              }
            }
          }
        }
        """

        variables = {
            "country": country,
            "first": page_size
        }

        try:
            async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
                async with session.post(
                    JUSTWATCH_GRAPHQL_ENDPOINT,
                    json={"query": graphql_query, "variables": variables},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 429:
                        logger.warning("JustWatch 429 速率限制，回傳快取或空列表")
                        return cached[0] if cached else []

                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"JustWatch GraphQL API 錯誤 HTTP {resp.status}: {text[:300]}")
                        return cached[0] if cached else []

                    data = await resp.json()

            # 解析 GraphQL 回應
            results = []
            if 'data' in data and 'popularTitles' in data['data']:
                popular_data = data['data']['popularTitles']
                edges = popular_data.get('edges', [])

                for edge in edges:
                    node = edge.get('node', {})
                    content = node.get('content', {})

                    # 只取得我們需要的欄位
                    title = content.get('title', '未知標題')
                    object_type = node.get('objectType', '').upper()  # SHOW or MOVIE
                    show_id = node.get('id', '')
                    poster_url_template = content.get('posterUrl', '')

                    # 構建實際海報 URL
                    poster_url = ""
                    if poster_url_template and '{profile}' in poster_url_template and '{format}' in poster_url_template:
                        # 使用常見的海報尺寸和格式
                        profile = "S166"  # 標準海報尺寸
                        image_format = "jpg"  # JPEG 格式
                        poster_url = f"https://images.justwatch.com{poster_url_template.replace('{profile}', profile).replace('{format}', image_format)}"

                    # 根據物件類型過濾
                    target_type = "SHOW" if content_type == "show" else "MOVIE"
                    if object_type == target_type:
                        results.append({
                            "title": title,
                            "object_type": object_type,
                            "id": show_id,
                            "poster_url": poster_url,
                            "content_type": content_type,  # 為了向後相容
                            "release_year": "N/A",  # 暫時無法取得，保持向後相容
                        })

            # 更新快取
            _cache[cache_key] = (results, now)
            logger.info(f"JustWatch GraphQL 成功取得 {len(results)} 筆 {content_type} 資料")
            return results

        except Exception as e:
            logger.error(f"JustWatch GraphQL 請求異常: {e}")
            return cached[0] if cached else []

    async def _fetch_top_shows(self, show_type: str) -> list[dict]:
        """從 JustWatch GraphQL 取得 Netflix 熱門排行"""
        return await self._fetch_popular_netflix(show_type)

    async def _create_show_embeds(self, shows: list[dict], max_shows: int) -> list[discord.Embed]:
        """建立顯示節目的 Embeds（每個 Embed 顯示一張海報）"""
        shows = shows[:max_shows]
        if not shows:
            # 沒有資料時的預設 Embed
            embed = discord.Embed(
                title="無法取得資料",
                description="暫時無法取得 Netflix 熱門排行榜資料，請稍後再試。",
                colour=discord.Color.dark_grey()
            )
            return [embed]

        embeds = []
        for show in shows:
            title = show.get("title", "未知標題")
            object_type = show.get("object_type", "UNKNOWN")
            poster_url = show.get("poster_url", "")

            # 建立 Embed
            embed = discord.Embed(
                title=f"[{object_type}] {title}",
                colour=discord.Color.blue() if object_type == "SHOW" else discord.Color.red(),
            )

            # 如果有海報 URL，設定為 Embed 的圖片
            if poster_url and poster_url.startswith("http"):
                embed.set_image(url=poster_url)
            else:
                # 沒有海報時顯示說明
                embed.description = "海報圖片載入失敗"

            embeds.append(embed)

        return embeds

    @app_commands.command(
        name="netflix_top10",
        description="查看台灣 Netflix 熱門電影/影集 TOP 16（顯示實際海報圖片）",
    )
    @app_commands.describe(
        show_type="選擇電影或影集排行榜（預設：影集）",
    )
    @app_commands.choices(
        show_type=[
            app_commands.Choice(name="🎬 電影", value="movie"),
            app_commands.Choice(name="📺 影集", value="series"),
        ]
    )
    async def netflix_top10(
        self,
        interaction: discord.Interaction,
        show_type: app_commands.Choice[str] = None,
    ):
        """斜線指令：/netflix_top10 [電影|影集] - 預設顯示影集前 16 名"""
        await interaction.response.defer()  # 先 defer 避免 3 秒超時

        st = show_type.value if show_type else "series"
        label = "電影" if st == "movie" else "影集"
        max_shows = 10 if st == "movie" else 16  # 電影 TOP 10、影集 TOP 16

        try:
            shows = await self._fetch_top_shows(st)
        except Exception as e:
            logger.error(f"取得 Netflix 排行榜失敗: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 取得排行榜時發生錯誤，請稍後再試。", ephemeral=True
            )
            return

        if not shows:
            await interaction.followup.send(
                "⚠️ 暫時無法取得排行榜資料，請稍後再試。", ephemeral=True
            )
            return

        # 建立 Embeds
        embeds = await self._create_show_embeds(shows, max_shows)

        # 分批發送（每批最多 MAX_EMBEDS_PER_MESSAGE 個 Embeds）
        batches = [embeds[i:i + MAX_EMBEDS_PER_MESSAGE]
                  for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)]

        # 發送第一批（使用 followup.send）
        first_batch = batches[0]
        await interaction.followup.send(embeds=first_batch)

        # 發送剩餘的批次（每批為新訊息）
        for batch in batches[1:]:
            await interaction.followup.send(embeds=batch)

        # 發送統計資訊
        shows_count = len([s for s in shows if s.get('object_type') == 'SHOW'])
        movies_count = len([s for s in shows if s.get('object_type') == 'MOVIE'])
        stats_embed = discord.Embed(
            title="📊 排行榜統計",
            description=f"共取得 {len(shows)} 筆資料\n"
                       f"📺 影集: {shows_count} 筆\n"
                       f"🎬 電影: {movies_count} 筆\n"
                       f"📋 顯示前 {max_shows} 名 {'影集' if st == 'series' else '電影'}",
            colour=discord.Color.blue()
        )
        await interaction.followup.send(embed=stats_embed)


async def setup(bot: commands.Bot):
    """註冊 Cog 到 Bot"""
    await bot.add_cog(NetflixTop10Cog(bot))
    logger.info("✅ NetflixTop10Cog 已載入 (JustWatch GraphQL API)")
