# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 自動通知新上架集數

功能：
- 定時檢查 Bahamut 首頁 API，獲取最近更新的動畫集數
- 追蹤已通知過的集數（videoSn），防止重複通知
- 初次啟動時執行 bootstrap，記錄當前所有集數，不發送通知
- 之後的每次檢查，只通知"新出現的集"（新 videoSn）
- 發送格式化 Discord Embed 到指定頻道

API：
- https://api.gamer.com.tw/mobile_app/anime/v3/index.php
- 返回 newAnime[]：最近更新的集列表
- 每個集包含：animeSn, videoSn, title, volume, cover, upTime 等

關鍵設計：
- 追蹤 videoSn（集的唯一識別符）而非 animeSn（動畫ID）
- 原因：同一個動畫可能有多個最近更新的集，每個有不同的 videoSn
- Bootstrap：首次運行記錄所有現存 videoSn，之後只通知新集
"""

# 模塊導入時就輸出標記，確保能追蹤加載
import sys
print("[ANIME_TRACKER_MODULE] Module is being imported...", flush=True)
sys.stdout.flush()

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import aiohttp
import sqlite3
import json
import logging
import re
import html
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# 配置
ANIME_CHANNEL_ID = 1252204317453324333  # 動畫通知頻道
ANIME_DB_PATH = Path(__file__).resolve().parent.parent / "uibot_anime.db"  # 獨立的動畫追蹤數據庫，固定到專案根目錄
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # 秒

# 表名與欄位
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"


class AnimeDatabase:
    """處理 Bahamut 動畫追蹤所需的數據庫操作"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """初始化數據庫表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. 已通知集列表（主要追蹤表）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {NOTIFIED_TABLE} (
                        videoSn INTEGER PRIMARY KEY,
                        animeSn INTEGER NOT NULL,
                        anime_name TEXT NOT NULL,
                        volume TEXT,
                        cover_url TEXT,
                        notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 2. Bootstrap 標誌（記錄是否完成初始化）
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {BOOTSTRAP_FLAG_TABLE} (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        bootstrap_completed INTEGER DEFAULT 0,
                        completed_at TIMESTAMP
                    )
                """)
                
                conn.commit()
                logger.info(f"✅ Anime database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to init anime DB: {e}")
            raise
    
    def is_bootstrap_completed(self) -> bool:
        """檢查是否已完成 bootstrap（初始化）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT bootstrap_completed FROM {BOOTSTRAP_FLAG_TABLE} WHERE id = 1")
                result = cursor.fetchone()
                return result and result[0] == 1
        except Exception as e:
            logger.error(f"❌ Error checking bootstrap: {e}")
            return False
    
    def mark_bootstrap_completed(self):
        """標記 bootstrap 完成"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {BOOTSTRAP_FLAG_TABLE} (id, bootstrap_completed, completed_at)
                    VALUES (1, 1, CURRENT_TIMESTAMP)
                """)
                conn.commit()
                logger.info("✅ Bootstrap marked as completed")
        except Exception as e:
            logger.error(f"❌ Error marking bootstrap: {e}")
    
    def is_notified(self, video_sn: int) -> bool:
        """檢查集是否已通知過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT 1 FROM {NOTIFIED_TABLE} WHERE videoSn = ?", (video_sn,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Error checking notified status: {e}")
            return False
    
    def add_notified(self, video_sn: int, anime_sn: int, anime_name: str, volume: str, cover_url: str):
        """記錄已通知的集"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR IGNORE INTO {NOTIFIED_TABLE} 
                    (videoSn, animeSn, anime_name, volume, cover_url, notified_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_sn, anime_sn, anime_name, volume, cover_url))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Error adding notified record: {e}")
    
    def bootstrap_add_all(self, episodes: List[Dict]):
        """Bootstrap：一次性添加所有當前集合到數據庫，不發送通知"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for ep in episodes:
                    video_sn = ep.get("videoSn")
                    if video_sn and not self.is_notified(video_sn):
                        cursor.execute(f"""
                            INSERT OR IGNORE INTO {NOTIFIED_TABLE}
                            (videoSn, animeSn, anime_name, volume, cover_url, notified_at)
                            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (
                            video_sn,
                            ep.get("animeSn"),
                            ep.get("title", "Unknown"),
                            ep.get("volume", ""),
                            ep.get("cover", "")
                        ))
                conn.commit()
                logger.info(f"✅ Bootstrap: added {len(episodes)} episodes to notified list")
        except Exception as e:
            logger.error(f"❌ Error during bootstrap: {e}")


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤主 Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AnimeDatabase(ANIME_DB_PATH)
        self.task_started = False
        self.bootstrap_completed = False
        logger.info("📺 AnimeTracker Cog instantiated")
        logger.info(f"📺 Bot 已就緒? {bot.is_ready()}")
        logger.info(f"📺 頻道 ID: {ANIME_CHANNEL_ID}")
        logger.info(f"📺 數據庫路徑: {ANIME_DB_PATH}")
    
    async def cog_load(self):
        """Cog 加載時啟動任務（Discord.py 支持此選項卡）"""
        try:
            logger.info("📺 cog_load() 被調用，準備啟動任務...")
            if not self.check_new_anime.is_running():
                logger.info("📺 任務未在運行，現在啟動...")
                self.check_new_anime.start()
                self.task_started = True
                logger.info("✅ AnimeTracker 任務已在 cog_load() 中啟動")
            else:
                logger.warning("⚠️ 任務已在運行中，跳過重複啟動")
        except Exception as e:
            logger.error(f"❌ cog_load() 啟動任務失敗: {e}", exc_info=True)
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        if self.check_new_anime.is_running():
            self.check_new_anime.cancel()
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """
        監聽反應事件 - 當用戶給動畫通知評分時獎勵 KK幣
        支持任何表情反應（正評或負評都可以）
        """
        # 不處理 bot 自己的反應
        if user.bot:
            return
        
        # 只處理來自動畫通知頻道的反應
        if reaction.message.channel.id != ANIME_CHANNEL_ID:
            return
        
        try:
            # 檢查 embed 是否包含評分提示（即是否為動畫通知）
            embeds = reaction.message.embeds
            if not embeds:
                return
            
            embed = embeds[0]
            # 檢查是否包含評分提示字段
            is_anime_message = any(
                field.name == "⭐ 點擊反應留下評價吧" 
                for field in embed.fields
            )
            
            if not is_anime_message:
                return
            
            logger.info(f"📺 [on_reaction_add] {user.name} 給動畫通知評分（反應：{reaction.emoji}）")
            
            # 導入 db_adapter 來更新 KK幣（需要確定實現方式）
            try:
                from db_adapter import set_user_field, get_user_field
                
                # 獲取當前 KK幣
                current_kkcoin = get_user_field(user.id, "kkcoin") or 0
                new_kkcoin = int(current_kkcoin) + 2000
                
                # 更新 KK幣
                set_user_field(user.id, "kkcoin", new_kkcoin)
                
                logger.info(f"✅ [on_reaction_add] {user.name} 獲得 2000 KK幣，現在共有 {new_kkcoin} KK幣")
                
                # 發送 DM 通知用戶
                try:
                    dm_embed = discord.Embed(
                        title="⭐ 評分獎勵",
                        description="感謝你給動畫通知評分！",
                        color=discord.Color.gold()
                    )
                    dm_embed.add_field(
                        name="獲得獎勵",
                        value="💰 +2000 KK幣",
                        inline=False
                    )
                    dm_embed.add_field(
                        name="目前餘額",
                        value=f"💵 {new_kkcoin} KK幣",
                        inline=False
                    )
                    await user.send(embed=dm_embed)
                except discord.Forbidden:
                    logger.warning(f"⚠️ [on_reaction_add] 無法發送 DM 給 {user.name}（關閉了 DM）")
                
            except ImportError:
                logger.warning("⚠️ [on_reaction_add] db_adapter 未找到，無法獎勵 KK幣")
            except Exception as e:
                logger.error(f"❌ [on_reaction_add] 獎勵 KK幣失敗: {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"❌ [on_reaction_add] 處理反應失敗: {e}", exc_info=True)
    
    async def fetch_new_anime_from_api(self) -> Optional[List[Dict]]:
        """
        從 Bahamut API 獲取今天更新的動畫集
        
        注意：API 返回的列表包含多個日期的動畫，我們只需要今天的
        
        Returns:
            今天的集列表，或 None 如果失敗
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
                    # API 返回結構：{"data": {"newAnime": {"date": [...], "popular": [...]}}}
                    new_anime = data.get("data", {}).get("newAnime", {})
                    # newAnime 是字典，我們需要 'date' 鍵中的列表
                    all_episodes = new_anime.get("date", []) if isinstance(new_anime, dict) else []
                    
                    # 篩選只取今天的動畫
                    today = datetime.now().strftime("%m/%d")
                    today_episodes = [
                        ep for ep in all_episodes 
                        if isinstance(ep, dict) and ep.get("upTime", "").startswith(today)
                    ]
                    
                    logger.info(f"🔍 API fetch: 獲得 {len(all_episodes)} 集，其中今天的 {len(today_episodes)} 集 (upTime: {today})")
                    return today_episodes
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ API timeout ({API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching anime from API: {e}", exc_info=True)
            return None

    def _episode_in_current_check_window(self, episode: Dict, now: datetime) -> bool:
        up_date = episode.get("upTime", "").strip()
        up_time = episode.get("upTimeHours", "").strip()
        if not up_date or not up_time:
            return False

        try:
            episode_dt = datetime.strptime(f"{datetime.now().year}/{up_date} {up_time}", "%Y/%m/%d %H:%M")
        except ValueError:
            return False

        window_start = now - timedelta(minutes=50)
        window_end = now - timedelta(minutes=5)
        return window_start <= episode_dt <= window_end

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

    def _truncate_text(self, text: str, limit: int = 240) -> str:
        return text if len(text) <= limit else text[:limit].rstrip() + '...'

    async def generate_anime_embed(self, episode: Dict) -> discord.Embed:
        """
        生成單個集的 Discord Embed
        
        Args:
            episode: 集信息字典
        
        Returns:
            格式化的 discord.Embed
        """
        anime_name = episode.get("title", "Unknown")
        volume = episode.get("volume", "")
        cover_url = episode.get("cover", "")
        anime_sn = episode.get("animeSn", "")
        
        # 構建動畫連結 (Bahamut 動畫連結)
        anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}" if anime_sn else "https://ani.gamer.com.tw"
        
        web_details = await self.fetch_anime_web_details(str(anime_sn)) if anime_sn else {}
        genres = web_details.get("genres", [])
        summary = web_details.get("summary")
        
        # 獲取標籤信息
        highlight_tag = episode.get("highlightTag", {})
        tag_parts = []
        
        if genres:
            tag_parts.extend([f"#{tag}" for tag in genres[:6]])
        elif highlight_tag.get("bilingual"):
            tag_parts.append("🗣️ 雙語")

        edition = highlight_tag.get("edition", "").strip()
        if edition:
            tag_parts.append(f"📺 {edition}")
        
        tags_str = " | ".join(tag_parts) if tag_parts else "無特殊標籤"
        
        description_text = f"**集數：{volume}**"
        if summary:
            description_text += "\n" + self._truncate_text(summary, 280)
        
        embed = discord.Embed(
            title=f"🎬 {anime_name}",
            description=description_text,
            url=anime_url,
            color=discord.Color.from_rgb(178, 108, 196),
            timestamp=datetime.utcnow()
        )
        
        if cover_url:
            embed.set_image(url=cover_url)
        
        embed.add_field(
            name="📌 標籤",
            value=tags_str,
            inline=False
        )
        
        if summary:
            embed.add_field(
                name="📝 劇情簡介",
                value=self._truncate_text(summary, 280),
                inline=False
            )
        
        embed.add_field(
            name="⭐ 點擊反應留下評價吧",
            value="不管點什麼表情都沒關係啦，正評負評都可以～\n評分成功會獲得 💰 2000 KK幣喔！",
            inline=False
        )
        
        embed.set_footer(text="Bahamut 動畫追蹤 | 🔕 反應留評獲獎勵")
        return embed
    
    @tasks.loop(minutes=1)
    async def check_new_anime(self):
        """
        根據日程表智能檢查，在預期時刻 +1 分鐘時發起檢查
        
        工作流程：
        1. 獲取 newAnimeSchedule（各星期的預期時刻表）
        2. 計算出今天和明天的所有預期時刻
        3. 當前時刻匹配到預期時刻 +1 分鐘時，發起 API 檢查
        4. 適應未來任何時段的更新時間
        """
        now = datetime.now()
        
        try:
            # 獲取日程表
            schedule = await self._get_anime_schedule()
            if not schedule:
                # 日程表為空，跳過
                return
            
            # 獲取當前時刻應該檢查的集合
            expected_check_times = self._get_expected_check_times(schedule, now)
            
            # 檢查當前時刻是否應該檢查（預期時刻 +1 分鐘）
            current_hm = now.strftime("%H:%M")
            should_check = current_hm in expected_check_times
            
            if not should_check:
                # 不是預期時刻，跳過
                return
            
            logger.info(f"📺 [check_new_anime] ========== 智能日程檢查 ({current_hm}) ==========")
            
            # 取得頻道
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if not channel:
                logger.error(f"❌ [check_new_anime] 動畫頻道 {ANIME_CHANNEL_ID} 未找到")
                return
            
            # 獲取最新動畫數據
            logger.info("📺 [check_new_anime] 正在從 API 獲取動畫數據...")
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                logger.warning("⚠️ [check_new_anime] 無法從 API 獲取數據")
                return
            
            logger.info(f"📺 [check_new_anime] 獲得 {len(episodes)} 集")
            
            # 檢查 Bootstrap 狀態
            bootstrap_status = self.db.is_bootstrap_completed()
            logger.info(f"📺 [check_new_anime] Bootstrap 狀態: {bootstrap_status}")
            
            if not bootstrap_status:
                # 首次運行：記錄所有現存集，不發送通知
                logger.info("🚀 [check_new_anime] 首次運行，執行 bootstrap...")
                self.db.bootstrap_add_all(episodes)
                self.db.mark_bootstrap_completed()
                self.bootstrap_completed = True
                
                embed = discord.Embed(
                    title="✅ 動畫追蹤已啟動",
                    description="已記錄現有集合。之後會通知新上架的集。",
                    color=discord.Color.green()
                )
                logger.info("📺 [check_new_anime] 發送 bootstrap 確認 embed")
                await channel.send(embed=embed)
                logger.info("✅ [check_new_anime] Bootstrap 完成，embed 已發送")
                return
            
            # 正常運行：檢查新集
            new_episodes = []
            for ep in episodes:
                video_sn = ep.get("videoSn")
                if not video_sn or self.db.is_notified(video_sn):
                    continue
                if not self._episode_in_current_check_window(ep, now):
                    logger.debug(f"📺 Skip episode outside current window: {ep.get('title')} {ep.get('upTime')} {ep.get('upTimeHours')}")
                    continue
                new_episodes.append(ep)
            
            if not new_episodes:
                logger.info("⏭️ No new episodes found")
                return
            
            # 發送新集通知
            logger.info(f"🆕 Found {len(new_episodes)} new episodes")
            for ep in new_episodes:
                try:
                    embed = await self.generate_anime_embed(ep)
                    message = await channel.send(embed=embed)

                    # 記錄已通知
                    self.db.add_notified(
                        video_sn=ep.get("videoSn"),
                        anime_sn=ep.get("animeSn"),
                        anime_name=ep.get("title", "Unknown"),
                        volume=ep.get("volume", ""),
                        cover_url=ep.get("cover", "")
                    )
                    
                    # 避免 Discord 限流（200ms 間隔）
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.error(f"❌ Error sending embed: {e}")
                    await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"❌ Error in check_new_anime: {e}", exc_info=True)
    
    async def _get_anime_schedule(self) -> dict:
        """從 API 獲取日程表 (newAnimeSchedule)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as response:
                    if response.status != 200:
                        logger.error(f"❌ API returned status {response.status}")
                        return {}
                    
                    data = await response.json()
                    schedule = data.get("data", {}).get("newAnimeSchedule", {})
                    return schedule
        except Exception as e:
            logger.error(f"❌ Error fetching schedule: {e}")
            return {}
    
    def _get_expected_check_times(self, schedule: dict, now: datetime) -> list:
        """
        計算出包含今天和明天的所有預期檢查時刻（預期時刻 +1 分鐘）
        
        Returns:
            預期檢查時刻列表，格式為 ["HH:MM", ...]
        """
        check_times = set()
        
        # 計算今天和明天的星期（1-7）
        weekday_today = (now.weekday() + 1) % 7
        if weekday_today == 0:
            weekday_today = 7  # Sunday is 7
        weekday_tomorrow = (weekday_today % 7) + 1
        
        # 從日程表中獲取時刻
        for weekday in [str(weekday_today), str(weekday_tomorrow)]:
            for anime_info in schedule.get(weekday, []):
                schedule_time = anime_info.get("scheduleTime", "")  # 格式: "22:00"
                if schedule_time:
                    try:
                        # 解析時間並加上 1 分鐘
                        hour, minute = map(int, schedule_time.split(":"))
                        check_minute = minute + 1
                        check_hour = hour
                        
                        # 處理進位
                        if check_minute >= 60:
                            check_minute = 0
                            check_hour = (hour + 1) % 24
                        
                        check_time_str = f"{check_hour:02d}:{check_minute:02d}"
                        check_times.add(check_time_str)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to parse schedule time '{schedule_time}': {e}")
        
        logger.debug(f"📺 Expected check times: {sorted(check_times)}")
        return sorted(list(check_times))
    
    @check_new_anime.before_loop
    async def before_check_new_anime(self):
        """在第一次循環前等待 bot 就緒"""
        logger.info("📺 [before_check_new_anime] 等待 bot 就緒...")
        await self.bot.wait_until_ready()
        logger.info(f"✅ [before_check_new_anime] Bot 已就緒！")
        logger.info(f"📺 [before_check_new_anime] Bot guilds 數量: {len(self.bot.guilds)}")
        logger.info(f"📺 [before_check_new_anime] 尋找目標頻道 {ANIME_CHANNEL_ID}...")
        
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if channel:
            logger.info(f"✅ [before_check_new_anime] 找到頻道: {channel.name} (Guild: {channel.guild.name})")
        else:
            logger.error(f"❌ [before_check_new_anime] 未找到頻道 {ANIME_CHANNEL_ID}")
            # 列出所有頻道以供診斷
            for guild in self.bot.guilds:
                logger.info(f"📋 Guild: {guild.name}")
                for ch in guild.channels[:5]:  # 只列前 5 個
                    logger.info(f"   - {ch.name} (ID: {ch.id})")

    @app_commands.command(name="anime_test", description="測試動畫通知 - 顯示最近的動畫集")
    async def anime_test(self, interaction: discord.Interaction):
        """測試指令：獲取最近的動畫數據並在當前頻道發送"""
        try:
            await interaction.response.defer()  # 延遲回應，因為可能需要時間
            
            logger.info(f"📺 [anime_test] 被 {interaction.user} 在頻道 {interaction.channel} 調用")
            
            # 獲取最新動畫數據
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                await interaction.followup.send("❌ 無法從 API 獲取動畫數據")
                logger.warning("📺 [anime_test] API 返回空結果")
                return
            
            logger.info(f"📺 [anime_test] 獲得 {len(episodes)} 集")
            
            # 生成並發送前 3 集的 embed
            sent_count = 0
            for ep in episodes[:3]:
                try:
                    embed = await self.generate_anime_embed(ep)
                    message = await interaction.followup.send(embed=embed)
                    
                    sent_count += 1
                    await asyncio.sleep(0.2)  # 避免限流
                except Exception as e:
                    logger.error(f"❌ [anime_test] 發送 embed 失敗: {e}")
            
            logger.info(f"✅ [anime_test] 成功發送 {sent_count} 個 embed")
            
        except Exception as e:
            logger.error(f"❌ [anime_test] 指令執行失敗: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ 錯誤: {str(e)[:100]}")
            except:
                pass
    

async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式"""
    await bot.add_cog(AnimeTracker(bot))
    logger.info("✅ AnimeTracker Cog 已加載")
