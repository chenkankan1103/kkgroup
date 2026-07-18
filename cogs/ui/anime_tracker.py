"""
Bahamut 動畫追蹤 Cog - 自動通知新上架集數
已重構為三個模組：Push/Core、Schedule Tracker、Ranking Stats
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import aiohttp
import sqlite3
import json
import re
import html
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from zoneinfo import ZoneInfo  # Python 3.9+, 正確的時區處理
import time
from urllib.parse import quote  # 用於生成 QuickChart URL
from shared.utils.view_registry import PersistentViewBase

# 台灣時區
TW_TZ = ZoneInfo('Asia/Taipei')

# 配置
ANIME_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"  # 統一使用主數據庫，所有表在同一個 user_data.db 中
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # 秒

# 表名與欄位
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"
ANIME_DETAILS_TABLE = "anime_details"  # 永恆快取動畫詳細信息
ANIME_STATS_TABLE = "anime_statistics"  # 動畫統計數據（觀看人數、評分趨勢等）
EPISODE_STATS_TABLE = "episode_statistics"  # 每集統計數據
ANIME_MESSAGES_TABLE = "anime_messages"  # 消息 ID 追蹤（用於 bot 重啟時恢復 view）
ANIME_VOTES_TABLE = "anime_votes"  # 匿名投票結果
ANIME_REWARDS_TABLE = "anime_rewards"  # KK幣獎勵追踪（防止重複發放）
ANIME_CHECK_HISTORY_TABLE = "anime_check_history"  # 每日時刻檢查歷史（防止重複檢查，解決 Bot 重啟問題）
ANIME_WEEKLY_SCHEDULE_TABLE = "anime_weekly_schedule"  # 週表：每週一自動拉取的完整時程表（減少 API 調用）

# 導入自定義模組
from .push_core import AnimePushCore, AnimeDatabase, ANIME_CHANNEL_ID
from .schedule_tracker import AnimeScheduleTracker
from .ranking_stats import RankingStats


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤主 Cog"""

    def __init__(self, bot: commands.Bot):
        print("[ANIME_INIT_START] 🎬 AnimeTracker.__init__ 開始執行")
        import sys
        sys.stdout.flush()

        import logging
        logger = logging.getLogger(__name__)
        logger.info("=" * 50)
        logger.info("📺 [AnimeTracker.__init__] 開始初始化")
        self.bot = bot
        try:
            self.db = AnimeDatabase(ANIME_DB_PATH)
            logger.info(f"✅ [AnimeTracker.__init__] 數據庫已初始化: {ANIME_DB_PATH}")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.__init__] 數據庫初始化失敗: {e}", exc_info=True)
            raise

        # 初始化三個模組
        self.push_core = AnimePushCore(ANIME_DB_PATH)
        self.schedule_tracker = AnimeScheduleTracker(ANIME_DB_PATH)
        self.ranking_stats = RankingStats(ANIME_DB_PATH)

        # 設置相互依賴
        self.push_core.set_bot_and_db(bot, self.db)
        self.schedule_tracker.set_dependencies(bot, self.db, self.push_core)
        self.ranking_stats.set_dependencies(bot, self.db)

        # 設定 View 生成工廠（解決循環導入問題）
        self.push_core.set_view_factory(self.generate_anime_view)

        self.task_started = False
        self.bootstrap_completed = False
        self.last_weekly_stats_sent = None

    # ==================== CULC 生命週期方法 ====================

    async def cog_load(self):
        """Cog 加載時啟動任務"""
        import sys
        import time
        start_time = time.perf_counter()
        print("[COG_LOAD_START] 🎬 cog_load() 開始執行", flush=True)
        sys.stdout.flush()

        import logging
        logger = logging.getLogger(__name__)

        logger.info("=" * 50)
        logger.info("🎬 [AnimeTracker.cog_load] cog_load() 被調用")

        try:
            # 恢復舊消息的視圖 - 在 bot 重啟時重新註冊所有永久視圖
            print("[COG_LOAD] 嘗試恢復舊消息 view...", flush=True)
            await self._restore_old_message_views()
            print("[COG_LOAD] ✅ 舊消息 view 恢復完成", flush=True)

            # 如果週表為空，立即拉取（解決首次部署/非禮拜天重啟問題）
            print("[COG_LOAD] 檢查週表是否需要初始化...", flush=True)
            await self._init_weekly_schedule_if_empty()
            print("[COG_LOAD] ✅ 週表初始化檢查完成", flush=True)

            # 補推：若 bot 重啟前有未推送的動畫，啟動時補發
            print("[COG_LOAD] 檢查是否有錯過的動畫推送...", flush=True)
            await self._catchup_missed_pushes()
            print("[COG_LOAD] ✅ 補推檢查完成", flush=True)

            # 啟動週表刷新任務
            print("[COG_LOAD] 檢查 refresh_weekly_schedule 任務狀態", flush=True)
            if not self.refresh_weekly_schedule.is_running():
                print("[COG_LOAD] ✅ 啟動 refresh_weekly_schedule 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 任務")
                try:
                    self.refresh_weekly_schedule.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] refresh_weekly_schedule 已啟動 (is_running={self.refresh_weekly_schedule.is_running()})")
                    print("[COG_LOAD] ✅ refresh_weekly_schedule 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 refresh_weekly_schedule 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 refresh_weekly_schedule...")
                        self.refresh_weekly_schedule.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，refresh_weekly_schedule 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，refresh_weekly_schedule 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] refresh_weekly_schedule 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ refresh_weekly_schedule 已在運行", flush=True)

            # 啟動精准派發器（背景任務，非 tasks.loop）
            print("[COG_LOAD] 啟動精準排程派發器", flush=True)
            logger.info("🚀 [AnimeTracker.cog_load] 啟動精準排程派發器")
            self._dispatcher_task = asyncio.create_task(self._schedule_dispatcher())
            logger.info("✅ [AnimeTracker.cog_load] 精準排程派發器已啟動")
            print("[COG_LOAD] ✅ 精準排程派發器已啟動", flush=True)

            # 啟動定期補推任務（每 5 分鐘檢查最近 10 分鐘內漏推項目並真正發送）
            print("[COG_LOAD] 啟動定期補推檢查任務", flush=True)
            logger.info("🚀 [AnimeTracker.cog_load] 啟動定期補推檢查任務")
            try:
                self._catchup_check_task = asyncio.create_task(self._periodic_catchup_check())
                # 給任務一點時間啟動，檢查是否有異常
                await asyncio.sleep(0.1)
                if self._catchup_check_task.done():
                    exc = self._catchup_check_task.exception()
                    if exc:
                        logger.error(f"❌ [AnimeTracker.cog_load] _periodic_catchup_check 任務立即失敗: {exc}", exc_info=True)
                        print(f"[COG_LOAD_ERROR] _periodic_catchup_check 任務立即失敗: {exc}", flush=True)
                    else:
                        logger.warning(f"⚠️ [AnimeTracker.cog_load] _periodic_catchup_check 任務意外結束")
                else:
                    logger.info("✅ [AnimeTracker.cog_load] 定期補推檢查任務已啟動並運行中")
                    print("[COG_LOAD] ✅ 定期補推檢查任務已啟動並運行中", flush=True)
            except Exception as e:
                logger.error(f"❌ [AnimeTracker.cog_load] 創建 _periodic_catchup_check 任務失敗: {e}", exc_info=True)
                print(f"[COG_LOAD_ERROR] 創建 _periodic_catchup_check 任務失敗: {e}", flush=True)
                raise

            # 啟動週期統計同步任務
            print("[COG_LOAD] 檢查 sync_episode_stats 任務狀態", flush=True)
            if not self.sync_episode_stats.is_running():
                print("[COG_LOAD] ✅ 啟動 sync_episode_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 sync_episode_stats 任務")
                try:
                    self.sync_episode_stats.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] sync_episode_stats 已啟動 (is_running={self.sync_episode_stats.is_running()})")
                    print("[COG_LOAD] ✅ sync_episode_stats 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啨動 sync_episode_stats 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啨動 sync_episode_stats 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 sync_episode_stats...")
                        self.sync_episode_stats.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，sync_episode_stats 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，sync_episode_stats 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] sync_episode_stats 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ sync_episode_stats 已在運行", flush=True)

            print("[COG_LOAD_END] ✅ cog_load() 執行完成", flush=True)
            sys.stdout.flush()
            logger.info("✅ [AnimeTracker.cog_load] 任務啟動完成")

        except Exception as e:
            import traceback
            error_msg = f"❌ [cog_load] 執行失敗: {e}"
            print(f"[COG_LOAD_ERROR] {error_msg}", flush=True)
            print(f"[COG_LOAD_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
            logger.error(error_msg, exc_info=True)
            raise
        elapsed = time.perf_counter() - start_time
        logger.info(f"⏱️ [AnimeTracker.cog_load] 總耗時: {elapsed:.2f} 秒")
        print(f"[COG_LOAD_TIMING] 總耗時: {elapsed:.2f} 秒", flush=True)
        logger.info("=" * 50)

    def cog_unload(self):
        """Cog 卸載時停止任務"""
        logger = logging.getLogger(__name__)
        logger.info("=" * 50)
        logger.info("🛑 [AnimeTracker.cog_unload] cog_unload() 被調用")
        try:
            # ✅ check_new_anime 已移除

            if self.refresh_weekly_schedule.is_running():
                self.refresh_weekly_schedule.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] refresh_weekly_schedule 已停止")

            # 停止精準排程派發器（背景任務，非 tasks.loop）
            if hasattr(self, '_dispatcher_task') and not self._dispatcher_task.done():
                self._dispatcher_task.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] 精準排程派發器已停止")

            # 停止定期補推檢查任務
            if hasattr(self, '_catchup_check_task') and not self._catchup_check_task.done():
                self._catchup_check_task.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] 定期補推檢查任務已停止")

            if self.sync_episode_stats.is_running():
                self.sync_episode_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] sync_episode_stats 已停止")

        except Exception as e:
            logger.error(f"❌ [AnimeTracker.cog_unload] 任務停止失敗: {e}", exc_info=True)
        logger.info("=" * 50)

    # ==================== 核心功能方法（委託給相應模組） ====================

    # Push/Core 相關方法
    async def _check_and_send_anime(self, scheduled_time_str: str, channel: discord.TextChannel) -> bool:
        """檢查並發送動畫推送 - 委託給 PushCore"""
        return await self.push_core._check_and_send_anime(scheduled_time_str, channel)

    async def generate_anime_embed(self, episode: dict) -> Optional[discord.Embed]:
        """生成動畫 embed - 委託給 PushCore"""
        return await self.push_core.generate_anime_embed(episode)

    async def generate_anime_view(self, episode: dict) -> Optional[discord.ui.View]:
        """生成動畫視圖 - 創建投票和評論按鈕 + 動畫頁/觀看連結"""
        try:
            # 只有在有必要的資料時才生成視圖
            video_sn = episode.get("videoSn")
            anime_sn = episode.get("animeSn")
            if not video_sn or not anime_sn:
                return None

            # 創建投票視圖
            vote_view = self.AnimeVoteView(episode, self)

            # 添加原有的連結按鈕
            anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
            vote_view.add_item(discord.ui.Button(label="🔗 動畫頁", url=anime_url, style=discord.ButtonStyle.link))

            video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}"
            vote_view.add_item(discord.ui.Button(label="▶️ 觀看", url=video_url, style=discord.ButtonStyle.link))

            return vote_view
        except Exception as e:
            logger.error(f"❌ [generate_anime_view] Failed to generate view: {e}", exc_info=True)
            return None

    async def send_anime_push(self, scheduled_time: str, channel_id: int, day_of_week: int = None, week_start_date: str = None) -> bool:
        """發送動畫推送 - 委託給 PushCore"""
        return await self.push_core.send_anime_push(scheduled_time, channel_id, day_of_week, week_start_date)

    # Schedule Tracker 相關方法
    async def _get_anime_schedule(self) -> Optional[Dict]:
        """從 API 獲取日程表 - 委託給 ScheduleTracker"""
        return await self.schedule_tracker._get_anime_schedule()

    def _get_weekday_name(self, weekday_num: int) -> str:
        """獲取星期名稱 - 委託給 ScheduleTracker"""
        return self.schedule_tracker._get_weekday_name(weekday_num)

    # Ranking Stats 相關方法
    async def record_vote(self, video_sn: int, anime_sn: int, message_id: int, vote_type: str, comment: str = None, user_hash: str = None):
        """記錄投票 - 委託給 RankingStats"""
        await self.ranking_stats.record_vote(video_sn, anime_sn, message_id, vote_type, comment, user_hash)

    def get_vote_stats(self, message_id: int) -> Dict:
        """獲取投票統計 - 委託給 RankingStats"""
        return self.ranking_stats.get_vote_stats(message_id)

    def get_vote_comments(self, message_id: int, limit: int = 5) -> List[str]:
        """獲取評論 - 委託給 RankingStats"""
        return self.ranking_stats.get_vote_comments(message_id, limit)

    def get_weekly_vote_stats(self) -> Dict[int, Dict]:
        """獲取週投票統計 - 委託給 RankingStats"""
        return self.ranking_stats.get_weekly_vote_stats()

    def record_reward(self, user_id: int, message_id: int, reward_type: str, reward_amount: int) -> bool:
        """記錄獎勵 - 委託給 RankingStats"""
        return self.ranking_stats.record_reward(user_id, message_id, reward_type, reward_amount)

    def is_reward_already_given(self, user_id: int, message_id: int, reward_type: str) -> bool:
        """檢查獎勵是否已發放 - 委託給 RankingStats"""
        return self.ranking_stats.is_reward_already_given(user_id, message_id, reward_type)

    async def generate_ranking_embed(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        period_label: str = "本季"
    ) -> Optional[discord.Embed]:
        """生成排名 embed - 委託給 RankingStats"""
        return await self.ranking_stats.generate_ranking_embed(start_time, end_time, period_label)

    # ==================== 資料庫操作方法（直接Delegation to AnimeDatabase） ====================

    def is_notified(self, video_sn: int) -> bool:
        """檢查是否已通知過"""
        return self.db.is_notified(video_sn)

    def add_notified(self, video_sn: int, anime_sn: int, anime_name: str, volume: str, cover_url: str):
        """添加已通知記錄"""
        self.db.add_notified(video_sn, anime_sn, anime_name, volume, cover_url)

    def get_anime_details(self, anime_sn: int) -> Optional[Dict]:
        """獲取動畫詳細信息"""
        return self.db.get_anime_details(anime_sn)

    def cache_anime_details(self, anime_sn: int, title: str, content: str, tags: List[str], popular: int, score: float):
        """快取動畫詳細信息"""
        self.db.cache_anime_details(anime_sn, title, content, tags, popular, score)

    def record_episode_stats(self, video_sn: int, anime_sn: int, episode_num: str, views: int, score: float):
        """記錄每集統計"""
        self.db.record_episode_stats(video_sn, anime_sn, episode_num, views, score)

    def get_top_anime_by_views(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """獲取觀看次數最多的動畫排行"""
        return self.db.get_top_anime_by_views(limit, start_time, end_time)

    def get_multi_episode_anime_for_chart(
        self,
        limit: int = 10,
        min_episodes: int = 1,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """獲取多集動畫用於圖表"""
        return self.db.get_multi_episode_anime_for_chart(limit, min_episodes, start_time, end_time)

    def get_weekly_schedule(self, week_start_date: str) -> List[Dict]:
        """獲取週表"""
        return self.db.get_weekly_schedule(week_start_date)

    def save_weekly_schedule(self, week_start_date: str, schedule_data: List[Dict]) -> bool:
        """保存週表"""
        return self.db.save_weekly_schedule(week_start_date, schedule_data)

    def get_today_schedule(self) -> List[Dict]:
        """獲取今日時程表"""
        return self.db.get_today_schedule()

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記時段已推送"""
        return self.db.mark_time_pushed(week_start_date, day_of_week, scheduled_time)

    def is_time_checked_today(self, scheduled_time: str, check_date=None) -> bool:
        """檢查今日是否已檢查過時段"""
        return self.db.is_time_checked_today(scheduled_time, check_date)

    def mark_time_checked(self, check_date=None) -> bool:
        """標記時段已檢查"""
        return self.db.mark_time_checked(scheduled_time, check_date)

    def save_message_info(self, message_id: int, video_sn: int, anime_sn: int, anime_name: str, channel_id: int) -> bool:
        """保存消息資訊"""
        return self.db.save_message_info(message_id, video_sn, anime_sn, anime_name, channel_id)

    def get_unviewed_messages(self) -> List[Dict]:
        """獲取未設定視圖的消息"""
        return self.db.get_unviewed_messages()

    def is_bootstrap_completed(self) -> bool:
        """檢查是否完成引導"""
        return self.db.is_bootstrap_completed()

    def mark_bootstrap_completed(self):
        """標記引導完成"""
        self.db.mark_bootstrap_completed()

    # ==================== 視圖恢復和啟動方法 ====================

    async def _restore_old_message_views(self):
        """Bot 重啟時恢復舊消息的視圖"""
        try:
            # 獲取所有保存的消息資訊
            messages = self.get_unviewed_messages()

            for msg_info in messages:
                try:
                    # 重新生成視圖並註冊到 bot
                    # 注意：這裡需要重新從 API 獲取 episode 數據來生成正確的視圖
                    # 為簡化起見，我們先註冊一個基本的視圖，實際內容會在用戶互動時更新
                    # 時重新生成
                    # get_unviewed_messages 返回 snake_case keys (video_sn, anime_sn, etc.)
                    video_sn = msg_info.get('video_sn') or msg_info.get('videoSn')

                    # 從資料庫獲取動畫資訊
                    anime_info = self.db.get_anime_details_by_videosn(video_sn)
                    if anime_info:
                        # 創建一個假的 episode 字典用於生成視圖
                        episode = {
                            'videoSn': video_sn,
                            'animeSn': anime_info.get('animeSn'),
                            'title': anime_info.get('title', 'Unknown'),
                            'volume': anime_info.get('volume', ''),
                            'cover': anime_info.get('cover_url', '')
                        }

                        # 生成視圖
                        view = await self.generate_anime_view(episode)
                        if view:
                            self.bot.add_view(view)

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"❌ [_restore_old_message_views] 復原視圖失敗 for message {msg_info.get('messageId')}: {e}")
                    continue

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [_restore_old_message_views] 失敗: {e}")

    async def _catchup_missed_pushes(self):
        """Bot 重啟時補推今日已過時刻但尚未推送的動畫（真正發送，不再只標記）

        修復：原實作只在重啟時把過時刻標記為 pushed=1 卻不實際發送，導致
        重啟期間錯過的動畫永久遺失。現在改為實際呼叫 send_anime_push 補發。
        send_anime_push 內部已會在 API 成功後標記 pushed=1，故此處不重複標記。
        """
        logger = logging.getLogger(__name__)
        try:
            await self.bot.wait_until_ready()
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")
            day_of_week = (now.weekday() + 1) % 7 or 7
            today_schedule = self.get_today_schedule()
            if not today_schedule:
                logger.info("ℹ️ [_catchup_missed_pushes] 今日週表為空，無需補推")
                return

            # 找出今天已過時刻但尚未標記為已推送的項目
            missed = []
            for item in today_schedule:
                if item['pushed']:
                    continue
                try:
                    sched_dt = datetime.strptime(item['scheduled_time'], "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                    )
                    if (now - sched_dt).total_seconds() >= 0:  # 已過或當前時刻
                        missed.append((item, sched_dt))
                except ValueError as e:
                    logger.warning(f"⚸ [_catchup_missed_pushes] 無法解析排程時間 '{item['scheduled_time']}': {e}")
                except Exception as e:
                    logger.error(f"❌ [_catchup_missed_pushes] 處理排程時間時發生未預期錯誤 '{item['scheduled_time']}': {e}", exc_info=True)

            if not missed:
                logger.info("ℹ️ [_catchup_missed_pushes] 無過時漏推項目")
                return

            # 按時間排序，依序補推
            missed.sort(key=lambda x: x[1])
            logger.info(f"🔄 [_catchup_missed_pushes] 發現 {len(missed)} 個重啟前漏推項目，開始補推")
            for item, sched_dt in missed:
                scheduled_time = item['scheduled_time']
                diff_seconds = (now - sched_dt).total_seconds()
                logger.info(f"📺 [_catchup_missed_pushes] 補推時刻: {scheduled_time} (距今 {diff_seconds:.0f} 秒前)")
                try:
                    success = await self.send_anime_push(
                        scheduled_time, ANIME_CHANNEL_ID,
                        week_start_date=week_start_str,
                        day_of_week=day_of_week
                    )
                    if success:
                        logger.info(f"✅ [_catchup_missed_pushes] 補推成功: {scheduled_time}")
                    else:
                        logger.warning(f"⚠️ [_catchup_missed_pushes] 補推無新番或失敗: {scheduled_time}")
                except Exception as e:
                    logger.error(f"❌ [_catchup_missed_pushes] 補推異常 {scheduled_time}: {e}", exc_info=True)
                await asyncio.sleep(2)  # 避免短時間內連續發送太多訊息
        except Exception as e:
            logger.error(f"❌ [_catchup_missed_pushes] 失敗: {e}", exc_info=True)

    async def _periodic_catchup_check(self):
        """
        定期補推檢查：每 5 分鐘執行一次，檢查今日所有「已過時但未推送」的項目並真正發送
        解決 dispatcher 錯過時刻、bot 重啟後漏推等問題
        """
        logger = logging.getLogger(__name__)
        print("[DEBUG_CATCHUP] _periodic_catchup_check function entered", flush=True)
        logger.info("🔄 [_periodic_catchup_check] 定期補推檢查任務啟動（每 5 分鐘）")

        # 等待 bot ready，但設 timeout 防止卡死
        try:
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
            print("[DEBUG_CATCHUP] bot.wait_until_ready() completed", flush=True)
            logger.info("✅ [_periodic_catchup_check] bot ready，開始執行補推檢查")
        except asyncio.TimeoutError:
            logger.error("❌ [_periodic_catchup_check] wait_until_ready() timeout 60s，終止任務")
            print("[DEBUG_CATCHUP] wait_until_ready() TIMEOUT!", flush=True)
            return

        while not self.bot.is_closed():
            try:
                now = datetime.now(TW_TZ)
                week_start = now - timedelta(days=now.weekday())
                week_start_str = week_start.strftime("%Y-%m-%d")
                day_of_week = (now.weekday() + 1) % 7 or 7
                today_schedule = self.get_today_schedule()

                if not today_schedule:
                    logger.warning("⚠️ [_periodic_catchup_check] today_schedule 為空，跳過本次檢查")
                    await asyncio.sleep(300)  # 5 分鐘
                    continue

                # 找出：pushed=0 且 scheduled_time <= 當前時間（今日所有已過時未推送項目）
                catchup_items = []
                for item in today_schedule:
                    if item['pushed']:
                        continue
                    try:
                        sched_dt = datetime.strptime(item['scheduled_time'], "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                        )
                        diff_seconds = (now - sched_dt).total_seconds()
                        # 已過時（不限時長，今日所有漏推都補上）
                        if diff_seconds >= 0:
                            catchup_items.append((item, sched_dt, diff_seconds))
                    except ValueError as e:
                        logger.warning(f"⚸ [{self.__class__.__name__}] 無法解析排程時間 '{item['scheduled_time']}': {e}")
                    except Exception as e:
                        logger.error(f"❌ [{self.__class__.__name__}] 處理排程時間時發生未預期錯誤 '{item['scheduled_time']}': {e}", exc_info=True)

                if catchup_items:
                    logger.info(f"🔄 [_periodic_catchup_check] 發現 {len(catchup_items)} 個今日漏推項目，開始補推")
                    # 按時間排序，先推較早的
                    catchup_items.sort(key=lambda x: x[1])

                    for item, sched_dt, diff_seconds in catchup_items:
                        scheduled_time = item['scheduled_time']
                        logger.info(f"📺 [_periodic_catchup_check] 補推時刻: {scheduled_time} (距今 {diff_seconds:.0f} 秒前)")
                        try:
                            success = await self.send_anime_push(
                                scheduled_time,
                                ANIME_CHANNEL_ID,
                                day_of_week=day_of_week,
                                week_start_date=week_start_str
                            )
                            if success:
                                logger.info(f"✅ [_periodic_catchup_check] 補推成功: {scheduled_time}")
                            else:
                                logger.warning(f"⚠️ [_periodic_catchup_check] 補推無新番或失敗: {scheduled_time}")
                        except Exception as e:
                            logger.error(f"❌ [_periodic_catchup_check] 補推異常 {scheduled_time}: {e}")
                else:
                    pass  # No catchup items found

                # 每 5 分鐘檢查一次
                await asyncio.sleep(300)

            except asyncio.CancelledError:
                logger.info("🛑 [_periodic_catchup_check] 任務被取消")
                break
            except Exception as e:
                logger.error(f"❌ [_periodic_catchup_check] 異常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 錯誤時等 1 分鐘避免狂迴圈

    async def _init_weekly_schedule_if_empty(self):
        """如果本週的週表為空，立即從 API 拉取（解決首次部署/非禮拜天重啟問題）"""
        try:
            await self.bot.wait_until_ready()
            today_schedule = self.get_today_schedule()
            if today_schedule:
                logger = logging.getLogger(__name__)
                logger.info(f"✅ [_init_weekly_schedule_if_empty] 週表已有 {len(today_schedule)} 筆，跳過")
                return

            logger = logging.getLogger(__name__)
            logger.info("🔄 [_init_weekly_schedule_if_empty] 週表為空，立即從 API 拉取...")
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] 無法拉取時程表 API")
                return

            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")

            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)
                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get('scheduleTime', '')
                        if scheduled_time:
                            schedule_data.append({
                                'day_of_week': day_of_week,
                                'scheduled_time': scheduled_time,
                                'anime_data': anime
                            })

            if schedule_data:
                self.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(f"✅ [_init_weekly_schedule_if_empty] 週表初始化完成: {len(schedule_data)} 筆")

                # 清理孤兒記錄
                if hasattr(self.db, 'clean_orphaned_records'):
                    orphan_stats = self.db.clean_orphaned_records(week_start_str)
                    if orphan_stats.get('messages', 0) > 0 or orphan_stats.get('notified', 0) > 0:
                        logger.info(f"🧹 [_init_weekly_schedule_if_empty] 清理孤兒記錄: messages={orphan_stats.get('messages')}, notified={orphan_stats.get('notified')}")
            else:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] API 返回空時程表")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [_init_weekly_schedule_if_empty] 失敗: {e}", exc_info=True)

    # ==================== API 相關方法 ====================

    async def fetch_new_anime_from_api(self) -> List[Dict]:
        """從 API 獲取最近更新的動畫"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

                    if 'newAnime' not in data:
                        return None

                    return data['newAnime']
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Error fetching new anime from API: {e}")
            return None

    async def fetch_all_recent_anime_from_api(self) -> List[Dict]:
        """獲取所有最近更新的動畫（用於排行榜）"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

                    if 'newAnime' not in data:
                        return None

                    return data['newAnime']
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Error fetching all recent anime from API: {e}")
            return None

    async def fetch_anime_details_from_api(self, video_sn: int) -> Optional[Dict]:
        """從 API 獲取單集動畫詳細信息"""
        try:
            url = f"https://api.gamer.com.tw/mobile_app/anime/v2/video.php?vsn={video_sn}"
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Error fetching anime details from API: {e}")
            return None

    def _extract_view_count_from_episode(self, episode: Dict) -> int:
        """從 episode 資料中提取觀看數"""
        views = 0
        # 嘗試多個可能的欄位名
        for field in ['views', 'viewCount', 'playCount', 'popular']:
            if field in episode and isinstance(episode[field], (int, float)):
                views = int(episode[field])
                break
        return views

    # ==================== 排程任務 ====================

    # 排程分發器：在「下一個待推送時刻」精確喚醒，呼叫 API → 推送 → 睡到下一個時刻
    # 取代原每分鐘輪詢，大幅減少 API 呼叫
    async def _schedule_dispatcher(self):
        """背景任務：精確在每個 scheduled_time 喚醒並推送"""
        logger = logging.getLogger(__name__)
        logger.info("🚀 [_schedule_dispatcher] 排程分發器啟動")

        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                now = datetime.now(TW_TZ)
                today_schedule = self.get_today_schedule()

                # 找出今天「尚未推送」且「時間 >= 現在」的最早一筆
                next_item = None
                for item in today_schedule:
                    if item['pushed']:
                        continue
                    scheduled = item['scheduled_time']
                    try:
                        sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                        )
                        if sched_dt >= now:
                            next_item = item
                            break
                    except ValueError as e:
                        logger.warning(f"⚸ [{self.__class__.__name__}] 無法解析排程時間 '{scheduled}': {e}")
                    except Exception as e:
                        logger.error(f"❌ [{self.__class__.__name__}] 處理排程時間時發生未預期錯誤 '{scheduled}': {e}", exc_info=True)

                if next_item:
                    scheduled = next_item['scheduled_time']
                    # 計算要睡多久（秒）
                    try:
                        sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                        )
                    except ValueError as e:
                        logger.warning(f"⚸ [{self.__class__.__name__}] 無法解析排程時間 '{scheduled}' 計算睡眠時間: {e}")
                        # 如果無法解析時間，跳過此項目並繼續尋找下一個
                        continue
                    except Exception as e:
                        logger.error(f"❌ [{self.__class__.__name__}] 處理排程時間時發生未預期錯誤 '{scheduled}' 計算睡眠時間: {e}", exc_info=True)
                        # 如果發生未預期錯誤，跳過此項目
                        continue
                    sleep_seconds = (sched_dt - now).total_seconds()

                    # 睡到預定時間（最多睡 24 小時防呆）
                    if sleep_seconds > 0:
                        logger.info(f"😴 [_schedule_dispatcher] 下一檔 {scheduled}，睡 {sleep_seconds:.0f} 秒")
                        await asyncio.sleep(min(sleep_seconds, 86400))

                    # 時間到 → 即時呼叫 API 推送
                    now = datetime.now(TW_TZ)
                    logger.info(f"⏰ [_schedule_dispatcher] 時間到 {scheduled}，呼叫 API 推送")
                    await self.send_anime_push(scheduled, ANIME_CHANNEL_ID)
                    # 成功會在 send_anime_push 內標記 pushed=1，下次迴圈會自動跳過
                else:
                    # 今天沒有待推送項目 → 睡到明天 00:00 重新載入時程
                    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    sleep_seconds = (tomorrow - now).total_seconds()
                    logger.info(f"😴 [_schedule_dispatcher] 今日無待推項目，睡到明天 00:00 ({sleep_seconds:.0f} 秒)")
                    await asyncio.sleep(sleep_seconds)

            except asyncio.CancelledError:
                logger.info("🛑 [_schedule_dispatcher] 任務被取消")
                break
            except Exception as e:
                logger.error(f"❌ [_schedule_dispatcher] 異常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 錯誤時休息 1 分鐘避免狂迴圈

    @tasks.loop(hours=24)
    async def refresh_weekly_schedule(self):
        """每天晚上 22:00 拉取完整週表全量覆蓋，並檢查今日 <=22:00 的漏推項目進行補推"""
        result = await self.schedule_tracker.refresh_weekly_schedule()

        if not result.get('success'):
            if result.get('skipped'):
                return  # 非 22:00 靜默跳過
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [refresh_weekly_schedule] 週表刷新失敗: {result.get('error')}")
            return

        # 週表刷新成功，檢查今日已過去/當前時刻(<=22:00)且未推送的項目進行補推
        today_schedule = result.get('today_schedule', [])
        now = datetime.now(TW_TZ)
        current_time_str = now.strftime("%H:%M")

        logger = logging.getLogger(__name__)
        logger.info(f"✅ [refresh_weekly_schedule] 週表刷新完成，檢查補推項目（現在 {current_time_str}）")

        # 篩選：pushed=0 且 scheduled_time <= 22:00（今天的推送時段已結束）
        missed = []
        for item in today_schedule:
            if item['pushed']:
                continue
            scheduled = item['scheduled_time']
            try:
                # 僅處理 <= 當前時間（22:00 執行時，當前即為 22:xx，所以 <=22:00 即為今日已過去時段）
                if scheduled <= current_time_str:
                    missed.append(item)
            except Exception as e:
                logger.error(f"❌ [refresh_weekly_schedule] 處理時刻時發生錯誤 '{scheduled}': {e}", exc_info=True)

        if missed:
            missed_sorted = sorted(missed, key=lambda x: x['scheduled_time'])
            logger.info(f"📺 [refresh_weekly_schedule] 發現 {len(missed_sorted)} 個漏推時刻，開始補推")
            for item in missed_sorted:
                await self.send_anime_push(item['scheduled_time'], ANIME_CHANNEL_ID)
                await asyncio.sleep(2)
        else:
            logger.info(f"ℹ️ [refresh_weekly_schedule] 今日無漏推項目")

    @tasks.loop(hours=6)
    async def sync_episode_stats(self):
        """自動發送週統計 - 每週天 台灣時間 23:00 發送 - 已停用：被每日檢查取代"""
        # 此功能已被 daily_anime_check 取代
        pass

    # ==================== 任務啟動和錯誤處理 ====================

    @refresh_weekly_schedule.before_loop
    async def before_refresh_weekly_schedule(self):
        """等待 bot 就緒，並對齊到每天晚上 22:00 執行"""
        await self.bot.wait_until_ready()

        # 計算距離下一次 22:00 的秒數
        now = datetime.now(TW_TZ)
        next_run = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        sleep_seconds = (next_run - now).total_seconds()
        logger = logging.getLogger(__name__)
        logger.info(f"⏳ [refresh_weekly_schedule] 首次執行將在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({sleep_seconds:.0f} 秒後)")

        await asyncio.sleep(sleep_seconds)

    @refresh_weekly_schedule.error
    async def refresh_weekly_schedule_error(self, error):
        """處理任務異常"""
        logger = logging.getLogger(__name__)
        logger.error(f"❌ [refresh_weekly_schedule] 任務異常: {error}", exc_info=True)

    @sync_episode_stats.before_loop
    async def before_sync_episode_stats(self):
        """等待 bot 就緒"""
        await self.bot.wait_until_ready()

    @sync_episode_stats.error
    async def sync_episode_stats_error(self, error):
        """處理任務異常"""
        logger = logging.getLogger(__name__)
        logger.error(f"❌ [sync_episode_stats] 任務異常: {error}", exc_info=True)

    # ==================== 輔助方法 ====================

    async def _sync_episode_stats_from_api(self):
        """從 API 同步劇集統計數據"""
        try:
            # 獲取最近的動畫數據
            episodes = await self.fetch_all_recent_anime_from_api()
            if not episodes:
                logger = logging.getLogger(__name__)
                logger.warning("⚠️ [_sync_episode_stats_from_api] 無法獲取動畫數據")
                return

            # 處理每集數據
            processed_count = 0
            for episode in episodes:
                video_sn = episode.get('videoSn')
                anime_sn = episode.get('animeSn')
                episode_num = episode.get('episodeNum', '')
                views = self._extract_view_count_from_episode(episode)
                score = episode.get('score', 0.0)

                if video_sn and anime_sn:
                    self.record_episode_stats(video_sn, anime_sn, episode_num, views, score)
                    processed_count += 1

            logger = logging.getLogger(__name__)
            logger.info(f"📊 [_sync_episode_stats_from_api] 同步了 {processed_count} 筆劇集統計數據")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [_sync_episode_stats_from_api] 同步失敗: {e}", exc_info=True)

    # ==================== 輔助類：AnimeVoteView (保持在主類中，因為它需要引用主類) ====================

    class AnimeVoteView(discord.ui.View):
        """動畫投票視圖 - 6 個投票按鈕 + 評論按鈕 (永久視圖)"""

        # 投票類型配置
        VOTE_TYPES = {
            "masterpiece": ("神作", "🟩"),     # 綠
            "great": ("佳作", "🟦"),          # 藍
            "darkhorse": ("黑馬", "🟪"),      # 紫
            "decent": ("普作/小品", "🟨"),    # 黃
            "controversial": ("爭議作", "🟧"), # 橙
            "disaster": ("雷作/糞作", "🟥"),   # 紅
        }

        def __init__(self, episode: Dict, anime_tracker: "AnimeTracker"):
            # 永久視圖設置：timeout=None 表示永不超時，persistent=True 表示重啟後依然有效
            super().__init__(timeout=None)
            self.episode = episode
            self.tracker = anime_tracker
            self.video_sn = episode.get("videoSn")
            self.anime_sn = episode.get("animeSn")
            self.message_id = None
            self.last_interaction_time = None  # 用於追蹤最後互動時間

            logger = logging.getLogger(__name__)
            logger.info(f"📌 [AnimeVoteView.__init__] 開始創建視圖，video_sn={self.video_sn}")

            # 添加投票按鈕
            button_count = 0
            for vote_key, (vote_label, color_emoji) in self.VOTE_TYPES.items():
                # 所有投票按鈕都用灰色
                button_style = discord.ButtonStyle.secondary  # 灰色

                button = discord.ui.Button(
                    label=f"{color_emoji} {vote_label}",
                    custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                    style=button_style
                )
                button.callback = self._vote_callback
                self.add_item(button)
                button_count += 1

            logger.info(f"✅ [AnimeVoteView.__init__] 添加了 {button_count} 個投票按鈕")

            # 添加評論按鈕
            comment_button = discord.ui.Button(
                label="💬 留言",
                custom_id=f"anime_comment_{self.video_sn}",
                style=discord.ButtonStyle.secondary  # 灰色
            )
            comment_button.callback = self._comment_callback
            self.add_item(comment_button)

            logger.info(f"✅ [AnimeVoteView.__init__] 添加了評論按鈕，目前共有 {len(self.children)} 個項目")

        async def _vote_callback(self, interaction: discord.Interaction):
            """處理投票按鈕點擊 - 投票 +2000 KK幣（每個用戶每條消息只適用一次）"""
            try:
                logger = logging.getLogger(__name__)
                logger.info(f"🎯 [_vote_callback] 用戶 {interaction.user.name}({interaction.user.id}) 點擊投票按鈕")
                logger.info(f"   custom_id={interaction.custom_id}, message_id={interaction.message.id}")

                # 記錄互動時間
                self.last_interaction_time = datetime.now(TW_TZ)

                # 解析投票類型
                vote_key = interaction.custom_id.replace(f"anime_vote_", "").rsplit("_", 1)[0]
                vote_label, _ = self.VOTE_TYPES.get(vote_key, ("未知", None))

                # 獲取用戶的匿名雜湊（用來防止同一用戶多次投票）
                user_hash = str(hash(interaction.user.id))[:10]

                # 記錄投票
                await self.tracker.record_vote(
                    video_sn=self.video_sn,
                    anime_sn=self.anime_sn,
                    message_id=interaction.message.id,
                    vote_type=vote_key,
                    user_hash=user_hash
                )

                logger.info(f"✅ [_vote_callback] 投票已記錄: {interaction.user.name} 投票了 {vote_label}")

                # 立即回應用戶
                logger.info(f"⏳ [_vote_callback] 準備 defer() 響應...")
                await interaction.response.defer()
                logger.info(f"✅ [_vote_callback] defer() 已執行")

                # === KK幣獎勵邏輯 (投票 +2000) ===
                reward_given = False
                try:
                    from db_adapter import set_user_field, get_user_field

                    # 檢查是否已發放過獎勵
                    if not self.tracker.db.is_reward_already_given(interaction.user.id, interaction.message.id, "vote"):
                        # 獲取當前 KK幣
                        current_kkcoin = get_user_field(interaction.user.id, "kkcoin") or 0
                        new_kkcoin = int(current_kkcoin) + 2000

                        # 更新 KK幣
                        set_user_field(interaction.user.id, "kkcoin", new_kkcoin)

                        # 記錄獎勵發放
                        self.tracker.db.record_reward(
                            user_id=interaction.user.id,
                            message_id=interaction.message.id,
                            reward_type="vote",
                            reward_amount=2000
                        )

                        logger.info(f"💰 [_vote_callback] {interaction.user.name} 投票獲得 2000 KK幣，現在共有 {new_kkcoin} KK幣")
                        reward_given = True
                    else:
                        logger.info(f"⏭️ [_vote_callback] {interaction.user.name} 已獲得過該消息的投票獎勵")
                except ImportError:
                    logger.warning("⚠️ [_vote_callback] db_adapter 未找到，無法獎勵 KK幣")
                except Exception as e:
                    logger.error(f"❌ [_vote_callback] 獎勵 KK幣失敗: {e}", exc_info=True)

                # 更新原始消息的 embed（添加統計信息）
                try:
                    await self.tracker._update_message_stats(interaction.message)
                    logger.info(f"✅ [_vote_callback] {interaction.user.name} 的投票已記錄並更新消息統計")
                except Exception as update_error:
                    logger.error(f"❌ [_vote_callback] 更新消息統計失敗: {update_error}", exc_info=True)

            except Exception as e:
                logger.error(f"❌ [_vote_callback] 投票失敗: {e}", exc_info=True)
                try:
                    await interaction.response.send_message(f"❌ 投票失敗: {str(e)[:50]}", ephemeral=True)
                except:
                    pass

        async def _comment_callback(self, interaction: discord.Interaction):
            """處理評論按鈕點擊 - 彈出評論輸入框"""
            try:
                logger = logging.getLogger(__name__)
                # 記錄互動時間
                self.last_interaction_time = datetime.now(TW_TZ)

                # 創建簡單的文本輸入模態框
                class CommentModal(discord.ui.Modal, title="留下匿名評論"):
                    comment_input = discord.ui.TextInput(
                        label="評論內容",
                        placeholder="寫下你對這部動畫的看法...",
                        max_length=200,
                        required=False
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            comment = str(self.comment_input).strip()
                            if not comment:
                                await modal_interaction.response.send_message("評論不能為空", ephemeral=True)
                                return

                            # 獲取用戶匿名雜湊
                            user_hash = str(hash(modal_interaction.user.id))[:10]

                            # 記錄評論（vote_type 為空表示只是評論）
                            self.tracker.db.record_vote(
                                video_sn=self.video_sn,
                                anime_sn=self.anime_sn,
                                message_id=modal_interaction.message.id,
                                vote_type="comment",
                                comment=comment,
                                user_hash=user_hash
                            )

                            logger.info(f"💬 [comment] {modal_interaction.user} 留言: {comment[:30]}...")

                            # === KK幣獎勵邏輯 (評論 +3000) ===
                            reward_message = "✅ 評論已保存！感謝你的意見"
                            try:
                                from db_adapter import set_user_field, get_user_field

                                # 檢查是否已發放過獎勵
                                if not self.tracker.db.is_reward_already_given(modal_interaction.user.id, modal_interaction.message.id, "comment"):
                                    # 獲取當前 KK幣
                                    current_kkcoin = get_user_field(modal_interaction.user.id, "kkcoin") or 0
                                    new_kkcoin = int(current_kkcoin) + 3000

                                    # 更新 KK幣
                                    set_user_field(modal_interaction.user.id, "kkcoin", new_kkcoin)

                                    # 記錄獎勵發放
                                    self.tracker.db.record_reward(
                                        user_id=modal_interaction.user.id,
                                        message_id=modal_interaction.message.id,
                                        reward_type="comment",
                                        reward_amount=3000
                                    )

                                    logger.info(f"💰 [comment_submit] {modal_interaction.user} 評論獲得 3000 KK幣，現在共有 {new_kkcoin} KK幣")
                                    reward_message = "✅ 評論已保存！\n💰 +3000 KK幣獎勵已發放"
                                else:
                                    logger.info(f"⏭️ [comment_submit] {modal_interaction.user} 已獲得過該消息的評論獎勵")
                                    reward_message = "✅ 評論已保存！"
                            except ImportError:
                                logger.warning("⚠️ [comment_submit] db_adapter 未找到，無法獎勵 KK幣")
                            except Exception as e:
                                logger.error(f"❌ [comment_submit] 獎勵 KK幣失敗: {e}", exc_info=True)

                            await modal_interaction.response.send_message(reward_message, ephemeral=True)

                            # 更新原始消息統計
                            try:
                                await self.tracker._update_message_stats(modal_interaction.message)
                                logger.info(f"✅ [comment_submit] {modal_interaction.user} 的評論已保存並更新消息統計")
                            except Exception as update_error:
                                logger.error(f"❌ [comment_submit] 更新消息統計失敗: {update_error}", exc_info=True)
                        except Exception as e:
                            logger.error(f"❌ [comment_submit] 保存評論失敗: {e}", exc_info=True)

                        # 將追蹤和更新函數保存到模態框實例
                        modal = CommentModal()
                        modal.tracker = self.tracker
                        modal.video_sn = self.video_sn
                        modal.anime_sn = self.anime_sn
                        modal.update_stats = self._update_message_stats

                        await interaction.response.send_modal(modal)

            except Exception as e:
                logger.error(f"❌ [_comment_callback] 評論失敗: {e}", exc_info=True)

        async def _update_message_stats(self, message: discord.Message):
            """更新消息中的投票統計"""
            try:
                logger = logging.getLogger(__name__)
                logger.info(f"📝 [_update_message_stats] 開始更新消息 ID={message.id}, 頻道 ID={message.channel.id}")

                if not message.embeds:
                    logger.warning(f"⚠️ [_update_message_stats] 消息沒有 embed, message_id={message.id}")
                    return

                original_embed = message.embeds[0]
                logger.info(f"✅ [_update_message_stats] 找到 embed, 標題={original_embed.title}")

                # 獲取投票統計和評論
                stats = self.tracker.get_vote_stats(message.id)
                comments = self.tracker.get_vote_comments(message.id, limit=3)
                logger.info(f"📊 [_update_message_stats] 投票統計: {stats}, 評論數: {len(comments)}")

                # 建立統計內容
                stats_content = ""
                if stats and any(stats.values()):
                    stat_lines = []
                    for vote_key, (vote_label, color_block) in self.VOTE_TYPES.items():
                        count = stats.get(vote_key, 0)
                        if count > 0:
                            stat_lines.append(f"{color_block} {vote_label}: {count} 票")
                    stats_content = "\n".join(stat_lines) if stat_lines else ""

                # 建立評論內容
                comments_content = ""
                if comments:
                    comments_content = "\n".join([f"• {c}" for c in comments])

                # 使用 embeds 參數直接編輯，不修改 embed 物件本身
                # 先重新構建完整的 embed，避免 EmbedProxy 序列化問題
                new_embed = discord.Embed(
                    title=original_embed.title,
                    description=original_embed.description,
                    color=original_embed.color,
                    timestamp=original_embed.timestamp
                )

                # 複製原有的字段，除了統計和評論
                for field in original_embed.fields:
                    if field.name not in ["📊 投票統計", "💬 匿名評論"]:
                        new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

                # 添加更新後的統計
                if stats_content:
                    new_embed.add_field(name="📊 投票統計", value=stats_content, inline=False)

                # 添加更新後的評論
                if comments_content:
                    new_embed.add_field(name="💬 匿名評論", value=comments_content, inline=False)

                # 複製 footer、author 等其他屬性
                if original_embed.footer:
                    new_embed.set_footer(text=original_embed.footer.text, icon_url=original_embed.footer.icon_url)
                if original_embed.author:
                    new_embed.set_author(name=original_embed.author.name, url=original_embed.author.url, icon_url=original_embed.author.icon_url)
                if original_embed.image:
                    new_embed.set_image(url=original_embed.image.url)
                if original_embed.thumbnail:
                    new_embed.set_thumbnail(url=original_embed.thumbnail.url)

                # 編輯消息
                logger.info(f"🔄 [_update_message_stats] 準備編輯消息 ID={message.id}")
                await message.edit(embed=new_embed)
                logger.info(f"✅ [_update_message_stats] 消息已成功編輯 ID={message.id}")

            except discord.Forbidden as e:
                logger.error(f"❌ [_update_message_stats] 權限不足（可能缺少 MANAGE_MESSAGES）: {e}", exc_info=True)
            except discord.NotFound as e:
                logger.error(f"❌ [_update_message_stats] 消息不存在或已被刪除: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"❌ [_update_message_stats] 更新統計失敗: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """Setup 函數供 Discord.py 加載 Cog"""
    await bot.add_cog(AnimeTracker(bot))