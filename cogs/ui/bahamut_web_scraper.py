# -*- coding: utf-8 -*-
"""
Bahamut Anime Web Scraper - Standalone Version
專門從巴哈動畫瘋網頁版爬取新番動畫列表的簡化版本

更新: 2026-08-24 使用移動版 API index.php 端點
- 端點: https://api.gamer.com.tw/mobile_app/anime/v3/index.php
- 此端點不受 Cloudflare WAF 保護，回傳完整週表資料
- 包含: videoSn, animeSn, title, cover, week(星期), upTimeHours(時間), volume(集數)
- 大幅減少請求數：從多次網頁爬取降為 1 次 API 呼叫
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class BahamutWebScraper:
    """巴哈動畫瘋網頁版爬取器 - 專注於新番動畫爬取

    使用移動版 API index.php 端點獲取完整週表資料：
    - 端點: https://api.gamer.com.tw/mobile_app/anime/v3/index.php
    - 不受 Cloudflare WAF 保護
    - 回傳完整週表：data.newAnime.date (63筆) + data.newAnimeSchedule (按星期分組)
    """

    def __init__(self):
        # API 端點 headers - 輕量級，僅需基本瀏覽器指紋
        self.api_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        # API 端點
        self.api_url = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"

    async def fetch_new_anime_from_web(self) -> List[Dict]:
        """從移動版 API 獲取新番動畫列表

        Returns:
            List[Dict]: 每個動畫的字典，包含:
                - videoSn (int): 影片序號
                - animeSn (int): 動畫序號
                - title (str): 動畫標題
                - cover (str): 封面圖片URL
                - volume (str): 集數/卷數資訊
        """
        try:
            logger.info("📡 [BahamutWebScraper] 從移動版 API index.php 獲取新番列表...")

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(
                timeout=timeout, headers=self.api_headers
            ) as session:
                async with session.get(self.api_url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"📺 [BahamutWebScraper] API 返回狀態碼: {resp.status}"
                        )
                        return []

                    data = await resp.json()
                    return self._parse_api_response(data)

        except Exception as e:
            logger.error(f"📺 [BahamutWebScraper] API 呼叫異常: {e}")
            return []

    def _parse_api_response(self, data: dict) -> List[Dict]:
        """解析 API 回應的 newAnime.date 陣列"""
        anime_list = []

        try:
            if (
                "data" not in data
                or "newAnime" not in data["data"]
                or "date" not in data["data"]["newAnime"]
            ):
                logger.warning(
                    "⚠️ [BahamutWebScraper] API 回應結構異常，缺少 data.newAnime.date"
                )
                return anime_list

            date_items = data["data"]["newAnime"]["date"]
            logger.info(f"📺 [BahamutWebScraper] API 回傳 {len(date_items)} 筆動畫資料")

            for item in date_items:
                try:
                    video_sn = int(item.get("videoSn", 0))
                    anime_sn = int(item.get("animeSn", 0))
                    title = item.get("title", "").strip()
                    cover = item.get("cover", "")
                    volume = item.get("volume", "")

                    if video_sn and anime_sn and title:
                        anime_list.append(
                            {
                                "videoSn": video_sn,
                                "animeSn": anime_sn,
                                "title": title,
                                "cover": cover,
                                "volume": volume,
                            }
                        )
                    else:
                        logger.debug(
                            f"Skipping item with missing fields: videoSn={video_sn}, animeSn={anime_sn}, title={title}"
                        )

                except (ValueError, KeyError) as e:
                    logger.debug(f"Error parsing item: {e}")
                    continue

        except Exception as e:
            logger.error(f"解析 API 回應失敗: {e}")

        logger.info(
            f"✅ [BahamutWebScraper] 成功解析 {len(anime_list)} 部新番動畫 (含 videoSn/animeSn 映射)"
        )
        return anime_list

    async def fetch_weekly_schedule_from_homepage(self) -> List[Dict]:
        """從移動版 API 爬取完整週表時程

        使用 index.php 的 data.newAnimeSchedule 和 data.newAnime.date
        這些已經包含完整的 week(星期), upTimeHours(時間) 資訊

        Returns:
            List[Dict]: 每個時程條目的字典，包含:
                - anime_sn (int): 動畫序號
                - video_sn (int): 影片序號
                - title (str): 動畫標題
                - day_of_week (int): 星期 (1=一, 2=二, ..., 7=日)
                - scheduled_time (str): 排程時間 (HH:MM)
                - episode (str): 集數資訊
        """
        try:
            logger.info("📡 [BahamutWebScraper] 從移動版 API index.php 獲取完整週表...")

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(
                timeout=timeout, headers=self.api_headers
            ) as session:
                async with session.get(self.api_url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"📅 [BahamutWebScraper] API 返回狀態碼: {resp.status}"
                        )
                        return []

                    data = await resp.json()
                    return self._parse_weekly_schedule(data)

        except Exception as e:
            logger.error(f"📅 [BahamutWebScraper] 爬取週表 API 異常: {e}")
            return []

    def _parse_weekly_schedule(self, data: dict) -> List[Dict]:
        """解析 API 回應的完整週表資料

        結合 newAnimeSchedule (按星期分組) 和 newAnime.date (含封面等額外資訊)
        """
        schedule = []

        try:
            # 1. 先建立 videoSn -> {anime_sn, title, cover, volume} 映射 (從 newAnime.date)
            anime_map = {}
            if (
                "data" in data
                and "newAnime" in data["data"]
                and "date" in data["data"]["newAnime"]
            ):
                for item in data["data"]["newAnime"]["date"]:
                    video_sn = int(item.get("videoSn", 0))
                    anime_sn = int(item.get("animeSn", 0))
                    title = item.get("title", "").strip()
                    cover = item.get("cover", "")
                    volume = item.get("volume", "")
                    if video_sn and anime_sn and title:
                        anime_map[video_sn] = {
                            "anime_sn": anime_sn,
                            "title": title,
                            "cover": cover,
                            "volume": volume,
                        }

            # 2. 解析 newAnimeSchedule (按星期 1-7 分組)
            if "data" in data and "newAnimeSchedule" in data["data"]:
                for day_str, day_items in data["data"]["newAnimeSchedule"].items():
                    try:
                        day_of_week = int(day_str)  # 1=週一, ..., 7=週日
                    except ValueError:
                        continue

                    for item in day_items:
                        try:
                            video_sn = int(item.get("videoSn", 0))
                            schedule_time = item.get("scheduleTime", "")
                            volume_string = item.get("volumeString", "")
                            title_from_schedule = item.get("title", "")

                            if not video_sn or not schedule_time:
                                continue

                            # 從 anime_map 補充詳細資訊
                            detail = anime_map.get(video_sn, {})
                            title = detail.get("title", title_from_schedule)
                            anime_sn = detail.get("anime_sn", 0)
                            cover = detail.get("cover", "")
                            episode = detail.get("volume", volume_string)

                            if anime_sn and title:
                                schedule.append(
                                    {
                                        "anime_sn": anime_sn,
                                        "video_sn": video_sn,
                                        "title": title,
                                        "day_of_week": day_of_week,
                                        "scheduled_time": schedule_time,
                                        "episode": episode,
                                        "cover": cover,
                                    }
                                )
                            else:
                                logger.debug(
                                    f"Missing anime_sn or title for videoSn={video_sn}"
                                )

                        except (ValueError, KeyError) as e:
                            logger.debug(f"Error parsing schedule item: {e}")
                            continue

            logger.info(
                f"✅ [BahamutWebScraper] 從 API 解析到 {len(schedule)} 筆週表時程"
            )
            return schedule

        except Exception as e:
            logger.error(f"解析週表 API 回應失敗: {e}")
            return []


# 便利函數：直接從移動版 API 獲取新番動畫列表
async def fetch_new_anime_from_web() -> List[Dict]:
    """便利函數：從移動版 API 獲取新番動畫列表

    Returns:
        List[Dict]: 每個動畫的字典，包含:
            - videoSn (int): 影片序號
            - animeSn (int): 動畫序號
            - title (str): 動畫標題
            - cover (str): 封面圖片URL
            - volume (str): 集數/卷數資訊
    """
    scraper = BahamutWebScraper()
    return await scraper.fetch_new_anime_from_web()
