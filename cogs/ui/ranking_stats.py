# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 排名和統計系統

負責排名和統計功能：
- 本週動畫投票統計（每週日晚上 11 點發送）
- 觀看人數排名趨勢圖生成（使用 QuickChart）
- episode 統計同步（每 6 小時從 API 更新觀看數）
- 每日直接檢查（備用機制，每天上午 9 點執行）

此模組與 schedule_tracker.py 和 push_core.py 合作，提供完整的動畫追蹤功能：
- push_core.py: 核心資料庫操作和投票系統
- schedule_tracker.py: 週表排程和時刻檢查
- ranking_stats.py: 排名統計和報告生成
"""

import logging
import json
import random
import aiohttp
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import discord
from discord.ext import tasks, commands
from .push_core import AnimeDatabase, ANIME_CHANNEL_ID, ANIME_DB_PATH, TW_TZ, API_ENDPOINT, API_TIMEOUT

logger = logging.getLogger(__name__)


class RankingStats:
    """排名和統計管理器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = None
        self.last_weekly_stats_sent = None  # 上次發送週統計的日期
        self.MAX_NEW_EPISODES_PER_PUSH = 20  # 單次推送最多處理的新集數量，避免阻塞事件循環
        self._last_fallback_check = None
        self._last_schedule_fallback = None

        # 每日檢查相關變數（備用機制）
        self.last_daily_check_date = None

    def set_dependencies(self, bot, db):
        """設置依賴"""
        # Set the bot attribute
        self.bot = bot
        # Set the db attribute
        self.db = db

    def is_reward_already_given(self, user_id: int, message_id: int, reward_type: str) -> bool:
        """檢查獎勵是否已發放 - 委託給 AnimeDatabase"""
        return self.db.is_reward_already_given(user_id, message_id, reward_type)

    def record_reward(self, user_id: int, message_id: int, reward_type: str, amount: int) -> bool:
        """記錄獎勵發放 - 委託給 AnimeDatabase"""
        return self.db.record_reward(user_id, message_id, reward_type, amount)

    # ==================== 投票系統方法（委託給 AnimeDatabase） ====================

    def record_vote(self, video_sn: int, anime_sn: int, message_id: int, vote_type: str, comment: str = None, user_hash: str = None) -> bool:
        """記錄投票 - 委託給 AnimeDatabase"""
        return self.db.record_vote(video_sn, anime_sn, message_id, vote_type, comment, user_hash)

    def get_vote_stats(self, message_id: int) -> Dict:
        """獲取投票統計 - 委託給 AnimeDatabase"""
        return self.db.get_vote_stats(message_id)

    def get_vote_comments(self, message_id: int, limit: int = 5) -> List[str]:
        """獲取評論 - 委託給 AnimeDatabase"""
        return self.db.get_vote_comments(message_id, limit)

    def get_weekly_vote_stats(self) -> Dict[int, Dict]:
        """獲取週投票統計 - 委託給 AnimeDatabase"""
        return self.db.get_weekly_vote_stats()

    async def get_quickchart_short_url(self, chart_config: Dict) -> Optional[str]:
        """
        使用 QuickChart /chart/create API 生成短網址

        Args:
            chart_config: QuickChart 圖表配置字典

        Returns:
            短網址或 None
        """
        try:
            # 添加常用參數
            chart_config_with_params = {
                **chart_config,
                "bkg": "white",
                "w": 950 if chart_config.get("type") == "line" and len(chart_config.get("data", {}).get("datasets", [])) > 1 else 850,
                "h": 400 if chart_config.get("type") == "line" and len(chart_config.get("data", {}).get("datasets", [])) > 1 else 350
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://quickchart.io/chart/create",
                    json=chart_config_with_params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        short_url = data.get("url")
                        if short_url:
                            logger.info(f"📊 [get_quickchart_short_url] 成功生成短網址: {short_url[:50]}...")
                            return short_url
                        else:
                            logger.warning(f"⚠️ [get_quickchart_short_url] API 無返回 url: {data}")
                            return None
                    else:
                        text = await resp.text()
                        logger.warning(f"⚠️ [get_quickchart_short_url] API 返回 {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.warning(f"⚠️ [get_quickchart_short_url] 生成短網址失敗: {e}")
            return None

    async def fetch_all_recent_anime_from_api(self) -> Optional[List[Dict]]:
        """
        從 Bahamut API 獲取所有最近的動畫集（不限於今天的）
        用於排行榜顯示

        Returns:
            所有最近的集列表，或 None 如果失敗
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    API_ENDPOINT,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    }
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ API returned status {resp.status}")
                        return None

                    data = await resp.json()
                    new_anime = data.get("data", {}).get("newAnime", {})

                    # 組合所有日期的動畫
                    all_episodes = []
                    if isinstance(new_anime, dict):
                        # 'date' 鍵包含按日期分組的集
                        all_episodes.extend(new_anime.get("date", []))
                        # 'popular' 鍵包含最受歡迎的集
                        all_episodes.extend(new_anime.get("popular", []))

                    # 去重（按 videoSn）
                    seen = set()
                    unique_episodes = []
                    for ep in all_episodes:
                        if isinstance(ep, dict):
                            video_sn = ep.get("videoSn")
                            if video_sn and video_sn not in seen:
                                seen.add(video_sn)
                                unique_episodes.append(ep)

                    logger.info(f"🔍 [fetch_all_recent_anime_from_api] 獲得 {len(unique_episodes)} 部最近的動畫")
                    return unique_episodes
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
            return None

    def _extract_view_count_from_episode(self, episode: dict, default: int = 0) -> int:
        """
        直接從 index API (v3/index.php) 的 episode 物件中提取觀看/人氣數，
        不需額外調用 video.php。

        Bahamut API 的 `newAnime.popular` 陣列中的 episode 物件可能包含
        多個潛在的觀看數字段：popular, viewCount, counter, views, view_counter 等。

        Args:
            episode: index API 返回的單個 episode 字典
            default: 找不到時返回的預設值

        Returns:
            提取到的觀看數（int），否則返回 default
        """
        view_candidates = [
            "popular", "viewCount", "counter", "views",
            "view_counter", "page_views", "click", "playCount",
        ]
        for field in view_candidates:
            raw = episode.get(field)
            if raw is not None:
                try:
                    val = int(str(raw).replace(',', '').replace(',', ''))
                    if val > 0:
                        logger.info(f"📺 [_extract_view_count_from_episode] 從 field='{field}' 提取到觀看數: {val}")
                        return val
                    else:
                        logger.debug(f"📺 [_extract_view_count_from_episode] field='{field}' 值為 0，繼續嘗試其他字段")
                except (ValueError, TypeError):
                    continue

        # 若 episode 物件沒有直接的觀看數，但 structure 中有 highlightTag/meta 也可嘗試
        highlight = episode.get("highlightTag") or {}
        if isinstance(highlight, dict):
            for field in ["counter", "views", "popular"]:
                raw = highlight.get(field)
                if raw is not None:
                    try:
                        val = int(str(raw).replace(',', ''))
                        if val > 0:
                            logger.info(f"📺 [_extract_view_count_from_episode] 從 highlightTag.{field} 提取到觀看數: {val}")
                            return val
                    except (ValueError, TypeError):
                        continue

        logger.debug(f"📺 [_extract_view_count_from_episode] 無法從 episode(videoSn={episode.get('videoSn')}) 提取觀看數")
        return default

    def _get_weekday_name(self, weekday_num: int) -> str:
        """將 weekday數字轉換為中文名稱"""
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        if 1 <= weekday_num <= 7:
            return weekdays[weekday_num - 1]
        else:
            return "未知"

    async def _sync_episode_stats_from_api(self):
        """
        定時從 Bahamut index API 獲取最新的動畫列表，
        記錄 per-episode 統計數據到 episode_statistics 表，
        確保週排行有足夠的歷史數據。

        此方法獨立於新集通知流程，定期執行以累積數據。
        """
        try:
            episodes = await self.fetch_all_recent_anime_from_api()
            if not episodes:
                logger.warning("⚠️ [_sync_episode_stats_from_api] 無法獲取動畫數據")
                return

            recorded = 0
            for ep in episodes:
                video_sn = ep.get("videoSn")
                anime_sn = ep.get("animeSn")
                if not video_sn or not anime_sn:
                    continue

                # 提取觀看數
                views = self._extract_view_count_from_episode(ep)

                # 如果 index API 沒有觀看數，從 video.php 補充
                if views <= 0:
                    try:
                        details = await self.fetch_anime_details_from_api(video_sn)
                        if details:
                            views = details.get("popular", 0)
                    except Exception as e:
                        logger.warning(f"⚠️ [_sync_episode_stats_from_api] videoSn={video_sn} 詳情獲取失敗: {e}")
                        continue

                anime_name = ep.get("title", f"Anime #{anime_sn}")
                episode_num = ep.get("volume", "")

                # 記錄統計（INSERT OR REPLACE，以 videoSn 為主鍵）
                self.db.record_episode_stats(
                    video_sn=video_sn,
                    anime_sn=anime_sn,
                    episode_num=episode_num,
                    views=views,
                    score=0  # index API 不包含評分，預設 0
                )

                # 也快取 anime details（名稱等）
                if anime_sn:
                    existing = self.db.get_anime_details(int(anime_sn))
                    if not existing:
                        self.db.cache_anime_details(
                            int(anime_sn),
                            anime_name,
                            "",
                            [],
                            views,
                            0
                        )

                recorded += 1
                await asyncio.sleep(2.0)  # 避免限流：限制 ~30 req/min

            logger.info(f"✅ [_sync_episode_stats_from_api] 完成，記錄了 {recorded}/{len(episodes)} 筆統計數據")

        except Exception as e:
            logger.error(f"❌ [_sync_episode_stats_from_api] 執行失敗: {e}", exc_info=True)

    async def fetch_anime_web_details(self, anime_sn: str) -> Dict[str, Optional[object]]:
        """
        從動畫瘋網頁版的 animeRef 詳情頁抓取作品分類和簡介。
        """
        if not anime_sn:
            return {}

        detail_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    detail_url,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ Web detail page returned status {resp.status} for animeSn={anime_sn}")
                        return {}
                    html_text = await resp.text()

            genres = []
            summary = None

            tag_section = re.search(r'<span class="title">作品分類</span>\s*<ul class="tag-list">(.*?)</ul>', html_text, re.S)
            if tag_section:
                genres = re.findall(r'<li class="tag">(.*?)</li>', tag_section.group(1), re.S)
                genres = [html.unescape(tag.strip()) for tag in genres if tag.strip()]

            summary_section = re.search(r'<div class="data-intro">\s*<p>(.*?)</p>', html_text, re.S)
            if summary_section:
                raw_summary = summary_section.group(1)
                summary = html.unescape(re.sub(r'\s+', ' ', raw_summary)).strip()

            return {
                "genres": genres,
                "summary": summary,
                "detail_url": detail_url,
            }
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Web detail timeout ({API_TIMEOUT}s) for animeSn={anime_sn}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error fetching anime web details for animeSn={anime_sn}: {e}", exc_info=True)
            return {}

    async def fetch_anime_details_from_api(self, video_sn: int) -> Optional[Dict]:
        """
        從 Bahamut 手機 API 獲取動畫詳細信息（簡介、標籤、人氣度等）

        API endpoint: https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn}
        返回 anime 部分包含：content(簡介), tags(標籤), popular(人氣度), score(評分)

        Returns:
            詳細信息字典或 None
        """
        if not video_sn:
            logger.info(f"📺 [fetch_anime_details_from_api] video_sn 為空，跳過")
            return None

        api_url = f"https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn}"
        logger.info(f"📺 [fetch_anime_details_from_api] 開始調用 API: {api_url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                    headers={
                        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)"
                    }
                ) as resp:
                    logger.info(f"📺 [fetch_anime_details_from_api] 獲得响應，status={resp.status}")
                    if resp.status != 200:
                        logger.warning(f"⚠️ API detail returned status {resp.status} for videoSn={video_sn}")
                        return None

                    data = await resp.json()
                    anime = data.get("data", {}).get("anime", {})
                    logger.info(f"📺 [fetch_anime_details_from_api] anime 字典鍵: {list(anime.keys()) if anime else '(empty)'}")

                    # 詳細日誌：打印完整的 anime 字典（前 2000 字符）
                    anime_str = str(anime)[:2000] if anime else "(empty)"
                    logger.info(f"📺 [fetch_anime_details_from_api] 完整 anime 數據: {anime_str}")

                    if not anime:
                        logger.warning(f"⚠️ No anime data in API response for videoSn={video_sn}")
                        return None

                    anime_sn = anime.get("anime_sn")
                    title = anime.get("title", "")
                    content = anime.get("content", "")
                    tags = anime.get("tags", [])
                    score = anime.get("score", 0)

                    # 嘗試多個可能的觀看數/人氣字段名（Bahamut API 可能使用不同名稱）
                    # 常見的 Bahamut 觀看次數字段：popular, viewCount, counter, views, view_counter, page_views
                    view_count = (
                        anime.get("popular", 0)
                        or anime.get("viewCount", 0)
                        or anime.get("counter", 0)
                        or anime.get("views", 0)
                        or anime.get("view_counter", 0)
                        or anime.get("page_views", 0)
                        or 0
                    )
                    # 確保是整數
                    if not isinstance(view_count, (int, float)):
                        try:
                            view_count = int(str(view_count).replace(',', ''))
                        except (ValueError, TypeError):
                            view_count = 0
                    view_count = int(view_count)

                    logger.info(f"✅ [fetch_anime_details_from_api] animeSn={anime_sn}, title={title[:30] if title else '(空)'}, tags={tags}, view_count={view_count}, score={score}")
                    logger.info(f"✅ [fetch_anime_details_from_api] 提取的觀看數: view_count={view_count}, type={type(view_count)}, anime.popular={anime.get('popular', 'N/A')}, anime.get('viewCount', 'N/A'), 全部鍵={list(anime.keys())}")

                    # 快取到數據庫
                    if anime_sn:
                        self.db.cache_anime_details(anime_sn, title, content, tags, view_count, score)
                        # 同時記錄統計數據（用於數據分析）
                        self.db.record_episode_stats(
                            video_sn=video_sn,
                            anime_sn=anime_sn,
                            episode_num=f"Ep. {anime.get('video_episode_number', '')}",
                            views=view_count,
                            score=score
                        )

                    return {
                        "anime_sn": anime_sn,
                        "title": title,
                        "content": content,
                        "tags": tags,
                        "popular": view_count,
                        "score": score,
                        "raw_keys": list(anime.keys()),  # 傳回原始鍵列表供調試
                    }
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API detail timeout ({API_TIMEOUT}s) for videoSn={video_sn}")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime details from API for videoSn={video_sn}: {e}", exc_info=True)
            return None

    def _truncate_text(self, text: str, limit: int = 240) -> str:
        return text if len(text) <= limit else text[:limit].rstrip() + '...'

    async def generate_anime_embed(self, episode: Dict) -> discord.Embed:
        """
        生成單個集的 Discord Embed

        包含動畫簡介、標籤、人氣度等信息
        優先使用快取，未快取時調用 API 並存儲到永恆快取

        Args:
            episode: 集信息字典（包含 videoSn, animeSn 等）

        Returns:
            格式化的 discord.Embed
        """
        anime_name = episode.get("title", "Unknown")
        volume = episode.get("volume", "")
        cover_url = episode.get("cover", "")
        anime_sn = episode.get("animeSn", "")
        video_sn = episode.get("videoSn", "")

        # 構建動畫連結
        anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}" if anime_sn else "https://ani.gamer.com.tw"

        # 優先檢查快取，未快取則調用 API
        anime_details = None
        if anime_sn:
            logger.info(f"📺 [generate_anime_embed] 檢查快取 animeSn={anime_sn}")
            anime_details = self.db.get_anime_details(int(anime_sn))
            if anime_details:
                logger.info(f"📺 [generate_anime_embed] ✅ 快取命中 animeSn={anime_sn}")
            else:
                logger.info(f"📺 [generate_anime_embed] ⏸ 快取未命中 animeSn={anime_sn}")

        if not anime_details and video_sn:
            # 快取中沒有，調用 API 獲取並快取
            logger.info(f"📺 [generate_anime_embed] 準備調用 API videoSn={video_sn}")
            anime_details = await self.fetch_anime_details_from_api(int(video_sn))
            if anime_details:
                logger.info(f"📺 [generate_anime_embed] ✅ API 成功回傳數據")
            else:
                logger.info(f"📺 [generate_anime_embed] ❌ API 未返回數據")

        # 提取詳細信息
        content = anime_details.get("content", "") if anime_details else ""
        api_tags = anime_details.get("tags", []) if anime_details else []
        popular = anime_details.get("popular", 0) if anime_details else 0
        score = anime_details.get("score", 0) if anime_details else 0

        logger.info(f"📺 [generate_anime_embed] anime_details type: {type(anime_details)}")
        logger.info(f"📺 [generate_anime_embed] anime_details keys: {list(anime_details.keys()) if anime_details else '(None)'}")
        logger.info(f"📺 [generate_anime_embed] 提取的詳細信息: content_len={len(content)}, tags={api_tags}, popular={popular}, score={score}")
        logger.info(f"📺 [generate_anime_embed] 觀看數詳情: popular={popular}, type={type(popular)}, bool(popular)={bool(popular)}")

        # 構建標籤信息
        tag_parts = []

        # 優先使用 API 返回的標籤
        if api_tags:
            tag_parts.extend([f"#{tag}" for tag in api_tags[:6]])
        else:
            # 如果沒有 API 標籤，嘗試從網頁抓取（舊方式）
            web_details = await self.fetch_anime_web_details(str(anime_sn)) if anime_sn else {}
            genres = web_details.get("genres", [])
            if genres:
                tag_parts.extend([f"#{tag}" for tag in genres[:6]])

        # 添加亮點標籤（雙語、版本等）
        highlight_tag = episode.get("highlightTag", {})
        if not api_tags and highlight_tag.get("bilingual"):
            tag_parts.append("🗣️ 雙語")

        edition = highlight_tag.get("edition", "").strip()
        if edition:
            tag_parts.append(f"📺 {edition}")

        tags_str = " | ".join(tag_parts) if tag_parts else "無特殊標籤"

        # 構建描述，優先使用 API 返回的簡介
        if not content:
            web_details = await self.fetch_anime_web_details(str(anime_sn)) if anime_sn else {}
            content = web_details.get("summary", "")

        description_text = f"**集數：{volume}**"

        # 人氣度和評分信息 - 改為以平均觀看人數為主
        # 嘗試獲取動畫統計信息（用於顯示平均數據）
        anime_stats = self.db.get_anime_statistics(int(anime_sn)) if anime_sn else None

        popularity_text = f"👥 {popular:,}" if popular else "👥 N/A"
        avg_views_text = (
            f"👥 {anime_stats['avg_views']:,.0f}" if anime_stats and anime_stats.get('avg_views') else "👥 N/A"
        )
        score_text = f"⭐ {score:.1f}" if score > 0 else "⭐ N/A"

        embed = discord.Embed(
            title=f"🎬 {anime_name}",
            description=description_text,
            url=anime_url,
            color=discord.Color.from_rgb(178, 108, 196),
            timestamp=datetime.now(TW_TZ)
        )

        if cover_url:
            embed.set_image(url=cover_url)

        # 添加詳細的人氣度與評分字段
        # 注意：popular 為系列人氣累計值（Bahamut API anime.popular），非單集獨立觀看數
        stats_lines = [
            f"**系列人氣**: {popularity_text} | {score_text} 評分"
        ]
        if anime_stats and anime_stats['total_episodes'] > 0:
            avg_views = anime_stats['avg_views']
            avg_score = anime_stats['avg_score']
            stats_lines.append(f"**本季均值**: 👥 {avg_views:,.0f} 人氣 | ⭐ {avg_score:.1f} 評分")
            stats_lines.append(f"**本季統計**: {anime_stats['total_episodes']} 集累積記錄")

        embed.add_field(
            name="📊 人氣數據",
            value="\n".join(stats_lines),
            inline=False
        )

        embed.add_field(
            name="📌 標籤",
            value=tags_str,
            inline=False
        )

        if content:
            embed.add_field(
                name="📝 劇情簡介",
                value=self._truncate_text(content, 140),
                inline=False
            )

        embed.add_field(
            name="🎯 匿名投票",
            value="選擇你認為本作的評價，或留下評論\n投票完全匿名，無法追蹤個人身份",
            inline=False
        )

        embed.add_field(
            name="🎁 獲得獎勵",
            value="💬 **投票**: +2000 KK幣\n📝 **評論**: +3000 KK幣\n每條消息僅限一次獎勵",
            inline=False
        )

        embed.set_footer(text="動畫瘋新番通知 | 使用下方按鈕進行匿名投票")
        return embed

    async def generate_ranking_embed(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        period_label: str = "本季"
    ) -> discord.Embed:
        """生成動畫觀看排行榜 embed（供自動推送使用）"""
        try:
            # 確保 episode_statistics 表存在（修復初始化問題）
            try:
                with sqlite3.connect(self.db.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS episode_statistics (
                            videoSn INTEGER PRIMARY KEY,
                            animeSn INTEGER NOT NULL,
                            episode_num TEXT,
                            views INTEGER,
                            score REAL,
                            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    logger.info("✅ [generate_ranking_embed] 確保 episode_statistics 表存在")
            except Exception as e:
                logger.warning(f"⚠️ [generate_ranking_embed] 表初始化失敗: {e}")

            # 先嘗試從數據庫取歷史統計數據
            top_anime = self.db.get_top_anime_by_views(
                limit=10,
                start_time=start_time,
                end_time=end_time
            )

            # 修復：如果 DB 沒有數據（不論是否有時間篩選），都試從 API 獲取
            # 原先的條件 `if not top_anime and not start_time and not end_time` 會導致
            # 當 send_weekly_stats 傳入 start_time/end_time 時，API 回退永遠不會被觸發
            if not top_anime:
                logger.info(f"📺 [generate_ranking_embed] 數據庫無歷史數據{'（含時間篩選）' if start_time or end_time else ''}，改為實時從 API 獲取")
                episodes = await self.fetch_all_recent_anime_from_api()

                if not episodes:
                    logger.warning("📺 [generate_ranking_embed] 無法獲取動畫數據")
                    return None

                # 按觀看人數排序
                anime_list = {}
                for ep in episodes:
                    anime_sn = ep.get("animeSn")
                    if not anime_sn:
                        continue

                    anime_name = ep.get("title", f"Anime #{anime_sn}")
                    views = 0

                    # 優先從 index API 直接提取觀看數（省去額外 API 調用）
                    views = self._extract_view_count_from_episode(ep)

                    # 如果 index API 沒有觀看數，調用 video.php 獲取詳細數據
                    if views <= 0:
                        try:
                            video_sn = ep.get("videoSn")
                            if video_sn:
                                details = await self.fetch_anime_details_from_api(video_sn)
                                if details:
                                    views = details.get("popular", 0)
                                    # 使用 API 返回的正確動畫名稱
                                    if details.get("title"):
                                        anime_name = details.get("title")
                                        logger.info(f"📺 [generate_ranking_embed] 獲得動畫名稱: {anime_name} (animeSn={anime_sn})")
                        except Exception as e:
                            logger.warning(f"⚠️ 無法取得 videoSn={video_sn} 的詳細信息: {e}")

                    # 聚合多集的数据
                    if anime_sn not in anime_list:
                        anime_list[anime_sn] = {
                            "name": anime_name,
                            "episodes": [],
                            "total_views": 0,
                            "total_episodes": 0,
                        }

                    if views > 0:
                        anime_list[anime_sn]["episodes"].append(views)
                        anime_list[anime_sn]["total_views"] += views
                        anime_list[anime_sn]["total_episodes"] += 1
                    else:
                        # 即使 views=0 也統計集數（但用 0 計算總觀看數）
                        anime_list[anime_sn]["episodes"].append(views)
                        anime_list[anime_sn]["total_episodes"] += 1

                # 轉換為排行格式並按總觀看數排序
                top_anime = []
                for anime_sn, data in anime_list.items():
                    if data["total_episodes"] > 0:
                        logger.info(f"📺 [generate_ranking_embed] 排行動畫: {data['name']} (animeSn={anime_sn}, views={data['total_views']})")
                        top_anime.append({
                            "anime_sn": anime_sn,
                            "name": data["name"],
                            "total_views": data["total_views"],
                            "total_episodes": data["total_episodes"]
                        })

                # 按總觀看數排序
                top_anime.sort(key=lambda x: x["total_views"], reverse=True)
                top_anime = top_anime[:10]

                if not top_anime:
                    logger.info("📺 [generate_ranking_embed] 無有效的動畫數據")
                    return None

                logger.info(f"📺 [generate_ranking_embed] 實時獲取了 {len(top_anime)} 部動畫的數據")

            # 嘗試獲取有多集的動畫數據（用於多線圖）
            # 改進：增加 limit 到 15，降低 min_episodes 到 1，讓更多動畫納入統計
            multi_anime = self.db.get_multi_episode_anime_for_chart(
                limit=10,
                min_episodes=1,
                start_time=start_time,
                end_time=end_time
            )
            logger.info(f"📺 [generate_ranking_embed] 查詢 multi_anime 結果: {len(multi_anime) if multi_anime else 0} 部動畫")
            if multi_anime:
                for i, anime in enumerate(multi_anime[:5]):  # 顯示前 5 部的詳細資訊
                    logger.info(f"  📺 [{i+1}] {anime['name']}: {len(anime['episodes'])} 集, {anime['total_views']} 次觀看")

            ranked_chart_anime = []
            if multi_anime:
                multi_anime_by_sn = {anime['anime_sn']: anime for anime in multi_anime}
                ranked_chart_anime = [
                    multi_anime_by_sn[anime['anime_sn']]
                    for anime in top_anime
                    if anime['anime_sn'] in multi_anime_by_sn
                ]

            embed = discord.Embed(
                title=f"🏆 {period_label}動畫觀看排行",
                color=discord.Color.gold(),
                timestamp=datetime.now(TW_TZ)
            )

            period_text = None
            if start_time and end_time:
                period_text = f"{start_time.strftime('%m/%d')} - {(end_time - timedelta(seconds=1)).strftime('%m/%d')}"

            rank_emojis = ["🥇", "🥈", "🥉"]
            ranking_lines = []
            for idx, anime in enumerate(top_anime, 1):
                anime_name = anime.get('name', f"Anime #{anime.get('anime_sn', '?')}").strip()
                display_name = anime_name if len(anime_name) <= 22 else f"{anime_name[:22]}..."
                rank_prefix = rank_emojis[idx - 1] if idx <= len(rank_emojis) else f"#{idx}"
                ranking_lines.append(
                    f"{rank_prefix} **{display_name}** - {anime['total_views']:,} 次 | {anime['total_episodes']} 集"
                )

            ranking_summary = "\n".join(ranking_lines) if ranking_lines else "本期尚無足夠觀看數據"

            # 如果有多集數據，生成多線趨勢圖；否則使用單線聚合圖
            if ranked_chart_anime and len(ranked_chart_anime) >= 2:
                # ===== 模式 A：多線趨勢圖（每部動畫一條線）=====
                if period_text:
                    embed.description = f"**統計週期**: {period_text}\n依總觀看數排名，折線圖只顯示實際上榜作品的集數累計趨勢"
                else:
                    embed.description = "依總觀看數排名，折線圖只顯示實際上榜作品的集數累計趨勢"

                # 構建多線圖表
                datasets = []

                # 顏色數組（10 種顏色）
                colors = [
                    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
                    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#ABEBC6"
                ]

                # 找出所有集數編號（X 軸）- 改進標準化處理
                all_episodes = set()
                for anime in ranked_chart_anime:
                    for ep in anime['episodes']:
                        ep_num = ep['num']
                        # 標準化集數格式：提取數字部分
                        if isinstance(ep_num, str):
                            # 提取數字（如 "第1集" -> 1, "EP.1" -> 1）
                            import re
                            numbers = re.findall(r'\d+', ep_num)
                            if numbers:
                                ep_num = int(numbers[0])
                            else:
                                continue
                        elif isinstance(ep_num, (int, float)):
                            ep_num = int(ep_num)
                        else:
                            continue

                        all_episodes.add(ep_num)

                # 排序並生成標籤（使用更清楚的集數格式）
                episode_labels = [f"第{ep}集" for ep in sorted(list(all_episodes))]

                # 為每部動畫建立一條線
                for idx, anime in enumerate(ranked_chart_anime):
                    name = anime['name'][:12]  # 增加到 12 個字以便識別
                    color = colors[idx % len(colors)]

                    # 建立該動畫的數據點（缺失集用 None）- 配合新標籤格式
                    ep_dict = {}
                    for ep in anime['episodes']:
                        # 標準化集數格式以匹配 episode_labels ("第X集")
                        ep_num = ep['num']
                        if isinstance(ep_num, str):
                            import re
                            numbers = re.findall(r'\d+', ep_num)
                            if numbers:
                                ep_num = f"第{int(numbers[0])}集"
                            else:
                                continue
                        elif isinstance(ep_num, (int, float)):
                            ep_num = f"第{int(ep_num)}集"
                        else:
                            continue

                        ep_dict[ep_num] = ep['views']

                    data = [ep_dict.get(label) for label in episode_labels]

                    # 改進：處理累計觀看數（如果需要顯示累計趨勢）
                    cumulative_data = []
                    cumulative_sum = 0
                    for views in data:
                        if views is not None:
                            cumulative_sum += views
                        cumulative_data.append(cumulative_sum if cumulative_sum > 0 else None)

                    datasets.append({
                        "label": name,
                        "data": cumulative_data,  # 使用累計數據顯示成長趨勢
                        "borderColor": color,
                        "fill": False,
                        "showLine": True,
                        "tension": 0.1  # 添加輕微的曲線效果
                    })

                # 構建圖表配置（改進版 - 適合集數累計觀看數顯示）
                try:
                    chart_config = {
                        "type": "line",
                        "data": {
                            "labels": episode_labels,
                            "datasets": datasets
                        },
                        "options": {
                            "responsive": True,
                            "plugins": {
                                "legend": {"position": "top"},
                                "title": {
                                    "display": True,
                                    "text": "動畫集數累計觀看數趨勢"
                                }
                            },
                            "scales": {
                                "x": {
                                    "title": {
                                        "display": True,
                                        "text": "集數"
                                    }
                                },
                                "y": {
                                    "title": {
                                        "display": True,
                                        "text": "累計觀看數"
                                    },
                                    "beginAtZero": True
                                }
                            }
                        }
                    }

                    # 嘗試使用短 URL API，失敗則改用直接 URL
                    short_url = await self.get_quickchart_short_url(chart_config)
                    if short_url:
                        chart_url = short_url
                        logger.info(f"✅ [generate_ranking_embed] 多線趨勢圖短 URL 已取得")
                    else:
                        # 改用直接 URL（只要長度不超過 2048）
                        config_json = json.dumps(chart_config, separators=(',', ':'), ensure_ascii=False)
                        encoded = quote(config_json)
                        chart_url = f"https://quickchart.io/chart?bkg=white&w=950&h=400&c={encoded}"

                        logger.info(f"📺 [generate_ranking_embed] 直接 URL 長度: {len(chart_url)}")

                        if len(chart_url) > 2048:
                            logger.warning(f"⚠️ [generate_ranking_embed] URL {len(chart_url)} 字元超過限制，改用文字顯示")
                            ranked_chart_anime = []  # 改用模式 B
                            chart_url = None

                    # 直接使用圖表 URL
                    if chart_url:
                        embed.set_image(url=chart_url)
                        logger.info(f"✅ [generate_ranking_embed] 多線趨勢圖已設置")

                    embed.add_field(
                        name="📋 排行名單",
                        value=ranking_summary,
                        inline=False
                    )
                except Exception as e:
                    logger.warning(f"⚠️ [generate_ranking_embed] 生成多線圖失敗: {e}，改用文字顯示")
                    ranked_chart_anime = []  # 改用模式 B

            # === 模式 B：文字排行列表（當無多集數據或圖表生成失敗）===
            if not ranked_chart_anime or len(ranked_chart_anime) < 2:
                if period_text:
                    embed.description = f"**統計週期**: {period_text}\n前 {len(top_anime)} 名觀看排行"
                else:
                    embed.description = f"前 {len(top_anime)} 名觀看排行"

                # 生成單線聚合圖
                anime_names = []
                anime_views = []
                for idx, anime in enumerate(top_anime, 1):
                    anime_name = anime.get('name', f"#{anime.get('anime_sn')}")
                    short_name = anime_name[:8] if len(anime_name) > 8 else anime_name
                    anime_names.append(f"#{idx} {short_name}")
                    anime_views.append(anime['total_views'])

                try:
                    chart_config = {
                        "type": "line",
                        "data": {
                            "labels": anime_names,
                            "datasets": [{
                                "data": anime_views,
                                "borderColor": "#FFD700",
                                "backgroundColor": "rgba(255,215,0,0.1)",
                                "borderWidth": 2,
                                "fill": True,
                                "tension": 0.3,
                                "pointRadius": 3,
                                "pointBackgroundColor": "#FFD700"
                            }]
                        },
                        "options": {
                            "scales": {
                                "y": {"ticks": {"font": {"size": 10}}},
                                "x": {"ticks": {"font": {"size": 8}}}
                            },
                            "plugins": {"legend": {"display": False}}
                        }
                    }

                    # 直接使用 URL 編碼方式（確保圖片一定能顯示）
                    config_json = json.dumps(chart_config, separators=(',', ':'), ensure_ascii=False)
                    encoded = quote(config_json)
                    chart_url = f"https://quickchart.io/chart?bkg=white&w=850&h=350&c={encoded}"

                    if len(chart_url) <= 2048:
                        embed.set_image(url=chart_url)
                        logger.info(f"📺 [generate_ranking_embed] 單線聚合圖 URL 已設置 (長度: {len(chart_url)})")
                except Exception as e:
                    logger.warning(f"⚠️ [generate_ranking_embed] 生成單線圖 URL 失敗: {e}")

                embed.add_field(
                    name="📋 排行名單",
                    value=ranking_summary,
                    inline=False
                )

            embed.set_footer(text="📊 排行與集數觀看趨勢" if ranked_chart_anime and len(ranked_chart_anime) >= 2 else "📈 觀看排行")

            logger.info(f"📺 [generate_ranking_embed] 排行榜已生成（模式: {'多線趨勢' if ranked_chart_anime and len(ranked_chart_anime) >= 2 else '聚合排行'}）")
            return embed
        except Exception as e:
            logger.error(f"❌ [generate_ranking_embed] 生成失敗: {e}", exc_info=True)
            return None

    async def send_weekly_stats(self) -> None:
        """自動發送週統計 - 每週天 台灣時間 23:00 發送"""
        now = datetime.now(TW_TZ)

        try:
            # 檢查是否是禮拜天且時間在晚上 23:00-23:59
            is_sunday = now.weekday() == 6  # 6 = Sunday
            is_send_time = now.hour == 23  # 台灣時間 23:00-23:59

            # 檢查是否已在本週發送過（防止重複）
            week_start = now - timedelta(days=now.weekday())
            week_start_date = week_start.date()

            if is_sunday and is_send_time and self.last_weekly_stats_sent != week_start_date:
                logger.info(f"📊 [send_weekly_stats] 禮拜天時間到，準備發送週統計...")

                # 獲取頻道
                channel = None  # 這裡需要從外部傳入或透過其他方式獲取
                # 在實際使用中，這個方法會被 AnimeTracker 類別的 send_weekly_stats 方法調用
                # 該方法會傳入正確的 channel 參數
                raise NotImplementedError("此方法需要傳入 channel 參數，應由 AnimeTracker 實際實現")

                # 以下是原始實作（現在被註解掉，因為需要 channel 參數）
                # if not channel:
                #     logger.error(f"❌ [send_weekly_stats] 找不到頻道 {ANIME_CHANNEL_ID}")
                #     return

                # week_start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
                # week_end_dt = week_start_dt + timedelta(days=7)
                # week_end = week_end_dt - timedelta(seconds=1)
                # week_start_str = week_start_dt.strftime("%m/%d")
                # week_end_str = week_end.strftime("%m/%d")

                # # 獲取週統計數據
                # weekly_stats = self.db.get_weekly_vote_stats()

                # if weekly_stats:
                #     embed = discord.Embed(
                #         title="📊 本週動畫投票統計",
                #         description=f"**統計週期**: {week_start_str} - {week_end_str}",
                #         color=discord.Color.blue(),
                #         timestamp=now
                #     )

                #     # 按投票總數排序
                #     sorted_animes = sorted(
                #         weekly_stats.items(),
                #         key=lambda x: x[1]['total_votes'],
                #         reverse=True
                #     )

                #     # 添加各動畫的統計
                #     for rank, (anime_sn, stats) in enumerate(sorted_animes[:10], 1):  # 顯示前 10 部
                #         anime_name = stats['anime_name']
                #         total_votes = stats['total_votes']
                #         votes_breakdown = stats['votes']
                #         episode_count = len(stats['episodes'])

                #         # 構建投票明細
                #         vote_type_names = {
                #             'masterpiece': '🟢 神作',
                #             'great': '⚫ 佳作',
                #             'darkhorse': '⚫ 黑馬',
                #             'decent': '🔵 普作',
                #             'controversial': '⚫ 爭議作',
                #             'disaster': '🔴 雷作'
                #         }

                #         vote_details = []
                #         for vote_type in sorted(votes_breakdown.keys(),
                #                                key=lambda x: votes_breakdown[x], reverse=True):
                #             count = votes_breakdown[vote_type]
                #             label = vote_type_names.get(vote_type, vote_type)
                #             vote_details.append(f"{label}: {count}")

                #         details_str = " | ".join(vote_details) if vote_details else "無投票"

                #         embed.add_field(
                #             name=f"#{rank} {anime_name}",
                #             value=f"**投票總數**: {total_votes} | **涉及集數**: {episode_count}\n{details_str}",
                #             inline=False
                #         )

                #     # 添加總體統計
                #     total_all_votes = sum(stats['total_votes'] for stats in weekly_stats.values())
                #     unique_animes = len(weekly_stats)

                #     embed.set_footer(text=f"總計: {total_all_votes} 投票 | {unique_animes} 部作品")

                #     # 發送投票統計
                #     await channel.send(embed=embed)
                #     logger.info(f"✅ [send_weekly_stats] 週投票統計已發送: {unique_animes} 部作品, {total_all_votes} 投票")
                # else:
                #     logger.info("📊 [send_weekly_stats] 本週無投票數據，僅發送觀看排行")

                # # 發送觀看量趨勢折線圖（改進：按集數累計顯示）
                # try:
                #     ranking_embed = await self.generate_ranking_embed(
                #         start_time=week_start_dt,
                #         end_time=week_end_dt,
                #         period_label="本週"
                #     )
                #     if ranking_embed:
                #         await channel.send(embed=ranking_embed)
                #         logger.info("✅ [send_weekly_stats] 集數累計觀看趨勢圖已發送")
                #     else:
                #         logger.info("⚠️ [send_weekly_stats] 無足夠集數數據生成趨勢圖，跳過")
                # except Exception as chart_err:
                #     logger.warning(f"⚠️ [send_weekly_stats] 趨勢圖生成失敗（不影響投票統計）: {chart_err}")

                # # 標記已發送
                # self.last_weekly_stats_sent = week_start_date

        except Exception as e:
            logger.error(f"❌ [send_weekly_stats] 發送週統計失敗: {e}", exc_info=True)

    async def sync_episode_stats(self) -> None:
        """
        每 6 小時從 Bahamut index API 同步一次 episode 統計數據，
        確保 episode_statistics 表有足夠的觀看數歷史資料，
        讓週日排行功能能正確顯示觀看人數成長。

        獨立於新集通知流程，避免"只有發通知才有統計"的問題。
        """
        try:
            now = datetime.now(TW_TZ)
            # 避開凌晨時段（2-5點 API 可能維護中）和整點高峰
            skip_hours = {2, 3, 4, 5}
            if now.hour in skip_hours:
                logger.debug(f"⏭️ [sync_episode_stats] 跳過維護時段（{now.hour}:00）")
                return

            logger.info(f"🔄 [sync_episode_stats] 開始同步 episode 統計數據...")
            await self._sync_episode_stats_from_api()
            logger.info(f"✅ [sync_episode_stats] 同步完成")

        except Exception as e:
            logger.error(f"❌ [sync_episode_stats] 同步失敗: {e}", exc_info=True)

    async def daily_anime_check(self) -> None:
        """每日直接從 API 檢查新番（取代週表模式）"""
        try:
            # 防止重複執行（同一天內只執行一次）
            today = datetime.now(TW_TZ).date()
            if self.last_daily_check_date == today:
                return

            # 檢查是否在檢查時間內（每天 9:00-9:59 執行）
            now = datetime.now(TW_TZ)
            is_check_time = now.hour == 9  # 現在是 9:00-9:59

            if not is_check_time:
                return

            self.last_daily_check_date = today
            logger.info(f"🚀 [daily_anime_check] 開始每日動畫檢查 (時間: {now.strftime('%Y-%m-%d %H:%M:%S')})")

            # 獲取頻道
            channel = None  # 需要從外部傳入
            if not channel:
                logger.error(f"❌ [daily_anime_check] 找不到頻道 ID: {ANIME_CHANNEL_ID}")
                return

            # 檢查並發送新番
            found_new = await self._check_and_send_anime("DAILY_CHECK", channel)

            if found_new:
                logger.info(f"✅ [daily_anime_check] 每日檢查完成，發現並發送了新番通知")
            else:
                logger.info(f"ℹ️ [daily_anime_check] 每日檢查完成，今日無新番")

        except Exception as e:
            logger.error(f"❌ [daily_anime_check] 每日檢查失敗: {e}", exc_info=True)

    # 下面的方法需要在 AnimeTracker 類別中實作，此處僅作為介面
    async def _check_and_send_anime(self, scheduled_time_str: str, channel) -> bool:
        """檢查新番集並發送通知（用於多窗口檢查）"""
        raise NotImplementedError("此方法應由 AnimeTracker 實際實現")

    async def send_anime_push(self, scheduled_time: str, channel_id: int = ANIME_CHANNEL_ID) -> bool:
        """在預定時刻推送動畫通知 - 查詢真實 API 確認已上架集"""
        raise NotImplementedError("此方法應由 AnimeTracker 實際實現")


async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式 - cog_load() 會自動被調用"""
    import sys
    print("[SETUP_START] 🎬 AnimeTracker setup() 開始", flush=True)
    sys.stdout.flush()

    try:
        # 這裡應該創建 AnimeTracker 實例並加載到 bot
        # 但由於 AnimeTracker 現在被分割成多個類別，
        # 實際的 setup 邏輯需要在 main anime_tracker.py 中或透過其他方式實現
        # 此處提供基本框架

        from .push_core import AnimeDatabase
        from .schedule_tracker import AnimeScheduleTracker
        from .ranking_stats import RankingStats

        db = AnimeDatabase(ANIME_DB_PATH)
        schedule_tracker = AnimeScheduleTracker(db)
        ranking_stats = RankingStats(db)

        # 實際的 AnimeTracker 實例創建和方法組合應該在其他地方完成
        # 此 setup 函數主要是為了與原始結構相容
        logger.info("✅ AnimeTracker 核心組件已初始化")
        print("[SETUP_END] 🎬 AnimeTracker setup() 完成", flush=True)
        sys.stdout.flush()

    except Exception as setup_err:
        import traceback
        error_msg = f"❌ [setup] AnimeTracker setup() 失敗: {setup_err}"
        print(f"[SETUP_ERROR] {error_msg}", flush=True)
        print(f"[SETUP_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
        logger.error(error_msg, exc_info=True)
        raise