"""
Netflix 台灣每日排行榜 Cog
使用 Streaming Availability API (RapidAPI 免費方案)
提供 /netflix_top10 指令查詢台灣 Netflix 電影/影集 TOP 10

API 文件: https://docs.movieofthenight.com/resource/shows#get-top-shows
"""
import logging
import os
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# API 設定
RAPIDAPI_BASE = "https://streaming-availability.p.rapidapi.com"
RAPIDAPI_HOST = "streaming-availability.p.rapidapi.com"

# 快取：避免短時間內重複請求（免費方案每月 500 次）
_cache: dict = {"movies": None, "series": None, "timestamp": 0}
CACHE_TTL = 3600  # 快取 1 小時


class NetflixTop10Cog(commands.Cog):
    """台灣 Netflix 每日 TOP 10 排行榜"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._api_key: Optional[str] = os.getenv("STREAMING_AVAILABILITY_API_KEY")

    def _get_api_key(self) -> str:
        """取得 API key，優先從環境變數讀取"""
        if self._api_key:
            return self._api_key
        # 每次重新讀取（支援運行時更新）
        self._api_key = os.getenv("STREAMING_AVAILABILITY_API_KEY")
        if not self._api_key:
            raise ValueError(
                "未設定 STREAMING_AVAILABILITY_API_KEY 環境變數。\n"
                "請到 https://rapidapi.com 註冊免費帳號並訂閱 Streaming Availability API。"
            )
        return self._api_key

    async def _fetch_top_shows(
        self, country: str = "tw", service: str = "netflix", show_type: str = "movie"
    ) -> list[dict]:
        """呼叫 Streaming Availability API 取得 TOP 10 排行榜"""
        import time

        # 檢查快取
        cache_key = show_type
        now = time.time()
        if _cache[cache_key] and (now - _cache["timestamp"]) < CACHE_TTL:
            logger.debug(f"使用快取: {show_type} (剩餘 {CACHE_TTL - (now - _cache['timestamp']):.0f}s)")
            return _cache[cache_key]

        api_key = self._get_api_key()
        params = {"country": country, "service": service, "show_type": show_type}
        headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{RAPIDAPI_BASE}/shows/top",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 429:
                    logger.warning("API 速率限制 (429)，使用快取資料")
                    return _cache.get(cache_key) or []
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"API 錯誤 HTTP {resp.status}: {text[:300]}")
                    return []
                data = await resp.json()

        # 更新快取
        _cache[cache_key] = data if isinstance(data, list) else data.get("shows", [])
        _cache["timestamp"] = now
        return _cache[cache_key]

    def _build_embed(
        self, shows: list[dict], show_type: str, page: int = 0
    ) -> discord.Embed:
        """建立 Discord Embed 顯示排行榜"""
        label = "🎬 電影" if show_type == "movie" else "📺 影集"
        color = discord.Color.red() if show_type == "movie" else discord.Color.blue()

        embed = discord.Embed(
            title=f"{label} TOP 10 — Netflix Taiwan",
            description="今日台灣 Netflix 最受歡迎排行",
            color=color,
        )

        if not shows:
            embed.description = "⚠️ 暫時無法取得排行榜資料，請稍後再試。"
            return embed

        # 顯示前 10 筆
        for i, show in enumerate(shows[:10], 1):
            title = show.get("title", "???")
            year = show.get("releaseYear") or show.get("firstAirYear") or "?"
            genres = ", ".join(
                g.get("name", "") for g in show.get("genres", [])
            ) or "N/A"
            rating = show.get("rating", "?")
            overview = (show.get("overview") or "無簡介")[:100]

            # 取得 Netflix 連結
            streaming = show.get("streamingOptions", {}).get("tw", {})
            netflix_link = ""
            if "netflix" in streaming:
                for opt in streaming["netflix"]:
                    netflix_link = opt.get("link", "")
                    if netflix_link:
                        break

            # 排名 emoji
            rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"#{i}")

            value = f"📅 {year}  |  ⭐ {rating}/100  |  {genres}\n{overview}"
            if netflix_link:
                value += f"\n[🔗 在 Netflix 觀看]({netflix_link})"

            embed.add_field(
                name=f"{rank_emoji} {title}",
                value=value,
                inline=False,
            )

        # 設定海報圖片（用第 1 名的海報）
        if shows:
            image_set = shows[0].get("imageSet", {})
            poster = image_set.get("verticalPoster", {}).get("w480", "")
            if not poster:
                poster = image_set.get("horizontalPoster", {}).get("w480", "")
            if poster:
                embed.set_thumbnail(url=poster)

        embed.set_footer(
            text="資料來源: Streaming Availability API by Movie of the Night"
        )
        return embed

    @app_commands.command(
        name="netflix_top10",
        description="查看台灣 Netflix 每日 TOP 10 排行榜",
    )
    @app_commands.describe(
        show_type="選擇電影或影集排行榜（預設：電影）",
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
        """斜線指令：/netflix_top10 [電影|影集]"""
        await interaction.response.defer()  # 先 defer 避免 3 秒超時

        st = show_type.value if show_type else "movie"
        label = "電影" if st == "movie" else "影集"

        try:
            shows = await self._fetch_top_shows("tw", "netflix", st)
        except ValueError as e:
            await interaction.followup.send(
                f"❌ {e}", ephemeral=True
            )
            return
        except Exception as e:
            logger.error(f"取得 Netflix 排行榜失敗: {e}")
            await interaction.followup.send(
                "❌ 取得排行榜時發生錯誤，請稍後再試。", ephemeral=True
            )
            return

        embed = self._build_embed(shows, st)
        await interaction.followup.send(embed=embed)


async def setup_netflix_top10(bot: commands.Bot):
    """註冊 Cog 到 Bot"""
    await bot.add_cog(NetflixTop10Cog(bot))
    logger.info("✅ NetflixTop10Cog 已載入")