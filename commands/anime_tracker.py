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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# 配置
ANIME_CHANNEL_ID = 1252204317453324333  # 動畫通知頻道
ANIME_DB_PATH = Path("./uibot_anime.db")  # 獨立的動畫追蹤數據庫
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
                field.name == "⭐ 評分獲獎勵" 
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
    
    def generate_anime_embed(self, episode: Dict) -> discord.Embed:
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
        anime_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={anime_sn}" if anime_sn else "https://ani.gamer.com.tw"
        
        # 獲取標籤信息
        highlight_tag = episode.get("highlightTag", {})
        tag_parts = []
        
        if highlight_tag.get("bilingual"):
            tag_parts.append("🗣️ 雙語")
        
        edition = highlight_tag.get("edition", "").strip()
        if edition:
            tag_parts.append(f"📺 {edition}")
        
        # 如果有標籤則顯示，否則不顯示
        tags_str = " | ".join(tag_parts) if tag_parts else "無特殊標籤"
        
        embed = discord.Embed(
            title=f"🎬 {anime_name}",
            description=f"**集數：{volume}**",
            url=anime_url,  # 點擊標題可到動畫頁面
            color=discord.Color.from_rgb(178, 108, 196),  # Bahamut 紫色
            timestamp=datetime.utcnow()
        )
        
        if cover_url:
            embed.set_image(url=cover_url)
        
        # 添加標籤
        embed.add_field(
            name="📌 標籤",
            value=tags_str,
            inline=False
        )
        
        # 添加評分提示
        embed.add_field(
            name="⭐ 評分獲獎勵",
            value="點擊下方表情反應來評分此集！評分成功可獲得 2000 KK幣",
            inline=False
        )
        
        embed.set_footer(text="Bahamut 動畫追蹤 | 點擊下方表情反應評分")
        return embed
    
    @tasks.loop(minutes=1)
    async def check_new_anime(self):
        """
        每分鐘檢查一次，但只在整點 10 分和 40 分執行實際檢查
        
        時間安排：
        - :10 分：檢查整點更新（允許 10 分鐘的 API 延遲）
        - :40 分：檢查整點 30 分的更新（允許 10 分鐘的 API 延遲）
        
        動畫通常在整點 (:00) 和整點 30 分 (:30) 時更新
        """
        now = datetime.now()
        
        # 只在 10 分和 40 分時執行檢查
        if now.minute in [10, 40]:
            try:
                logger.info(f"📺 [check_new_anime] ========== 定時檢查開始 ({now.strftime('%H:%M:%S')}) ==========")
                
                # 取得頻道
                channel = self.bot.get_channel(ANIME_CHANNEL_ID)
                if not channel:
                    # 診斷：列出所有可用的頻道
                    all_channels = []
                    for guild in self.bot.guilds:
                        for ch in guild.channels:
                            if hasattr(ch, 'id'):
                                all_channels.append(f"{ch.name} (ID:{ch.id})")
                    logger.error(f"❌ [check_new_anime] 動畫頻道 {ANIME_CHANNEL_ID} 未找到")
                    logger.error(f"📋 可用頻道前 10 個: {', '.join(all_channels[:10])}")
                    return
                
                # 獲取最新動畫數據
                logger.info("📺 [check_new_anime] 當前頻道: " + channel.name)
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
                    if video_sn and not self.db.is_notified(video_sn):
                        new_episodes.append(ep)
                
                if not new_episodes:
                    logger.info("⏭️ No new episodes found")
                    return
                
                # 發送新集通知
                logger.info(f"🆕 Found {len(new_episodes)} new episodes")
                for ep in new_episodes:
                    try:
                        embed = self.generate_anime_embed(ep)
                        message = await channel.send(embed=embed)
                        
                        # 添加評分表情反應
                        reactions = ["⭐", "😍", "👍", "🔥"]
                        for emoji in reactions:
                            try:
                                await message.add_reaction(emoji)
                                await asyncio.sleep(0.1)  # 避免 API 限流
                            except Exception as e:
                                logger.warning(f"⚠️ 添加反應 {emoji} 失敗: {e}")
                        
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
                    embed = self.generate_anime_embed(ep)
                    message = await interaction.followup.send(embed=embed)
                    
                    # 添加評分表情反應
                    reactions = ["⭐", "😍", "👍", "🔥"]
                    for emoji in reactions:
                        try:
                            await message.add_reaction(emoji)
                            await asyncio.sleep(0.1)  # 避免 API 限流
                        except Exception as e:
                            logger.warning(f"⚠️ 添加反應 {emoji} 失敗: {e}")
                    
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
    


async def setup(bot):
    """設置 AnimeTracker Cog"""
    import os
    log_file = "/tmp/anime_tracker_setup.log"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n[SETUP_START] {datetime.now().isoformat()}\n")
        f.write(f"[SETUP] 開始設置 AnimeTracker Cog...\n")
        f.flush()
    
    logger.info("📺 [setup] 開始設置 AnimeTracker Cog...")
    try:
        cog = AnimeTracker(bot)
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[SETUP] Cog 實例已創建\n")
            f.flush()
        
        await bot.add_cog(cog)
        logger.info("✅ [setup] AnimeTracker Cog 已添加到 bot")
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[SETUP] Cog 已添加到 bot\n")
            f.write(f"[SETUP] task_started: {cog.task_started}, bot.is_ready(): {bot.is_ready()}\n")
            f.flush()
        
        # 嘗試啟動任務（如果 cog_load 沒有被調用）
        if not cog.task_started and bot.is_ready():
            logger.info("📺 [setup] Bot 已就緒，直接啟動任務...")
            if not cog.check_new_anime.is_running():
                cog.check_new_anime.start()
                cog.task_started = True
                logger.info("✅ [setup] AnimeTracker 任務已啟動")
                
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"[SETUP] 任務已啟動\n")
                    f.flush()
        else:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[SETUP] 任務未啟動 - started:{cog.task_started}, bot_ready:{bot.is_ready()}\n")
                f.flush()
            logger.info(f"📺 [setup] 任務狀態 - started:{cog.task_started}, bot_ready:{bot.is_ready()}")
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[SETUP_END] 成功\n")
            f.flush()
            
    except Exception as e:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[SETUP_ERROR] {str(e)}\n")
            f.write(f"[SETUP] Traceback:\n")
            import traceback
            f.write(traceback.format_exc())
            f.flush()
        logger.error(f"❌ [setup] AnimeTracker 設置失敗: {e}", exc_info=True)
        raise



# 必要的 setup() 函數，讓 Discord.py 可以加載此 Cog
async def setup(bot: commands.Bot):
    """加載 AnimeTracker Cog"""
    try:
        logger.info("📺 setup() 開始加載 AnimeTracker Cog...")
        await bot.add_cog(AnimeTracker(bot))
        logger.info("✅ AnimeTracker Cog 加載成功！")
    except Exception as e:
        logger.error(f"❌ setup() 加載 Cog 失敗: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式"""
    await bot.add_cog(AnimeTracker(bot))
    logger.info("✅ AnimeTracker Cog 已加載")
