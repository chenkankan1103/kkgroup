"""
Netflix 台灣每日排行榜 Cog
使用 Streaming Availability API (RapidAPI 免費方案)
提供 /netflix_top10 指令查詢台灣 Netflix 電影/影集 TOP 10

API 文件: https://docs.movieofthenight.com/resource/shows#get-top-shows
"""
import logging
import os
from typing import Optional, List, Tuple
import asyncio
from io import BytesIO

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

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

    async def _fetch_image_bytes(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        """下載圖片二進位資料，失敗返回 None"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    logger.warning(f"下載圖片失敗 HTTP {resp.status}: {url}")
                    return None
        except Exception as e:
            logger.warning(f"下載圖片異常: {e} - {url}")
            return None

    async def _create_collage_file(self, shows: list[dict]) -> discord.File:
        """非同步製作貼圖並回傳 discord.File"""
        shows = shows[:10]
        if not shows:
            img = Image.new('RGB', (400, 100), color=(30, 30, 30))
            draw = ImageDraw.Draw(img)
            font = ImageFont.load_default()
            draw.text((10, 40), "無法取得海報", fill=(255, 255, 255), font=font)
            buf = BytesIO()
            img.save(buf, format='PNG')
            return discord.File(fp=buf, filename='collage.png')

        # 下載所有海報
        async with aiohttp.ClientSession() as session:
            download_tasks = []
            poster_urls = []
            for show in shows:
                url = self._get_poster_url(show, width=300)
                poster_urls.append(url)
                if url:
                    download_tasks.append(self._fetch_image_bytes(session, url))
                else:
                    download_tasks.append(None)
            # 並行下載（過濾掉 None）
            results = await asyncio.gather(*[t for t in download_tasks if t is not None], return_exceptions=False)

        # 組合結果，保持順序
        images = []
        idx = 0
        for url in poster_urls:
            if url:
                data = results[idx]
                idx += 1
                if data is None:
                    continue
                try:
                    img = Image.open(BytesIO(data)).convert("RGB")
                except Exception:
                    continue
            else:
                # 沒有 URL，跳過
                continue

            # 調整寬度為 300，保持比例
            base_width = 300
            w_percent = base_width / float(img.size[0])
            hsize = int((float(img.size[1]) * w_percent))
            img = img.resize((base_width, hsize), Image.LANCZOS)

            # 在圖片下方繪製標題（透過新增一張底圖）
            title = show.get("title", "未知標題")
            # 限制標題長度
            if len(title) > 20:
                title = title[:17] + "..."
            # 創建底圖
            img_width, img_height = img.size
            extra_height = 30  # 文字區域高度
            new_img = Image.new('RGB', (img_width, img_height + extra_height), color=(0, 0, 0))
            new_img.paste(img, (0, 0))
            draw = ImageDraw.Draw(new_img)
            font = ImageFont.load_default()
            # 計算文字位置使其水平居中
            try:
                text_w, text_h = font.getsize(title)
            except AttributeError:
                left, top, right, bottom = font.getbbox(title)
                text_w = right - left
                text_h = bottom - top
            text_x = (img_width - text_w) / 2
            text_y = img_height + (extra_height - text_h) / 2
            draw.text((text_x, text_y), title, fill=(255, 255, 255), font=font)
            images.append(new_img)

        if not images:
            # 若全部下載失敗
            img = Image.new('RGB', (400, 100), color=(30, 30, 30))
            draw = ImageDraw.Draw(img)
            font = ImageFont.load_default()
            draw.text((10, 40), "無法取得海報", fill=(255, 255, 255), font=font)
            buf = BytesIO()
            img.save(buf, format='PNG')
            return discord.File(fp=buf, filename='collage.png')

        # 垂直堆疊所有圖片，間距 10 px
        spacing = 10
        total_width = max(img.width for img in images)
        total_height = sum(img.height for img in images) + spacing * (len(images) - 1)
        combined = Image.new('RGB', (total_width, total_height), color=(0, 0, 0))
        y_offset = 0
        for img in images:
            # 置中粘貼（若寬度不足則靠左）
            x_offset = (total_width - img.width) // 2
            combined.paste(img, (x_offset, y_offset))
            y_offset += img.height + spacing

        # 輸出到 bytes
        buf = BytesIO()
        combined.save(buf, format='PNG')
        return discord.File(fp=buf, filename='collage.png')

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

        if not shows:
            await interaction.followup.send(
                "⚠️ 暫時無法取得排行榜資料，請稍後再試。", ephemeral=True
            )
            return

        # 建立海報貼圖
        file = await self._create_collage_file(shows)

        # 建立嵌入訊息，僅顯示標題與說明，圖片放在 attachment
        embed = discord.Embed(
            title=f"{'🎬 電影' if st == 'movie' else '📺 影集'} TOP 10 — 台灣 Netflix",
            description="今日台灣 Netflix 最受歡迎排行（海報見下圖）",
            colour=discord.Color.red() if st == "movie" else discord.Color.blue(),
        )
        # 添加簡易文字列表（可選）
        lines = []
        for i, show in enumerate(shows[:10], 1):
            title = show.get("title", "???")
            year = str(show.get("releaseYear") or show.get("firstAirYear") or "?")
            lines.append(f"{i}. {title} ({year})")
        if lines:
            embed.add_field(name="排名列表", value="\n".join(lines), inline=False)

        # 設定頁腳（說明資料來源與 fallback）
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

        # 將圖片附加到嵌入訊息
        embed.set_image(url="attachment://collage.png")

        await interaction.followup.send(embed=embed, file=file)


async def setup(bot: commands.Bot):
    """註冊 Cog 到 Bot"""
    await bot.add_cog(NetflixTop10Cog(bot))
    logger.info("✅ NetflixTop10Cog 已載入")