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
import re
from typing import Dict, List, Optional
import aiohttp
import logging

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
            async with aiohttp.ClientSession(timeout=timeout, headers=self.api_headers) as session:
                async with session.get(self.api_url) as resp:
                    if resp.status != 200:
                        logger.warning(f"📺 [BahamutWebScraper] API 返回狀態碼: {resp.status}")
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
            if 'data' not in data or 'newAnime' not in data['data'] or 'date' not in data['data']['newAnime']:
                logger.warning("⚠️ [BahamutWebScraper] API 回應結構異常，缺少 data.newAnime.date")
                return anime_list

            date_items = data['data']['newAnime']['date']
            logger.info(f"📺 [BahamutWebScraper] API 回傳 {len(date_items)} 筆動畫資料")

            for item in date_items:
                try:
                    video_sn = int(item.get('videoSn', 0))
                    anime_sn = int(item.get('animeSn', 0))
                    title = item.get('title', '').strip()
                    cover = item.get('cover', '')
                    volume = item.get('volume', '')

                    if video_sn and anime_sn and title:
                        anime_list.append({
                            "videoSn": video_sn,
                            "animeSn": anime_sn,
                            "title": title,
                            "cover": cover,
                            "volume": volume
                        })
                    else:
                        logger.debug(f"Skipping item with missing fields: videoSn={video_sn}, animeSn={anime_sn}, title={title}")

                except (ValueError, KeyError) as e:
                    logger.debug(f"Error parsing item: {e}")
                    continue

        except Exception as e:
            logger.error(f"解析 API 回應失敗: {e}")

        logger.info(f"✅ [BahamutWebScraper] 成功解析 {len(anime_list)} 部新番動畫 (含 videoSn/ansible 映射)")
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
            async with aiohttp.ClientSession(timeout=timeout, headers=self.api_headers) as session:
                async with session.get(self.api_url) as resp:
                    if resp.status != 200:
                        logger.warning(f"📅 [BahamutWebScraper] API 返回狀態碼: {resp.status}")
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
            if 'data' in data and 'newAnime' in data['data'] and 'date' in data['data']['newAnime']:
                for item in data['data']['newAnime']['date']:
                    video_sn = int(item.get('videoSn', 0))
                    anime_sn = int(item.get('animeSn', 0))
                    title = item.get('title', '').strip()
                    cover = item.get('cover', '')
                    volume = item.get('volume', '')
                    if video_sn and anime_sn and title:
                        anime_map[video_sn] = {
                            'anime_sn': anime_sn,
                            'title': title,
                            'cover': cover,
                            'volume': volume
                        }

            # 2. 解析 newAnimeSchedule (按星期 1-7 分組)
            if 'data' in data and 'newAnimeSchedule' in data['data']:
                for day_str, day_items in data['data']['newAnimeSchedule'].items():
                    try:
                        day_of_week = int(day_str)  # 1=週一, ..., 7=週日
                    except ValueError:
                        continue

                    for item in day_items:
                        try:
                            video_sn = int(item.get('videoSn', 0))
                            schedule_time = item.get('scheduleTime', '')
                            volume_string = item.get('volumeString', '')
                            title_from_schedule = item.get('title', '')

                            if not video_sn or not schedule_time:
                                continue

                            # 從 anime_map 補充詳細資訊
                            detail = anime_map.get(video_sn, {})
                            title = detail.get('title', title_from_schedule)
                            anime_sn = detail.get('anime_sn', 0)
                            cover = detail.get('cover', '')
                            episode = detail.get('volume', volume_string)

                            if anime_sn and title:
                                schedule.append({
                                    'anime_sn': anime_sn,
                                    'video_sn': video_sn,
                                    'title': title,
                                    'day_of_week': day_of_week,
                                    'scheduled_time': schedule_time,
                                    'episode': episode,
                                    'cover': cover
                                })
                            else:
                                logger.debug(f"Missing anime_sn or title for videoSn={video_sn}")

                        except (ValueError, KeyError) as e:
                            logger.debug(f"Error parsing schedule item: {e}")
                            continue

            logger.info(f"✅ [BahamutWebScraper] 從 API 解析到 {len(schedule)} 筆週表時程")
            return schedule

        except Exception as e:
            logger.error(f"解析週表 API 回應失敗: {e}")
            return []

    async def fetch_new_anime_from_web(self) -> List[Dict]:
        """從網頁版爬取新番動畫列表

        Returns:
            List[Dict]: 每個動畫的字典，包含:
                - videoSn (int): 影片序號
                - animeSn (int): 動畫序號
                - title (str): 動畫標題
                - cover (str): 封面圖片URL
                - volume (str): 集數/卷數資訊
        """
        try:
            # 嘗試不同的網頁 URL 作為新番列表來源
            for url in self.urls_to_try:
                anime_list = await self._try_scrape_url(url)
                if anime_list:  # 如果成功獲取到動畫列表，就使用它
                    logger.info(f"📺 [BahamutWebScraper] 成功從 {url} 爬取到 {len(anime_list)} 部新番")
                    return anime_list

            # 如果所有 URL 都失敗，回傳空列表
            logger.warning("📺 [BahamutWebScraper] 所有網頁嘗試均失敗")
            return []

        except Exception as e:
            logger.error(f"📺 [BahamutWebScraper] 爬取異常: {e}")
            return []

    async def _try_scrape_url(self, url: str) -> List[Dict]:
        """嘗試從特定 URL 爬取新番動畫"""
        try:
            timeout = aiohttp.ClientTimeout(total=15)

            async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.debug(f"網頁 {url} 返回狀態碼: {resp.status}")
                        return []

                    html_text = await resp.text()
                    return await self._parse_anime_list_html(html_text, url, session)

        except Exception as e:
            logger.debug(f"網頁 {url} 爬取失敗: {e}")
            return []

    async def _parse_anime_list_html(self, html_text: str, source_url: str, session: aiohttp.ClientSession) -> List[Dict]:
        """解析HTML以提取動畫條目"""
        anime_list = []

        try:
            # 尋找所有 animeRef.php 鏈接
            anime_ref_pattern = r"href\s*=\s*['\"]([^'\"]*animeRef\.php\?sn=(\d+)[^'\"]*)['\"]"
            anime_ref_matches = list(re.finditer(anime_ref_pattern, html_text, re.IGNORECASE))
            logger.debug(f"Found {len(anime_ref_matches)} animeRef.php links in {source_url}")

            # 處理前10個動畫（避免過多請求）
            for match in anime_ref_matches[:10]:
                try:
                    full_url = match.group(1)
                    anime_sn_str = match.group(2)
                    anime_sn = int(anime_sn_str)

                    # 構建完整URL
                    if full_url.startswith('http'):
                        detail_url = full_url
                    elif full_url.startswith('/'):
                        detail_url = f"https://ani.gamer.com.tw{full_url}"
                    else:
                        detail_url = f"https://ani.gamer.com.tw/{full_url}"

                    # 獲取詳細頁面
                    anime_info = await self._get_anime_detail_info(session, detail_url, anime_sn)
                    if anime_info:
                        anime_list.append(anime_info)
                        logger.debug(f"Added anime: {anime_info['title']} (SN: {anime_sn}, VideoSN: {anime_info['videoSn']})")

                except (ValueError, IndexError, Exception) as e:
                    logger.debug(f"Error processing animeRef match: {e}")
                    continue

            # 如果從列表頁沒找到足夠資料，嘗試直接從列表頁解析
            if len(anime_list) < 3:
                logger.debug(f"Detail page scraping found {len(anime_list)} anime, trying list page parsing")
                list_page_anime = self._parse_from_list_page(html_text)
                anime_list.extend(list_page_anime)

        except Exception as e:
            logger.error(f"解析HTML時發生錯誤: {e}")

        return anime_list

    async def _get_anime_detail_info(self, session: aiohttp.ClientSession, detail_url: str, anime_sn: int) -> Optional[Dict]:
        """獲取單個動畫的詳細資訊"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)

            async with session.get(detail_url, timeout=timeout, headers=self.headers) as resp:
                if resp.status != 200:
                    logger.debug(f"Detail page {detail_url} 返回狀態碼: {resp.status}")
                    return None

                html_text = await resp.text()
                return self._extract_anime_info_from_detail(html_text, anime_sn)

        except Exception as e:
            logger.debug(f"獲取動畫詳細資訊失敗 {detail_url}: {e}")
            return None

    def _extract_anime_info_from_detail(self, html_text: str, anime_sn: int) -> Optional[Dict]:
        """從動畫詳細頁面HTML中提取資訊"""
        try:
            # 尋找 videoSn
            video_sn = self._extract_video_sn_from_html(html_text)
            if not video_sn:
                logger.debug(f"Could not find videoSn for anime SN {anime_sn}")
                return None

            # 尋找標題
            title = self._extract_title_from_html(html_text)
            if not title:
                title = f"未知標題_{anime_sn}"

            # 尋找封面圖
            cover_url = self._extract_cover_from_html(html_text)

            # 尋找卷數/集數
            volume = self._extract_volume_from_html(html_text)

            return {
                "videoSn": video_sn,
                "animeSn": anime_sn,
                "title": title,
                "cover": cover_url or "",
                "volume": volume or ""
            }

        except Exception as e:
            logger.debug(f"從詳細頁面提取動畫資訊失敗: {e}")
            return None

    def _extract_video_sn_from_html(self, html_text: str) -> Optional[int]:
        """從HTML片段中提取 videoSn"""
        try:
            # 尋找 animeVideo.php?sn=XXXX 鏈接
            video_pattern = r'animeVideo\.php\?sn=(\d+)'
            video_matches = re.findall(video_pattern, html_text, re.IGNORECASE)

            if video_matches:
                # 取第一個找到的 videoSn
                return int(video_matches[0])

            # 另外可能是 data-video-sn 屬性
            data_pattern = r'data-video-sn\s*=\s*["\'](\d+)["\']'
            data_matches = re.findall(data_pattern, html_text, re.IGNORECASE)
            if data_matches:
                return int(data_matches[0])

            # 另一種可能：在JS中或其他屬性
            js_pattern = r'["\']video_sn["\']\s*[:=]\s*["\']?(\d+)'
            js_matches = re.findall(js_pattern, html_text, re.IGNORECASE)
            if js_matches:
                return int(js_matches[0])

        except (ValueError, IndexError):
            pass
        return None

    def _extract_cover_from_html(self, html_text: str) -> Optional[str]:
        """從HTML片段中提取封面圖 URL"""
        try:
            # 尋找 img 標籤，優先找看起來像封面的圖片
            img_patterns = [
                r'<img\s[^>]*src\s*=\s*["\']([^"\']*\/cover[^"\']*)["\'][^>]*>',  # 包含 cover 的 URL
                r'<img\s[^>]*src\s*=\s*["\']([^"\']*\.(jpg|jpeg|png|webp))["\'][^>]*>',  # 圖片檔案
                r'<img\s[^>]*data-src\s*=\s*["\']([^"\']*)["\'][^>]*>',  # lazy loading
                r'<img\s[^>]*src\s*=\s*["\']([^"\']*)["\'][^>]*>',  # 任意圖片
            ]

            for pattern in img_patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                if matches:
                    # 取第一個匹配的 URL
                    src = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    # 確保是完整 URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://ani.gamer.com.tw' + src
                    elif not src.startswith('http'):
                        src = 'https://ani.gamer.com.tw/' + src
                    return src

        except Exception:
            pass
        return None

    def _extract_title_from_html(self, html_text: str) -> Optional[str]:
        """從HTML片段中提取標題"""
        try:
            # 首先嘗試從 og:title meta tag 取得標題（最可靠）
            og_title_pattern = r'<meta[^>]*property\s*=\s*["\']og:title["\'][^>]*content\s*=\s*["\']([^"\']*)["\']'
            og_match = re.search(og_title_pattern, html_text, re.IGNORECASE)
            if og_match:
                title = og_match.group(1).strip()
                if title and len(title) > 1:
                    return title

            # 接著嘗試從一般 title tag 取得並清理網站後綴
            title_tag_pattern = r'<title[^>]*>([^<]+)</title>'
            title_match = re.search(title_tag_pattern, html_text, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
                # 移除常見的網站後綴
                suffixes = [
                    " - 巴哈姆特動畫瘋",
                    " | 巴哈姆特",
                    " - 巴哈姆特"
                ]
                for suffix in suffixes:
                    if title.endswith(suffix):
                        title = title[:-len(suffix)]
                        break
                if title and len(title) > 1:
                    return title

            # 嘗試找特定的動畫名稱容器（如anime_name class內的h1）
            anime_name_patterns = [
                r'<[^>]*class\s*=\s*["\'][^"\']*anime-name[^"\']*["\'][^>]*>[^<]*<h[1-6][^>]*>([^<]+)</h[1-6]>',
                r'<h[1-6][^>]*class\s*=\s*["\'][^"\']*anime-name[^"\']*["\'][^>]*>([^<]+)</h[1-6]>',
                r'<[^>]*class\s*=\s*["\'][^"\']*title[^"\']*["\'][^>]*>[^<]*<h[1-6][^>]*>([^<]+)</h[1-6]>',  # 更具體的title class
            ]

            for pattern in anime_name_patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                if matches:
                    # 取第一個非空的匹配
                    for match in matches:
                        title = match.strip()
                        if title and len(title) > 1:
                            return title

            # 嘗試找看起來像標題的文字
            # 常見標題位置：在特定class中的文字
            title_patterns = [
                r'<[^>]*class\s*=\s*["\'][^"\']*anime-name[^"\']*["\'][^>]*>([^<]+)</[^>]*>',  # anime-name class
                r'<[^>]*class\s*=\s*["\'][^"\']*name[^"\']*["\'][^>]*>([^<]+)</[^>]*>',  # name class
                r'<h[1-6][^>]*>([^<]+)</h[1-6]>',  # 標題標籤
                r'<[^>]*class\s*=\s*["\"][^"\']*subject[^"\']*["\"][^>]*>([^<]+)</[^>]*>',  # subject class
                r'<[^>]*class\s*=\s*["\'][^"\']*ht[^"\']*["\"][^>]*>([^<]+)</[^>]*>',  # ht class (可能是標題)
                r'<[^>]*class\s*=\s*["\'][^"\']*fangkuang[^"\']*["\"][^>]*>([^<]+)</[^>]*>',  # 方框
                r'<[^>]*class\s*=\s*["\'][^"\']*title[^"\']*["\'][^>]*>([^<]+)</[^>]*>',  # title class (放在最後，因為太通用)
            ]

            for pattern in title_patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                if matches:
                    # 取第一個非空的匹配
                    for match in matches:
                        title = match.strip()
                        if title and len(title) > 1:
                            return title

            # 如果上面都沒找到，嘗試從 alt 屬性中取得
            alt_pattern = r'<img\s[^>]*alt\s*=\s*["\']([^"\']*)["\'][^>]*>'
            alt_matches = re.findall(alt_pattern, html_text, re.IGNORECASE)
            if alt_matches:
                for alt in alt_matches:
                    if alt.strip() and len(alt.strip()) > 1:
                        return alt.strip()

        except Exception:
            pass
        return None

    def _extract_volume_from_html(self, html_text: str) -> Optional[str]:
        """從HTML片段中提取卷數/集數"""
        try:
            # 常見的集數顯示模式
            volume_patterns = [
                r'第\s*(\d+)\s*話',  # 第1話
                r'Vol\.?\s*(\d+)',  # Vol.1 或 Vol1
                r'EP\.?\s*(\d+)',   # EP.1 或 EP1
                r'(\d+)\s*話',      # 1話
                r'(\d+)\s*集',      # 1集
                r'NEW',             # 新番標記
                r'更新中',          # 更新中
            ]

            for pattern in volume_patterns:
                match = re.search(pattern, html_text, re.IGNORECASE)
                if match:
                    return match.group(0)  # 返回完整匹配，如 "第1話"

            # 額外檢查：有時會直接在文字中出現
            text_patterns = [
                r'第\s*(\d+)\s*話\s*[^\d]',  # 第1話後面接非數字
                r'Vol\.?\s*(\d+)\s*[^\d]',   # Vol.1後面接非數字
            ]

            for pattern in text_patterns:
                match = re.search(pattern, html_text, re.IGNORECASE)
                if match:
                    # 返回完整匹配（包含後面的文字，但我們只想要數字部分）
                    full_match = match.group(0)
                    # 提取數字部分
                    num_match = re.search(r'\d+', full_match)
                    if num_match:
                        return f"{num_match.group()}話" if '話' in full_match else f"Vol.{num_match.group()}"

        except Exception:
            pass
        return None

    def _parse_from_list_page(self, html_text: str) -> List[Dict]:
        """從列表頁直接解析動畫資訊（當無法進入詳細頁時的備用方案）"""
        anime_list = []

        try:
            # 尋找所有 animeRef.php 鏈接
            anime_ref_pattern = r"href\s*=\s*['\"]([^'\"]*animeRef\.php\?sn=(\d+)[^'\"]*)['\"]"
            anime_ref_matches = list(re.finditer(anime_ref_pattern, html_text, re.IGNORECASE))
            logger.debug(f"Found {len(anime_ref_matches)} animeRef.php links for list page parsing")

            for match in anime_ref_matches[:10]:  # 處理前10個
                try:
                    anime_sn_str = match.group(2)
                    anime_sn = int(anime_sn_str)

                    # 在鏈接周圍尋找資訊
                    link_start = match.start()
                    link_end = match.end()

                    # 擴大搜索範圍
                    context_start = max(0, link_start - 2000)
                    context_end = min(len(html_text), link_end + 2000)
                    context = html_text[context_start:context_end]

                    # 從上下文中提取資訊
                    title = self._extract_title_from_html(context)
                    volume = self._extract_volume_from_html(context)

                    # 尋找圖片URL
                    cover_url = None
                    img_matches = re.findall(r'<img\s[^>]*src\s*=\s*["\']([^"\']*)["\'][^>]*>', context, re.IGNORECASE)
                    if img_matches:
                        # 取第一個看起來像圖片的URL
                        for src in img_matches:
                            if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                                cover_url = src
                                break
                        if not cover_url and img_matches:
                            cover_url = img_matches[0]

                    # 確保是完整 URL
                    if cover_url:
                        if cover_url.startswith('//'):
                            cover_url = 'https:' + cover_url
                        elif cover_url.startswith('/'):
                            cover_url = 'https://ani.gamer.com.tw' + cover_url
                        elif not cover_url.startswith('http'):
                            cover_url = 'https://ani.gamer.com.tw/' + cover_url

                    # 雖然沒有 videoSn，但我們仍然加入（videoSn 為 None 會在後續被過濾掉）
                    if title:  # 至少需要標題
                        anime_list.append({
                            "videoSn": None,  # 將在詳細頁面中獲取
                            "animeSn": anime_sn,
                            "title": title,
                            "cover": cover_url or "",
                            "volume": volume or ""
                        })

                except (ValueError, IndexError) as e:
                    logger.debug(f"Error processing animeRef match for list page: {e}")
                    continue

        except Exception as e:
            logger.error(f"從列表頁解析時發生錯誤: {e}")

        return anime_list


    async def fetch_weekly_schedule_from_homepage(self) -> List[Dict]:
        """從首頁爬取完整週表時程

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
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
                async with session.get("https://ani.gamer.com.tw/") as resp:
                    if resp.status != 200:
                        logger.warning(f"首頁返回狀態碼: {resp.status}")
                        return []

                    html_text = await resp.text()
                    return self._parse_homepage_schedule(html_text)

        except Exception as e:
            logger.error(f"爬取首頁週表失敗: {e}")
            return []

    def _parse_homepage_schedule(self, html_text: str) -> List[Dict]:
        """解析首頁 HTML 獲取週表時程

        使用 newanime-date-area 區塊，包含完整資料：
        - data-animesn: 動畫序號
        - data-date-code: 日期代碼 (1=週一, 2=週二, ..., 7=週日)
        - animeVideo.php?sn=VIDEO_SN
        - p.anime-name: 動畫標題
        - span.anime-hours: 時間
        - p: 集數資訊 (格式: 蝚?N?)

        Args:
            html_text: 首頁 HTML 內容

        Returns:
            List[Dict]: 時程條目列表
        """
        schedule = []

        try:
            # Find all newanime-date-area blocks (handles both single and double quotes)
            # Pattern: <div class='newanime-date-area ...' data-animesn='ANIME_SN' data-date-code='DATE_CODE'>
            day_pattern = r"<div class=[\'\"']newanime-date-area[^\'\"']*[\'\"'] data-animesn=[\'\"'](\d+)[\'\"'] data-date-code=[\'\"'](\d+)[\'\"']([\s\S]*?)</div>\s*</div>\s*</div>"
            matches = re.findall(day_pattern, html_text, re.DOTALL)
            logger.debug(f"Found {len(matches)} newanime-date-area blocks on homepage")

            # dateCode mapping: 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun
            for anime_sn_str, date_code_str, content in matches:
                try:
                    anime_sn = int(anime_sn_str)
                    day_of_week = int(date_code_str)

                    # Extract video_sn from animeVideo.php?sn=VIDEO_SN
                    video_match = re.search(r"animeVideo\.php\?sn=(\d+)", content)
                    if not video_match:
                        logger.debug(f"anime_sn={anime_sn}: No video_sn found")
                        continue
                    video_sn = int(video_match.group(1))

                    # Extract name from <p class='anime-name'>NAME</p>
                    name_match = re.search(r"<p class=[\'\"']anime-name[\'\"']>([^<]+)</p>", content)
                    if not name_match:
                        logger.debug(f"anime_sn={anime_sn}: No name found")
                        continue
                    title = name_match.group(1).strip()

                    # Extract time from <span class='anime-hours'>HH:MM</span>
                    time_match = re.search(r"<span class=[\'\"']anime-hours[\'\"']>(\d+:\d+)</span>", content)
                    if not time_match:
                        logger.debug(f"anime_sn={anime_sn}: No time found")
                        continue
                    scheduled_time = time_match.group(1)

                    # Extract episode from <p>蝚?N?</p> or other patterns
                    episode = ""
                    ep_match = re.search(r"<p>蝚\?(\d+)\?</p>", content)
                    if ep_match:
                        episode = f"第{ep_match.group(1)}集"
                    else:
                        # Fallback: look for other episode patterns
                        ep_match2 = re.search(r"第(\d+)集", content)
                        if ep_match2:
                            episode = f"第{ep_match2.group(1)}集"

                    schedule.append({
                        'anime_sn': anime_sn,
                        'video_sn': video_sn,
                        'title': title,
                        'day_of_week': day_of_week,
                        'scheduled_time': scheduled_time,
                        'episode': episode
                    })
                    logger.debug(f"Parsed: {title} (anime_sn={anime_sn}, video_sn={video_sn}, day={day_of_week}, time={scheduled_time}, ep={episode})")

                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parsing newanime-date-area entry: {e}")
                    continue

            logger.info(f"📅 [BahamutWebScraper] 從首頁解析到 {len(schedule)} 筆週表時程")
            return schedule

        except Exception as e:
            logger.error(f"解析首頁週表失敗: {e}")
            return []


# 便利函數：直接從網頁版爬取新番動畫列表
async def fetch_new_anime_from_web() -> List[Dict]:
    """便利函數：從網頁版爬取新番動畫列表

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