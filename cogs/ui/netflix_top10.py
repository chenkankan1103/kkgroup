"""
Netflix 台灣熱門排行榜 Cog
使用 JustWatch Popular Titles GraphQL API（無需 API Key、無配額限制）
提供 /netflix_top10 指令查詢台灣 Netflix 熱門影集排行
顯示實際海報圖片（標題已嵌入海報中）
"""
import logging
import time
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import ImageFont

logger = logging.getLogger(__name__)

# JustWatch GraphQL API 設定
JUSTWATCH_GRAPHQL_ENDPOINT = "https://apis.justwatch.com/graphql"
DEFAULT_HEADERS = {
    "User-Agent": "KKGroup-Discord-Bot/1.0 (https://github.com/kkgroup)",
    "Content-Type": "application/json",
}

# 簡單記憶體快取（key: f"{country}_show", value: (data, timestamp)）
_cache: dict[str, tuple] = {}
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
        country: str = "TW",
        page_size: int = 20,
    ) -> list[dict]:
        """
        從 JustWatch GraphQL 取得熱門影集排行

        Returns:
            list[dict]: 每筆包含 title, object_type, id, poster_url, release_year
        """
        cache_key = f"{country}_show"
        now = time.time()

        # 檢查快取
        cached = _cache.get(cache_key)
        if cached and (now - cached[1]) < CACHE_TTL:
            logger.debug(f"JustWatch 快取命中: {cache_key}")
            return cached[0]

        # GraphQL 查詢
        # 用 filter.packages 過濾只抓 Netflix (JustWatch 官方「平台熱門」做法)，
        # 並用 releaseYear.min 限制今年起，排除舊片混入排行。
        graphql_query = """
        query PopularTitles($country: Country!, $first: Int!, $year: Int!) {
          popularTitles(country: $country, first: $first, filter: {
            packages: ["nfx"],
            releaseYear: { min: $year }
          }) {
            edges {
              node {
                __typename
                id
                objectType
                content(country: $country, language: "zh-TW") {
                  title
                  originalReleaseYear
                  posterUrl
                }
              }
            }
          }
        }
        """

        variables = {
            "country": country,
            "first": page_size,
            "year": datetime.now().year,  # 動態帶入今年，未來每日推播仍正確
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
                        # 注意：JustWatch CDN 只接受小寫 profile（如 s166/s332/s718），大寫會回傳 400
                        profile = "s718"  # 標準海報尺寸（小寫）
                        image_format = "jpg"  # JPEG 格式
                        poster_url = f"https://images.justwatch.com{poster_url_template.replace('{profile}', profile).replace('{format}', image_format)}"

                    # 取得實際發行年份（JustWatch 回傳數字）
                    release_year = content.get('originalReleaseYear')
                    release_year = release_year if isinstance(release_year, int) else "N/A"

                    # 只保留影集（熱門榜含電影條目，需過濾掉）
                    if object_type == "SHOW":
                        results.append({
                            "title": title,
                            "object_type": object_type,
                            "id": show_id,
                            "poster_url": poster_url,
                            "release_year": release_year,
                        })

            # 更新快取
            _cache[cache_key] = (results, now)
            logger.info(f"JustWatch GraphQL 成功取得 {len(results)} 筆影集資料")
            return results

        except Exception as e:
            logger.error(f"JustWatch GraphQL 請求異常: {e}")
            return cached[0] if cached else []

    async def _fetch_top_shows(self) -> list[dict]:
        """從 JustWatch GraphQL 取得 Netflix 熱門影集排行

        抓取量放大到 50：熱門榜含電影條目（客戶端過濾掉），較大的候選池
        可確保過濾後仍有足夠影集湊出 TOP 10。
        """
        return await self._fetch_popular_netflix(page_size=50)

    async def _create_show_embeds(self, shows: list[dict], max_shows: int) -> list[discord.Embed]:
        """建立排行榜 Embeds：首張為標題卡，其後每張顯示海報縮圖 + 排名。

        設計：統一使用 Netflix 品牌紅 (#E50914)，標題卡帶出「Netflix 每日排行」
        識別與日期，每部作品一張縮圖卡並標示名次。
        """
        shows = shows[:max_shows]
        if not shows:
            # 沒有資料時的預設 Embed
            return [discord.Embed(
                title="無法取得資料",
                description="暫時無法取得 Netflix 熱門排行榜資料，請稍後再試。",
                colour=discord.Color.dark_grey(),
            )]

        today = datetime.now().strftime("%Y-%m-%d")
        medals = ["🥇", "🥈", "🥉"]
        NETFLIX_RED = 0xE50914  # Netflix 品牌紅
        embeds = []

        # 標題卡：帶出「Netflix 每日排行」識別
        header = discord.Embed(
            title=f"🎬 Netflix 每日排行 TOP {max_shows}",
            description=f"📅 {today} · 台灣 Netflix 熱門排行榜\n每部作品皆附海報縮圖與名次",
            colour=discord.Color(NETFLIX_RED),
        )
        header.set_footer(text="Netflix 每日排行 · 資料來源 JustWatch")
        embeds.append(header)

        for rank, show in enumerate(shows, start=1):
            title = show.get("title", "未知標題")
            object_type = show.get("object_type", "UNKNOWN")
            poster_url = show.get("poster_url", "")
            release_year = show.get("release_year", "N/A")

            # 排名徽章：前三名用獎牌，其餘用數字
            badge = medals[rank - 1] if rank <= 3 else f"{rank}."
            embed = discord.Embed(
                title=f"{badge} #{rank} {title}",
                colour=discord.Color(NETFLIX_RED),
            )
            # 發行年份（若非今年則註明，讓用戶知道是近期片）
            year_note = ""
            if release_year != "N/A":
                is_new = str(release_year) == today[:4]  # 今年新作
                year_note = f"📅 {release_year} 年" + (" · 🔥 今年新作" if is_new else "")
                embed.description = year_note
            embed.set_footer(text="Netflix 每日排行")

            # 如果有海報 URL，設定為縮圖；否則顯示說明（保留年份註記）
            if poster_url and poster_url.startswith("http"):
                embed.set_thumbnail(url=poster_url)
            elif year_note:
                embed.description = f"{year_note}\n海報圖片載入失敗"
            else:
                embed.description = "海報圖片載入失敗"

            embeds.append(embed)

        return embeds

    async def _send_silent(self, channel, embeds: list[discord.Embed]):
        """以靜音模式推播排行榜（不觸發通知聲，供未來每日排程使用）。

        與動畫推送一致使用 silent=True：等同 Discord 的「靜音通知」，
        不會讓頻道成員手機/桌面跳出通知聲。
        """
        for batch in [embeds[i:i + MAX_EMBEDS_PER_MESSAGE]
                      for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)]:
            await channel.send(embeds=batch, silent=True)

    @app_commands.command(
        name="netflix_top10",
        description="查看台灣 Netflix 熱門影集 TOP 10（顯示實際海報縮圖）",
    )
    async def netflix_top10(
        self,
        interaction: discord.Interaction,
    ):
        """斜線指令：/netflix_top10 - 顯示影集前 10 名"""
        await interaction.response.defer()  # 先 defer 避免 3 秒超時

        max_shows = 10

        try:
            shows = await self._fetch_top_shows()
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


async def setup(bot: commands.Bot):
    """註冊 Cog 到 Bot"""
    await bot.add_cog(NetflixTop10Cog(bot))
    logger.info("✅ NetflixTop10Cog 已載入 (JustWatch GraphQL API)")