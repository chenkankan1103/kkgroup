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
_cache: dict = {}
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

    def _get_best_image_url(self, show: dict) -> str:
        """取得最佳可用的圖片URL（優先橫向海報，適用於橫幅顯示）"""
        image_set = show.get("imageSet", {})

        # 按優先順序嘗試不同類型和尺寸的圖片
        # 為橫幅顯示優先使用橫向海報
        candidates = [
            # 橫向海報，寬度優先
            image_set.get("horizontalPoster", {}).get("w1280"),
            image_set.get("horizontalPoster", {}).get("w780"),
            image_set.get("horizontalPoster", {}).get("w480"),
            # 豎向海報（備用）
            image_set.get("verticalPoster", {}).get("w480"),
            image_set.get("verticalPoster", {}).get("w342"),
            # 其他類型
            image_set.get("logo", {}).get("w480"),
            image_set.get("background", {}).get("w1280"),
        ]

        for url in candidates:
            if url and isinstance(url, str) and url.startswith("http"):
                return url
        return ""

    def _get_poster_url(self, show: dict, width: int = 150) -> str:
        """取得適合作為縮圖的海報URL"""
        image_set = show.get("imageSet", {})

        # 嘗試取得指定寬度的橫向海報
        key_w = f"w{width}"
        poster = image_set.get("horizontalPoster", {}).get(key_w)
        if poster and isinstance(poster, str) and poster.startswith("http"):
            return poster

        # 嘗試豎向海報
        poster = image_set.get("verticalPoster", {}).get(key_w)
        if poster and isinstance(poster, str) and poster.startswith("http"):
            return poster

        # 回退到任何可用的海報
        for poster_type in ["horizontalPoster", "verticalPoster"]:
            for size_key, url in image_set.get(poster_type, {}).items():
                if url and isinstance(url, str) and url.startswith("http"):
                    return url

        return ""

    def _translate_genres_to_chinese(self, genres: list[str]) -> list[str]:
        """將英文類型名稱翻譯為中文"""
        genre_mapping = {
            "Action": "動作",
            "Adventure": "冒險",
            "Animation": "動畫",
            "Biography": "傳記",
            "Comedy": "喜劇",
            "Crime": "犯罪",
            "Documentary": "紀錄片",
            "Drama": "戲劇",
            "Family": "家庭",
            "Fantasy": "奇幻",
            "Film-Noir": "黑色電影",
            "History": "歷史",
            "Horror": "恐怖",
            "Music": "音樂",
            "Musical": "歌舞",
            "Mystery": "懸疑",
            "Romance": "浪漫",
            "Sci-Fi": "科幻",
            "Sport": "體育",
            "Thriller": "驚悚",
            "War": "戰爭",
            "Western": "西部",
            # 其他可能的類型
            "Talk-Show": "脫口秀",
            "Reality-TV": "真人秀",
            "Game-Show": "遊戲節目",
            "News": "新聞",
            "Sporting-Event": "體育賽事"
        }

        translated = []
        for genre in genres:
            if genre in genre_mapping:
                translated.append(genre_mapping[genre])
            else:
                # 如果找不到對應的翻譯，保留原文但添加中文標註
                translated.append(f"{genre}（{genre}）")

        return translated

    async def _fetch_top_shows(
        self, country: str = "tw", service: str = "netflix", show_type: str = "movie"
    ) -> tuple[list[dict], str]:
        """呼叫 Streaming Availability API 取得 TOP 10 排行榜

        Returns:
            tuple: (shows_list, actual_country_used)
        """
        import time

        # 檢查快取
        cache_key = f"{country}_{show_type}"
        now = time.time()
        cached_shows = _cache.get(cache_key)
        cached_timestamp = _cache.get(f"{cache_key}_timestamp", 0)
        if cached_shows and (now - cached_timestamp) < CACHE_TTL:
            logger.debug(f"使用快取: {country}/{show_type} (剩餘 {CACHE_TTL - (now - cached_timestamp):.0f}s)")
            return cached_shows, _cache.get(f"{cache_key}_country", country)

        api_key = self._get_api_key()
        # 嘗試使用語言參數以獲得本地化資料（如果 API 支援）
        params = {
            "country": country,
            "service": service,
            "show_type": show_type,
            "language": "zh-TW"  # 嘗試取得繁體中文資料
        }
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
                    cached_data, cached_country = _cache.get(cache_key, ([], country))
                    return cached_data, cached_country
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"API 錯誤 HTTP {resp.status}: {text[:300]}")
                    # 如果是 API 錯誤 HTTP {resp.status}: {text[:300]}")
                    # 如果是 country 不支援，嘗試 fallback 到香港 (僅限首次請求為 TW 時)
                    if "country" in text.lower() and "not supported" in text.lower() and country.lower() == "tw":
                        logger.info(f"Country {country} 不支援，嘗試 fallback 到 HK")
                        return await self._fetch_top_shows("hk", service, show_type)
                    # 如果語言參數不被支援，移除它並重試
                    if "language" in params and resp.status in [400, 422]:
                        logger.info("語言參數不被支援，移除並重試")
                        params.pop("language", None)
                        # 遞迴重試，但避免無限迴圈
                        return await self._fetch_top_shows_without_language(country, service, show_type, api_key, headers)
                    return [], country
                data = await resp.json()

        # 更新快取
        shows = data if isinstance(data, list) else data.get("shows", [])
        _cache[cache_key] = shows
        _cache[f"{cache_key}_timestamp"] = now
        _cache[f"{cache_key}_country"] = country
        return shows, country

    async def _fetch_top_shows_without_language(
        self, country: str, service: str, show_type: str, api_key: str, headers: dict
    ) -> tuple[list[dict], str]:
        """備用方法：不使用語言參數獲取資料"""
        import time

        cache_key = f"{country}_{show_type}"
        now = time.time()
        cached_shows = _cache.get(cache_key)
        cached_timestamp = _cache.get(f"{cache_key}_timestamp", 0)
        if cached_shows and (now - cached_timestamp) < CACHE_TTL:
            return cached_shows, _cache.get(f"{cache_key}_country", country)

        params = {"country": country, "service": service, "show_type": show_type}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{RAPIDAPI_BASE}/shows/top",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 429:
                    logger.warning("API 速率限制 (429)，使用快取資料")
                    cached_data, cached_country = _cache.get(cache_key, ([], country))
                    return cached_data, cached_country
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"API 錯誤 HTTP {resp.status}: {text[:300]}")
                    if "country" in text.lower() and "not supported" in text.lower() and country.lower() == "tw":
                        logger.info(f"Country {country} 不支援，嘗試 fallback 到 HK")
                        return await self._fetch_top_shows("hk", service, show_type)
                    return [], country
                data = await resp.json()

        # 更新快取
        shows = data if isinstance(data, list) else data.get("shows", [])
        _cache[cache_key] = shows
        _cache[f"{cache_key}_timestamp"] = now
        _cache[f"{cache_key}_country"] = country
        return shows, country

    def _build_embed(
        self, shows: list[dict], show_type: str, country_used: str = "tw", page: int = 0
    ) -> discord.Embed:
        """建立 Discord Embed 顯示排行榜"""
        label = "🎬 電影" if show_type == "movie" else "📺 影集"
        color = discord.Color.red() if show_type == "movie" else discord.Color.blue()

        embed = discord.Embed(
            title=f"{label} TOP 10 — 台灣 Netflix",
            description="今日台灣 Netflix 最受歡迎排行",
            color=color,
        )

        if not shows:
            embed.description = "⚠️ 暫時無法取得排行榜資料，請稍後再試。"
            return embed

        # 設定主要橫幅圖片（用第 1 名的最佳橫向海報）
        if shows:
            main_image_url = self._get_best_image_url(shows[0])
            if main_image_url:
                embed.set_image(url=main_image_url)  # 大橫幅圖片

        # 顯示前 10 筆
        for i, show in enumerate(shows[:10], 1):
            title = show.get("title", "???")
            year = show.get("releaseYear") or show.get("firstAirYear") or "?"

            # 翻譯類型名稱為中文
            genres_raw = [g.get("name", "") for g in show.get("genres", [])]
            genres = self._translate_genres_to_chinese(genres_raw)
            genres_str = ", ".join(genres) if genres else "未知類型"

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

            value = f"📅 {year} 年 | ⭐ {rating}/100 | {genres_str}\n{overview}"
            if netflix_link:
                value += f"\n[🔗 在 Netflix 觀看]({netflix_link})"

            embed.add_field(
                name=f"{rank_emoji} {title}",
                value=value,
                inline=False,
            )

            # 為所有項目顯示海報縮圖（在欄位開頭添加圖片）
            poster_url = self._get_poster_url(show, width=120)  # 小縮圖，適應所有項目
            if poster_url:
                # 在當前欄位值開頭添加圖片
                current_value = embed.fields[i-1].value  # i-1 因為索引從 0 開始
                embed.set_field_at(
                    i-1,
                    name=embed.fields[i-1].name,
                    value=f"![海報]({poster_url})\n{current_value}",
                    inline=False,
                )

        # 設定頁腳（由呼叫者負責設定最終內容以處理 fallback 國家）
        embed.set_footer(text="資料來源: Streaming Availability API by Movie of the Night")
        return embed

    @app_commands.command(
        name="netflix_top10",
        description="查看台灣 Netflix 每日 TOP 10 排行榜（因 API 限制實際顯示香港資料）",
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
            shows, country_used = await self._fetch_top_shows("tw", "netflix", st)
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

        # 如果使用了 fallback 地區，在 footer 中說明
        if country_used.lower() != "tw":
            country_names = {
                "hk": "香港 (HK)",
                "jp": "日本 (JP)",
                "kr": "韓國 (KR)",
                "sg": "新加坡 (SG)",
                "my": "馬來西亞 (MY)",
                "ph": "菲律賓 (PH)",
                "th": "泰國 (TH)",
                "vn": "越南 (VN)"
            }
            country_name = country_names.get(country_used.lower(), country_used.upper())
            embed.set_footer(
                text=f"資料來源: Streaming Availability API by Movie of the Night\n"
                     f"※ 因台灣無資料，顯示 {country_name} 排名"
            )
        else:
            embed.set_footer(
                text="資料來源: Streaming Availability API by Movie of the Night"
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """註冊 Cog 到 Bot"""
    await bot.add_cog(NetflixTop10Cog(bot))
    logger.info("✅ NetflixTop10Cog 已載入")