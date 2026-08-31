# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 自動通知新上架集數
已重構為三個模組：Push/Core、Schedule Tracker、Ranking Stats
"""

import logging
import sqlite3
from datetime import datetime, timedelta
import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks
from typing import Optional, List, Dict, Any
from .push_core import AnimePushCore, TW_TZ, API_ENDPOINT, API_TIMEOUT, API_HEADERS, get_week_start_date, ANIME_CHANNEL_ID
from .schedule_tracker import AnimeScheduleTracker
from .ranking_stats import RankingStats

logger = logging.getLogger(__name__)

# 檢查並移除重複的導入
try:
    from .bahamut_web_scraper import BahamutWebScraper
except ImportError:
    # 備用導入方式
    BahamutWebScraper = None

class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤 Cog - 負責動畫推送系統"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.push_core = None
        self.schedule_tracker = None
        self.ranking_stats = None
        self.web_scraper = None
        self.scheduler = None
        self.db_path = None
        self._views_restored = False
        self._scheduler_started = False

        # 初始化時標記需要設置依賴
        self._dependencies_set = False

    async def set_dependencies(self, db_path: str):
        """設置依賴元件（非同步版本，包含排程器初始化）"""
        print("[AnimeTracker.set_dependencies] 開始...", flush=True)
        if self._dependencies_set:
            print("[AnimeTracker.set_dependencies] 已設置過，跳過", flush=True)
            return

        self.db_path = db_path

        # 初始化各個模組
        from .push_core import AnimeDatabase, AnimeDBImpl
        db_impl = AnimeDBImpl(self.db_path)
        db = AnimeDatabase(db_impl)
        self.db = db
        self.push_core = AnimePushCore(db)
        self.schedule_tracker = AnimeScheduleTracker(self.db_path)
        self.ranking_stats = RankingStats(db)

        # 初始化網路爬蟲
        if BahamutWebScraper:
            self.web_scraper = BahamutWebScraper()
        else:
            # 備用方案：直接使用 push_core 中的方法
            self.web_scraper = None

        # 先設置各模組的 db 依賴
        self.push_core.set_dependencies(self.bot, db, self)
        self.schedule_tracker.set_dependencies(self.bot, db, self.push_core, self)
        self.ranking_stats.set_dependencies(self.bot, db)

        self._dependencies_set = True
        msg = "✅ [AnimeTracker.set_dependencies] 依賴設置完成"
        print(msg, flush=True)
        self.logger.info(msg)

        # 初始化排程器
        print(f"[AnimeTracker.set_dependencies] _scheduler_started={self._scheduler_started}", flush=True)
        if not self._scheduler_started:
            print("[AnimeTracker.set_dependencies] 呼叫 _init_scheduler()...", flush=True)
            await self._init_scheduler()
            self._scheduler_started = True
            print("[AnimeTracker.set_dependencies] _init_scheduler() 完成", flush=True)

        # 檢查並初始化週表（如果為空）
        print("[AnimeTracker.set_dependencies] 呼叫 _init_weekly_schedule_if_empty()...", flush=True)
        await self._init_weekly_schedule_if_empty()
        print("[AnimeTracker.set_dependencies] 完成", flush=True)

    async def cog_load(self):
        """Cog 載入時執行的初始化"""
        self.logger.info("📺 [AnimeTracker.cog_load] 開始載入 Cog")

        # 只恢復永續視圖，依賴和排程器由 uibot.py 的 on_ready 中的 set_dependencies 初始化
        await self._restore_persistent_views()

        self.logger.info("🚀 [AnimeTracker.cog_load] AnimeTracker Cog 載入完成（等待 set_dependencies 初始化依賴）")

    async def _init_scheduler(self):
        """初始化 APScheduler"""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger

            print("[AnimeTracker._init_scheduler] 開始初始化排程器...", flush=True)
            self.scheduler = AsyncIOScheduler(timezone=TW_TZ)

            # 添加週表刷新任務（每天 18:10）
            self.scheduler.add_job(
                self._refresh_weekly_schedule_task,
                CronTrigger(hour=18, minute=10, timezone=TW_TZ),
                id='weekly_schedule_refresh',
                name='週表資料刷新',
                replace_existing=True
            )

            # 添加同步統計任務（每 6 小時）
            self.scheduler.add_job(
                self._sync_episode_stats_task,
                CronTrigger(hour='*/6', timezone=TW_TZ),
                id='episode_stats_sync',
                name='動畫統計同步',
                replace_existing=True
            )

            self.scheduler.start()
            msg = "🚀 [AnimeTracker._init_scheduler] 排程器已啟動"
            print(msg, flush=True)
            self.logger.info(msg)
            msg = "📅 [AnimeTracker._init_scheduler] 週表刷新任務已添加 (每天 22:00)"
            print(msg, flush=True)
            self.logger.info(msg)
            msg = "🔄 [AnimeTracker._init_scheduler] 統計同步任務已添加 (每 6 小時)"
            print(msg, flush=True)
            self.logger.info(msg)

        except Exception as e:
            msg = f"❌ [AnimeTracker._init_scheduler] 初始化排程器失敗: {e}"
            print(msg, flush=True)
            import traceback
            traceback.print_exc()
            self.logger.error(msg, exc_info=True)

    async def _refresh_weekly_schedule_task(self):
        """週表資料刷新任務"""
        try:
            self.logger.info("🔄 [AnimeTracker._refresh_weekly_schedule_task] 開始週表資料刷新")
            result = await self.schedule_tracker.refresh_weekly_schedule()
            if result.get("success"):
                self.logger.info(f"✅ [AnimeTracker._refresh_weekly_schedule_task] 週表資料刷新成功")
                # 重新排程推送任務
                await self._reschedule_push_jobs()
            else:
                self.logger.error(f"❌ [AnimeTracker._refresh_weekly_schedule_task] 週表資料刷新失敗: {result.get('error')}")
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker._refresh_weekly_schedule_task] 週表資料刷新異常: {e}", exc_info=True)

    async def _sync_episode_stats_task(self):
        """同步動畫統計任務"""
        try:
            self.logger.info("🔄 [AnimeTracker._sync_episode_stats_task] 開始同步動畫統計")
            await self.ranking_stats.sync_episode_stats()
            await self.ranking_stats.send_weekly_stats()
            self.logger.info("✅ [AnimeTracker._sync_episode_stats_task] 動畫統計同步完成")
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker._sync_episode_stats_task] 動畫統計同步失敗: {e}", exc_info=True)

    async def _init_weekly_schedule_if_empty(self):
        """如果週表為空，則立即從 API 拉取資料；無論如何都會排程推送任務"""
        try:
            # 檢查週表是否為空
            today_schedule = self.schedule_tracker.get_today_schedule()
            if not today_schedule:
                self.logger.info("🔄 [_init_weekly_schedule_if_empty] 週表為空，立即從 API 拉取...")
                result = await self.schedule_tracker.refresh_weekly_schedule(force=True)
                if result.get("success"):
                    self.logger.info("✅ [_init_weekly_schedule_if_empty] 週表初始化完成")
                else:
                    error_msg = result.get('error')
                    if error_msg is None:
                        if result.get('skipped'):
                            error_msg = "週表更新被跳過（非刷新時間）"
                        else:
                            error_msg = "未知錯誤"
                    self.logger.error(f"❌ [_init_weekly_schedule_if_empty] 週表初始化失敗: {error_msg}")
            else:
                self.logger.info(f"📅 [_init_weekly_schedule_if_empty] 週表已有資料 ({len(today_schedule)} 筆)，跳過 API 拉取")

            # 無論週表是否為空，都要排程推送任務
            await self._reschedule_push_jobs()
        except sqlite3.OperationalError as e:
            if "no such table: anime_weekly_schedule" in str(e):
                self.logger.warning("⚠️ [_init_weekly_schedule_if_empty] 週表尚未建立，跳過初始化")
            else:
                self.logger.error(f"❌ [_init_weekly_schedule_if_empty] 初始化週表時發生資料庫錯誤: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"❌ [_init_weekly_schedule_if_empty] 初始化週表時發生錯誤: {e}", exc_info=True)

    async def _reschedule_push_jobs(self):
        """根據當前週表重新排程所有推送任務"""
        try:
            if not self.scheduler:
                self.logger.warning("⚠️ [_reschedule_push_jobs] 掑程器未初始化")
                return

            # 移除所有現有的推送任務
            jobs = self.scheduler.get_jobs()
            push_job_ids = [job.id for job in jobs if job.id.startswith('push_')]
            for job_id in push_job_ids:
                self.scheduler.remove_job(job_id)

            if push_job_ids:
                self.logger.info(f"🧹 [_reschedule_push_jobs] 已移除 {len(push_job_ids)} 個舊推送任務")

            # 根據週表創建新的推送任務
            today = datetime.now(TW_TZ)
            # 使用 API 週語義 (api_week=True)，與 push_core、週表刷新、資料庫儲存保持一致
            week_start_str = get_week_start_date(today, api_week=True)

            # 獲取今天的完整時程 (使用相同的週起始日期)
            today_schedule = self.schedule_tracker.get_today_schedule(week_start_date=week_start_str)
            scheduled_count = 0

            for schedule_item in today_schedule:
                day_of_week = schedule_item.get('day_of_week')
                scheduled_time = schedule_item.get('scheduled_time')
                video_sn = schedule_item.get('video_sn')
                anime_sn = schedule_item.get('anime_sn') or 0  # anime_sn 可能為 None，預設為 0

                if not all([day_of_week, scheduled_time, video_sn]):
                    continue

                try:
                    # 解析時間
                    time_obj = datetime.strptime(scheduled_time, "%H:%M").time()
                    # 計算目標日期（根據星期几）
                    days_ahead = (day_of_week - today.weekday() - 1) % 7
                    target_date = today + timedelta(days=days_ahead)
                    target_datetime = datetime.combine(target_date, time_obj, tzinfo=TW_TZ)

                    # 如果目標時間已經過去，則安排到下一週
                    if target_datetime <= today:
                        target_datetime += timedelta(weeks=1)

                    # 創建推送任務 ID
                    job_id = f"push_{anime_sn}_{video_sn}_{day_of_week}_{scheduled_time.replace(':', '')}"

                    # 添加 cron 任務
                    self.scheduler.add_job(
                        self._push_anime_task,
                        'cron',
                        hour=target_datetime.hour,
                        minute=target_datetime.minute,
                        timezone=TW_TZ,
                        id=job_id,
                        name=f'推送動畫: {anime_sn}_{video_sn}',
                        args=[anime_sn, video_sn],
                        replace_existing=True
                    )

                    scheduled_count += 1
                    self.logger.debug(f"🕐 [_reschedule_push_jobs] 已排程推送任務: {job_id} 於 {target_datetime}")

                except Exception as e:
                    self.logger.error(f"❌ [_reschedule_push_jobs] 排程推送任務失敗 ({anime_sn}, {video_sn}): {e}")

            self.logger.info(f"🔄 [_reschedule_push_jobs] 推送任務重新排程完成，共 {scheduled_count} 個任務")

        except Exception as e:
            self.logger.error(f"❌ [_reschedule_push_jobs] 重新排程推送任務時發生錯誤: {e}", exc_info=True)

    async def _push_anime_task(self, anime_sn: int, video_sn: int):
        """執行動畫推送任務"""
        try:
            self.logger.info(f"📢 [_push_anime_task] 開始推送動畫: anime_sn={anime_sn}, video_sn={video_sn}")
            self.logger.debug(f"[_push_anime_task] 參數: anime_sn={anime_sn}, video_sn={video_sn}")

            # Query anime_weekly_schedule for the entry matching anime_sn and video_sn
            # Data may have videoSn in column OR in JSON animeData
            # anime_sn may be in JSON as animeSn (camelCase) or anime_sn (snake_case)
            # json_extract returns integers, so use integer parameters
            if anime_sn > 0:
                # If we have anime_sn, try matching:
                # - videoSn: either column or JSON
                # - anime_sn: JSON as animeSn or anime_sn
                query = """
                    SELECT weekStartDate, dayOfWeek, scheduledTime
                    FROM anime_weekly_schedule
                    WHERE (videoSn = ? OR json_extract(animeData, '$.videoSn') = ?)
                      AND (json_extract(animeData, '$.animeSn') = ? OR json_extract(animeData, '$.anime_sn') = ?)
                """
                self.logger.debug(f"[_push_anime_task] 執行查詢 (anime_sn > 0): {query.strip()} with params ({video_sn}, {video_sn}, {anime_sn}, {anime_sn})")
                row = await self.db.fetchone(query, (video_sn, video_sn, anime_sn, anime_sn))
                self.logger.debug(f"[_push_anime_task] 查詢結果: {row}")
            else:
                # If anime_sn is 0 or unknown, match only by videoSn (column or JSON)
                query = """
                    SELECT weekStartDate, dayOfWeek, scheduledTime
                    FROM anime_weekly_schedule
                    WHERE videoSn = ? OR json_extract(animeData, '$.videoSn') = ?
                """
                self.logger.debug(f"[_push_anime_task] 執行查詢 (anime_sn <= 0): {query.strip()} with params ({video_sn}, {video_sn})")
                row = await self.db.fetchone(query, (video_sn, video_sn))
                self.logger.debug(f"[_push_anime_task] 查詢結果: {row}")

            if not row:
                self.logger.warning(f"⚠️ [_push_anime_task] 找不到排程資料: anime_sn={anime_sn}, video_sn={video_sn}")
                return

            week_start_date, day_of_week, scheduled_time = row
            self.logger.info(f"📌 [_push_anime_task] 找到排程: week_start={week_start_date}, day={day_of_week}, time={scheduled_time}")
            self.logger.debug(f"[_push_anime_task] 排程詳情: week_start_date={week_start_date}, day_of_week={day_of_week}, scheduled_time={scheduled_time}")

            # Use the configured anime push channel ID
            channel_id = ANIME_CHANNEL_ID
            self.logger.debug(f"[_push_anime_task] 使用頻道 ID: {channel_id}")

            self.logger.info(f"[_push_anime_task] 呼叫 push_core.send_anime_push: scheduled_time={scheduled_time}, channel_id={channel_id}, day_of_week={day_of_week}, week_start_date={week_start_date}")
            success = await self.push_core.send_anime_push(scheduled_time, channel_id, day_of_week, week_start_date)
            self.logger.debug(f"[_push_anime_task] push_core.send_anime_push 返回: {success}")

            if success:
                self.logger.info(f"✅ [_push_anime_task] 動畫推送成功: anime_sn={anime_sn}, video_sn={video_sn}")
            else:
                self.logger.warning(f"⚠️ [_push_anime_task] 動畫推送未觸發 (可能已推送或無新集數): anime_sn={anime_sn}, video_sn={video_sn}")
        except Exception as e:
            self.logger.error(f"❌ [_push_anime_task] 動畫推送任務失敗: {e}", exc_info=True)
            self.logger.debug(f"[_push_anime_task] 異常詳情: anime_sn={anime_sn}, video_sn={video_sn}", exc_info=True)

    async def _restore_persistent_views(self):
        """重啟時恢復所有永續視圖"""
        try:
            if self._views_restored:
                return

            # 恢復動畫投票視圖
            # 這裡會從資料庫中獲取未處理的動畫訊息，然後重新附加視圖
            # 實際實作會在 push_core 或相關模組中處理
            self._views_restored = True
            self.logger.info("👁️ [_restore_persistent_views] 永續視圖恢復完成")
        except Exception as e:
            self.logger.error(f"❌ [_restore_persistent_views] 恢復永續視圖失敗: {e}", exc_info=True)

    # ==================== 動畫視圖生成方法 ====================

    def generate_anime_view(self, episode: Dict[str, Any], video_sn: str) -> Optional[discord.ui.View]:
        """生成動畫推送視圖

        Args:
            episode: 動畫集數資訊
            video_sn: 視頻序號

        Returns:
            Optional[discord.ui.View]: 生成的視圖，失敗時返回 None
        """
        try:
            vote_view = discord.ui.View(timeout=None)

            anime_info = episode.get('anime_info', {})
            anime_sn = anime_info.get('anime_sn')
            anime_title = anime_info.get('anime_title', '未知動畫')

            if not anime_sn:
                self.logger.warning("⚠️ [generate_anime_view] 缺少 anime_sn")
                return None

            # 動畫頁面按鈕
            anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
            vote_view.add_item(
                discord.ui.Button(
                    label="🔗 動畫頁", url=anime_url, style=discord.ButtonStyle.link
                )
            )

            # 觀看按鈕
            video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}"
            vote_view.add_item(
                discord.ui.Button(
                    label="▶️ 觀看", url=video_url, style=discord.ButtonStyle.link
                )
            )

            return vote_view
        except Exception as e:
            self.logger.error(f"[generate_anime_view] Failed to generate view: {e}", exc_info=True)
            return None

    # ==================== Discord 事件處理方法 ====================

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot 就緒事件"""
        self.logger.info("📺 [AnimeTracker.on_ready] AnimeTracker Cog 收到 on_ready 事件")
        # 依賴和排程器由 uibot.py 的 on_ready 中的 set_dependencies 初始化

    # ==================== 指令方法 ====================

    @commands.hybrid_command(name="anime_refresh", description="手動刷新動畫週表")
    @commands.has_permissions(administrator=True)
    async def anime_refresh(self, ctx: commands.Context):
        """手動刷新動畫週表"""
        await ctx.defer(ephemeral=True)

        try:
            self.logger.info(f"🔄 [AnimeTracker.anime_refresh] 手動刷新週表請求 by {ctx.author}")
            result = await self.schedule_tracker.refresh_weekly_schedule()

            if result.get("success"):
                await ctx.followup.send(
                    f"✅ 週表刷新成功！\n"
                    f"📅 週起始日期: {result.get('week_start_date')}\n"
                    f"📊 總時程數: {result.get('total_count')}\n"
                    f"🕐 今日時程數: {len(result.get('today_schedule', []))}",
                    ephemeral=True
                )
                # 重新排程推送任務
                await self._reschedule_push_jobs()
            else:
                await ctx.followup.send(
                    f"❌ 週表刷新失敗: {result.get('error', '未知錯誤')}",
                    ephemeral=True
                )
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker.anime_refresh] 手動刷新週表失敗: {e}", exc_info=True)
            await ctx.followup.send(
                f"❌ 手動刷新週表時發生錯誤: {str(e)}",
                ephemeral=True
            )

    @commands.hybrid_command(name="anime_status", description="查看動畫追蹤系統狀態")
    @commands.has_permissions(administrator=True)
    async def anime_status(self, ctx: commands.Context):
        """查看動畫追蹤系統狀態"""
        await ctx.defer(ephemeral=True)

        try:
            status_lines = []

            # 排程器狀態
            if self.scheduler and self.scheduler.running:
                status_lines.append("✅ 掑程器: 運行中")
                jobs = self.scheduler.get_jobs()
                status_lines.append(f"📋 排程任務數: {len(jobs)}")
                push_jobs = [j for j in jobs if j.id.startswith('push_')]
                status_lines.append(f"📢 推送任務數: {len(push_jobs)}")
            else:
                status_lines.append("❌ 掑程器: 未運行")

            # 週表狀態
            today_schedule = self.schedule_tracker.get_today_schedule()
            status_lines.append(f"📅 今日時程數: {len(today_schedule)}")

            # 依賴狀態
            status_lines.append(f"🔧 依賴設置: {'✅ 已完成' if self._dependencies_set else '❌ 未完成'}")
            status_lines.append(f"🚀 掑程器啟動: {'✅ 已啟動' if self._scheduler_started else '❌ 未啟動'}")
            status_lines.append(f"👁️ 視圖恢復: {'✅ 已完成' if self._views_restored else '❌ 未完成'}")

            await ctx.followup.send(
                "📊 **動畫追蹤系統狀態**\n" + "\n".join(status_lines),
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker.anime_status] 查詢狀態失敗: {e}", exc_info=True)
            await ctx.followup.send(
                f"❌ 查詢狀態時發生錯誤: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    """設置 Cog 的入口點"""
    # 這個函式會被 bot.load_extension() 調用
    await bot.add_cog(AnimeTracker(bot))