# -*- coding: utf-8 -*-
"""
Bahamut 動畫排名統計系統 - 簡化版

功能：
- 動畫詳情 API 獲取與快取
- 動畫 Embed 生成
- 排名排行榜生成
使用獨立資料庫：anime_push.db
"""

import logging
import re
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import discord
from discord.ext import commands
from .push_core_simple import (
    ANIME_PUSH_DB_PATH,
    fetch_all_recent_anime_from_api,
    fetch_anime_details_from_api,
    extract_view_count_from_episode,
    TW_TZ,
)

logger = logging.getLogger(__name__)


class RankingStats:
    """排名和統計管理器 - 簡化版"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(ANIME_PUSH_DB_PATH)
        self.bot = None
        self.db = None  # 相容性介面

    def set_dependencies(self, bot, db):
        """設置依賴"""
        self.bot = bot
        self.db = db  # 相容性：提供給舊代碼使用

    # ==================== API 獲取方法（保留） ====================

    async def fetch_all_recent_anime_from_api(self) -> Optional[List[Dict]]:
        """從 Bahamut API 獲取所有最近的動畫集 - 代理到 push_core_simple"""
        from .push_core_simple import fetch_all_recent_anime_from_api
        return await fetch_all_recent_anime_from_api()

    def _extract_view_count_from_episode(self, episode: dict, default: int = 0) -> int:
        """從 episode 物件提取觀看數 - 代理到 push_core_simple"""
        from .push_core_simple import extract_view_count_from_episode
        return extract_view_count_from_episode(episode, default)

    async def fetch_anime_details_from_api(self, video_sn: int) -> Optional[Dict]:
        """從 Bahamut 手機 API 獲取動畫詳細信息 - 代理到 push_core_simple"""
        from .push_core_simple import fetch_anime_details_from_api
        return await fetch_anime_details_from_api(video_sn)

    # ==================== Embed 生成（保留） ====================

    def _get_weekday_name(self, weekday_num: int) -> str:
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        if 1 <= weekday_num <= 7:
            return weekdays[weekday_num - 1]
        return "未知"

    def _truncate_text(self, text: str, limit: int = 240) -> str:
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    async def generate_anime_embed(self, episode: Dict) -> Optional[discord.Embed]:
        """生成單個集的 Discord Embed"""
        try:
            anime_name = episode.get("title", "Unknown")
            volume = episode.get("volume", "")
            cover_url = episode.get("cover", "")
            anime_sn = episode.get("animeSn", "")
            video_sn = episode.get("videoSn", "")

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
                logger.info(f"📺 [generate_anime_embed] 準備調用 API videoSn={video_sn}")
                anime_details = await fetch_anime_details_from_api(int(video_sn))
                if anime_details:
                    logger.info("📺 [generate_anime_embed] ✅ API 成功回傳數據")
                else:
                    logger.info("📺 [generate_anime_embed] ❌ API 未返回數據")

            # 提取詳細信息
            content = anime_details.get("content", "") if anime_details else ""
            api_tags = anime_details.get("tags", []) if anime_details else []
            popular = anime_details.get("popular", 0) if anime_details else 0
            score = anime_details.get("score", 0) if anime_details else 0

            # 構建標籤信息
            tag_parts = []
            if api_tags:
                tag_parts.extend([f"#{tag}" for tag in api_tags[:6]])
            else:
                # 如果沒有 API 標籤，嘗試從網頁抓取（可選）
                pass

            # 添加亮點標籤
            highlight_tag = episode.get("highlightTag", {})
            if not api_tags and highlight_tag.get("bilingual"):
                tag_parts.append("🗣️ 雙語")

            edition = highlight_tag.get("edition", "").strip()
            if edition:
                tag_parts.append(f"📺 {edition}")

            tags_str = " | ".join(tag_parts) if tag_parts else "無特殊標籤"

            # 構建描述
            description_parts = [f"**集數：{volume}**"]
            if content:
                description_parts.append(self._truncate_text(content, 200))

            description_text = "\n\n".join(description_parts)

            # 人氣度和評分信息
            popularity_text = f"👥 {popular:,}" if popular else "👥 N/A"
            score_text = f"⭐ {score:.1f}" if score > 0 else "⭐ N/A"

            embed = discord.Embed(
                title=f"🎬 {anime_name}",
                description=description_text,
                url=anime_url,
                color=discord.Color.from_rgb(178, 108, 196),
                timestamp=datetime.now(TW_TZ),
            )

            if cover_url:
                embed.set_image(url=cover_url)

            stats_lines = [f"**系列人氣**: {popularity_text} | {score_text} 評分"]
            embed.add_field(name="📊 人氣數據", value="\n".join(stats_lines), inline=False)
            embed.add_field(name="📌 標籤", value=tags_str, inline=False)

            embed.add_field(
                name="🎯 匿名投票",
                value="選擇你認為本作的評價，或留下評論\n投票完全匿名，無法追蹤個人身份",
                inline=False,
            )

            embed.add_field(
                name="🎁 獲得獎勵",
                value="💬 **投票**: +2000 KK幣\n📝 **評論**: +3000 KK幣\n每條消息僅限一次獎勵",
                inline=False,
            )

            embed.set_footer(text="動畫瘋新番通知 | 使用下方按鈕進行匿名投票")
            return embed

        except Exception as e:
            logger.error(f"❌ [generate_anime_embed] 生成失敗: {e}", exc_info=True)
            return None

    async def generate_ranking_embed(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        period_label: str = "本季",
    ) -> Optional[discord.Embed]:
        """生成動畫觀看排行榜 embed - 簡化版（不使用 episode_statistics）"""
        try:
            # 直接從 API 獲取實時數據
            logger.info(f"📺 [generate_ranking_embed] 實時從 API 獲取 {period_label} 數據")
            episodes = await fetch_all_recent_anime_from_api()

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
                views = extract_view_count_from_episode(ep)

                if views <= 0:
                    try:
                        video_sn = ep.get("videoSn")
                        if video_sn:
                            details = await fetch_anime_details_from_api(video_sn)
                            if details:
                                views = details.get("popular", 0)
                                if details.get("title"):
                                    anime_name = details.get("title")
                    except Exception as e:
                        logger.warning(f"⚠️ 無法取得 videoSn={video_sn} 的詳細信息: {e}")

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
                    anime_list[anime_sn]["episodes"].append(views)
                    anime_list[anime_sn]["total_episodes"] += 1

            # 轉換為排行格式並按總觀看數排序
            top_anime = []
            for anime_sn, data in anime_list.items():
                if data["total_episodes"] > 0:
                    top_anime.append({
                        "anime_sn": anime_sn,
                        "name": data["name"],
                        "total_views": data["total_views"],
                        "total_episodes": data["total_episodes"],
                    })

            top_anime.sort(key=lambda x: x["total_views"], reverse=True)
            top_anime = top_anime[:10]

            if not top_anime:
                return None

            embed = discord.Embed(
                title=f"🏆 {period_label}動畫觀看排行",
                color=discord.Color.gold(),
                timestamp=datetime.now(TW_TZ),
            )

            rank_emojis = ["🥇", "🥈", "🥉"]
            ranking_lines = []
            for idx, anime in enumerate(top_anime, 1):
                anime_name = anime.get("name", f"Anime #{anime.get('anime_sn', '?')}").strip()
                display_name = anime_name if len(anime_name) <= 22 else f"{anime_name[:22]}..."
                rank_prefix = rank_emojis[idx - 1] if idx <= len(rank_emojis) else f"#{idx}"
                ranking_lines.append(
                    f"{rank_prefix} **{display_name}** - {anime['total_views']:,} 次 | {anime['total_episodes']} 集"
                )

            ranking_summary = "\n".join(ranking_lines) if ranking_lines else "本期尚無足夠觀看數據"

            # 生成簡單聚合圖
            try:
                anime_names = []
                anime_views = []
                for idx, anime in enumerate(top_anime, 1):
                    anime_name = anime.get("name", f"#{anime.get('anime_sn')}")
                    short_name = anime_name[:8] if len(anime_name) > 8 else anime_name
                    anime_names.append(f"#{idx} {short_name}")
                    anime_views.append(anime["total_views"])

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
                            "pointBackgroundColor": "#FFD700",
                        }],
                    },
                    "options": {
                        "scales": {
                            "y": {"ticks": {"font": {"size": 10}}},
                            "x": {"ticks": {"font": {"size": 8}}},
                        },
                        "plugins": {"legend": {"display": False}},
                    },
                }

                config_json = json.dumps(chart_config, separators=(",", ":"), ensure_ascii=False)
                from urllib.parse import quote
                encoded = quote(config_json)
                chart_url = f"https://quickchart.io/chart?bkg=white&w=850&h=350&c={encoded}"

                if len(chart_url) <= 2048:
                    embed.set_image(url=chart_url)
                    logger.info(f"📺 [generate_ranking_embed] 聚合圖 URL 已設置")

            except Exception as e:
                logger.warning(f"⚠️ [generate_ranking_embed] 生成圖表失敗: {e}")

            embed.add_field(name="📋 排行名單", value=ranking_summary, inline=False)
            embed.set_footer(text="📈 觀看排行 (實時 API 數據)")

            logger.info(f"📺 [generate_ranking_embed] 排行榜已生成 (前 {len(top_anime)} 名)")
            return embed

        except Exception as e:
            logger.error(f"❌ [generate_ranking_embed] 生成失敗: {e}", exc_info=True)
            return None


# 模組級別函數（相容性）
async def fetch_all_recent_anime_from_api() -> Optional[List[Dict]]:
    from .push_core_simple import fetch_all_recent_anime_from_api
    return await fetch_all_recent_anime_from_api()

async def fetch_anime_details_from_api(video_sn: int) -> Optional[Dict]:
    from .push_core_simple import fetch_anime_details_from_api
    return await fetch_anime_details_from_api(video_sn)

def extract_view_count_from_episode(episode: dict, default: int = 0) -> int:
    from .push_core_simple import extract_view_count_from_episode
    return extract_view_count_from_episode(episode, default)

async def setup(bot):
    """Discord.py 加載入口"""
    logger.info("📊 [RankingStats] 簡化版排名統計模組已加載")