"""
Bahamut 動畫追蹤 Cog - 自動通知新上架集數
已重構為三個模組：Push/Core、Schedule Tracker、Ranking Stats
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from zoneinfo import ZoneInfo  # Python 3.9+, 正確的時區處理
import time
from shared.utils.view_registry import PersistentViewBase

# 非同步 DB 適配器 - 避免阻塞事件循環
from shared.db.async_adapter import (
    get_user_field as async_get_user_field,
    set_user_field as async_set_user_field,
)

# 導入共用常數
from .push_core import (
    TW_TZ,
    ANIME_DB_PATH,
    ANIME_CHANNEL_ID,
    API_ENDPOINT,
    API_TIMEOUT,
    NOTIFIED_TABLE,
    BOOTSTRAP_FLAG_TABLE,
    ANIME_DETAILS_TABLE,
    ANIME_STATS_TABLE,
    EPISODE_STATS_TABLE,
    ANIME_MESSAGES_TABLE,
    ANIME_VOTES_TABLE,
    ANIME_REWARDS_TABLE,
    ANIME_CHECK_HISTORY_TABLE,
    ANIME_WEEKLY_SCHEDULE_TABLE,
)

# 導入自定義模組
from . import push_core
from .push_core import AnimePushCore, AnimeDatabase, find_unpushed_items
from .schedule_tracker import AnimeScheduleTracker
from .ranking_stats import RankingStats

# Logger
logger = logging.getLogger(__name__)


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
            logger.error(
                f"❌ [AnimeTracker.__init__] 數據庫初始化失敗: {e}", exc_info=True
            )
            raise

        # 初始化三個模組
        self.push_core = AnimePushCore(ANIME_DB_PATH)
        self.schedule_tracker = AnimeScheduleTracker(ANIME_DB_PATH)
        self.ranking_stats = RankingStats(ANIME_DB_PATH)

        # 設置相互依賴
        self.push_core.set_bot_and_db(bot, self.db)
        self.schedule_tracker.set_dependencies(bot, self.db, self.push_core)
        self.ranking_stats.set_dependencies(bot, self.db)

        # 設定 View 和 Embed 生成工廠
        self.push_core.set_view_factory(self.generate_anime_view)
        self.push_core.set_embed_factory(self.ranking_stats.generate_anime_embed)

        self.task_started = False
        self.bootstrap_completed = False
        self.last_weekly_stats_sent = None

    def __getattr__(self, name):
        """Delegate attribute access to sub-modules (push_core, db, schedule_tracker, ranking_stats)."""
        # Use __dict__ to avoid recursive __getattr__ calls
        for attr in ("push_core", "db", "schedule_tracker", "ranking_stats"):
            obj = self.__dict__.get(attr)
            if obj is not None and hasattr(obj, name):
                return getattr(obj, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    # ==================== CULC 生命週期方法 ====================

    async def cog_load(self):
        """Cog 加載時啟動任務"""
        import sys

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


            # 啟動週表刷新任務
            print("[COG_LOAD] 檢查 refresh_weekly_schedule 任務狀態", flush=True)
            if not self.refresh_weekly_schedule.is_running():
                print("[COG_LOAD] ✅ 啟動 refresh_weekly_schedule 任務", flush=True)
                logger.info(
                    "🚀 [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 任務"
                )
                try:
                    self.refresh_weekly_schedule.start()
                    logger.info(
                        f"✅ [AnimeTracker.cog_load] refresh_weekly_schedule 已啟動 (is_running={self.refresh_weekly_schedule.is_running()})"
                    )
                    print("[COG_LOAD] ✅ refresh_weekly_schedule 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(
                        f"❌ [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 失敗: {start_err}",
                        exc_info=True,
                    )
                    print(
                        f"[COG_LOAD] ❌ 啟動 refresh_weekly_schedule 失敗: {start_err}",
                        flush=True,
                    )
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info(
                            "🔄 [AnimeTracker.cog_load] 重試啟動 refresh_weekly_schedule..."
                        )
                        self.refresh_weekly_schedule.start()
                        logger.info(
                            "✅ [AnimeTracker.cog_load] 重試成功，refresh_weekly_schedule 已啟動"
                        )
                        print(
                            "[COG_LOAD] ✅ 重試成功，refresh_weekly_schedule 已啟動",
                            flush=True,
                        )
                    except Exception as retry_err:
                        logger.error(
                            f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}",
                            exc_info=True,
                        )
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(
                    "⏭️  [AnimeTracker.cog_load] refresh_weekly_schedule 已在運行 (is_running=True)"
                )
                print("[COG_LOAD] ⚠️ refresh_weekly_schedule 已在運行", flush=True)

            # 🔍 驗證週表刷新任務真正啟動（before_loop 可能失敗但不拋出異常）
            await asyncio.sleep(0.5)
            if self.refresh_weekly_schedule.is_running():
                logger.info(
                    "✅ [AnimeTracker.cog_load] 確認 refresh_weekly_schedule 正在運行"
                )
                print("[COG_LOAD] ✅ 確認 refresh_weekly_schedule 正在運行", flush=True)
            else:
                logger.error(
                    "❌ [AnimeTracker.cog_load] refresh_weekly_schedule 啟動後狀態異常 (is_running=False)，嘗試重啟..."
                )
                print(
                    "[COG_LOAD_ERROR] ❌ refresh_weekly_schedule 啟動後狀態異常，嘗試重啟...",
                    flush=True,
                )
                try:
                    self.refresh_weekly_schedule.start()
                    await asyncio.sleep(0.5)
                    if self.refresh_weekly_schedule.is_running():
                        logger.info("✅ [AnimeTracker.cog_load] 重啟成功")
                        print("[COG_LOAD] ✅ 重啟成功", flush=True)
                    else:
                        logger.critical(
                            "💥 [AnimeTracker.cog_load] 重啟仍失敗，任務無法啟動！"
                        )
                        print(
                            "[COG_LOAD_CRITICAL] 💥 重啟仍失敗，任務無法啟動！",
                            flush=True,
                        )
                except Exception as e:
                    logger.critical(
                        f"💥 [AnimeTracker.cog_load] 重啟異常: {e}", exc_info=True
                    )
                    print(f"[COG_LOAD_CRITICAL] 💥 重啟異常: {e}", flush=True)

            # 啟動精准派發器（背景任務，非 tasks.loop）
            print("[COG_LOAD] 啟動精準排程派發器", flush=True)
            logger.info("🚀 [AnimeTracker.cog_load] 啟動精準排程派發器")
            self._dispatcher_task = asyncio.create_task(
                self._wrap_task_with_restart(
                    "_schedule_dispatcher", self._schedule_dispatcher
                )
            )
            # 給任務一點時間啟動，檢查是否有異常
            await asyncio.sleep(0.1)
            if self._dispatcher_task.done():
                exc = self._dispatcher_task.exception()
                if exc:
                    logger.error(
                        f"❌ [AnimeTracker.cog_load] _schedule_dispatcher 任務立即失敗: {exc}",
                        exc_info=True,
                    )
                    print(
                        f"[COG_LOAD_ERROR] _schedule_dispatcher 任務立即失敗: {exc}",
                        flush=True,
                    )
                    raise exc
                else:
                    logger.warning(
                        "⚠️ [AnimeTracker.cog_load] _schedule_dispatcher 任務意外結束（無異常）"
                    )
                    print(
                        "[COG_LOAD_WARN] _schedule_dispatcher 任務意外結束", flush=True
                    )
            else:
                logger.info("✅ [AnimeTracker.cog_load] 精準排程派發器已啟動並運行中")
                print("[COG_LOAD] ✅ 精準排程派發器已啟動並運行中", flush=True)

            # 🔁 啟動後立即補推：處理重啟期間漏掉的已過時段
            print("[COG_LOAD] 執行啟動後補推...", flush=True)
            try:
                await self.catchup_missed_pushes()
                print("[COG_LOAD] ✅ 啟動後補推完成", flush=True)
            except Exception as e:
                logger.error(f"❌ [AnimeTracker.cog_load] 補推失敗: {e}", exc_info=True)
                print(f"[COG_LOAD] ❌ 補推失敗: {e}", flush=True)

                        # 啟動週期統計同步任務
            print("[COG_LOAD] 檢查 sync_episode_stats 任務狀態", flush=True)
            if not self.sync_episode_stats.is_running():
                print("[COG_LOAD] ✅ 啟動 sync_episode_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 sync_episode_stats 任務")
                try:
                    self.sync_episode_stats.start()
                    logger.info(
                        f"✅ [AnimeTracker.cog_load] sync_episode_stats 已啟動 (is_running={self.sync_episode_stats.is_running()})"
                    )
                    print("[COG_LOAD] ✅ sync_episode_stats 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(
                        f"❌ [AnimeTracker.cog_load] 啨動 sync_episode_stats 失敗: {start_err}",
                        exc_info=True,
                    )
                    print(
                        f"[COG_LOAD] ❌ 啨動 sync_episode_stats 失敗: {start_err}",
                        flush=True,
                    )
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info(
                            "🔄 [AnimeTracker.cog_load] 重試啟動 sync_episode_stats..."
                        )
                        self.sync_episode_stats.start()
                        logger.info(
                            "✅ [AnimeTracker.cog_load] 重試成功，sync_episode_stats 已啟動"
                        )
                        print(
                            "[COG_LOAD] ✅ 重試成功，sync_episode_stats 已啟動",
                            flush=True,
                        )
                    except Exception as retry_err:
                        logger.error(
                            f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}",
                            exc_info=True,
                        )
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(
                    "⏭️  [AnimeTracker.cog_load] sync_episode_stats 已在運行 (is_running=True)"
                )
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
                logger.info(
                    "✅ [AnimeTracker.cog_unload] refresh_weekly_schedule 已停止"
                )

            # 停止精準排程派發器（背景任務，非 tasks.loop）
            if hasattr(self, "_dispatcher_task") and not self._dispatcher_task.done():
                self._dispatcher_task.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] 精準排程派發器已停止")


            if self.sync_episode_stats.is_running():
                self.sync_episode_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] sync_episode_stats 已停止")

        except Exception as e:
            logger.error(
                f"❌ [AnimeTracker.cog_unload] 任務停止失敗: {e}", exc_info=True
            )
        logger.info("=" * 50)

    # ==================== 核心功能方法 ====================

    async def generate_anime_view(self, episode: dict) -> Optional[discord.ui.View]:
        """生成動畫視圖 - 創建投票和評論按鈕 + 動畫頁/觀看連結"""
        try:
            video_sn = episode.get("videoSn")
            anime_sn = episode.get("animeSn")
            if not video_sn or not anime_sn:
                return None

            vote_view = self.AnimeVoteView(episode, self)
            anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
            vote_view.add_item(
                discord.ui.Button(
                    label="🔗 動畫頁", url=anime_url, style=discord.ButtonStyle.link
                )
            )
            video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}"
            vote_view.add_item(
                discord.ui.Button(
                    label="▶️ 觀看", url=video_url, style=discord.ButtonStyle.link
                )
            )
            return vote_view
        except Exception as e:
            logger.error(
                f"❌ [generate_anime_view] Failed to generate view: {e}", exc_info=True
            )
            return None

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
                    video_sn = msg_info.get("video_sn") or msg_info.get("videoSn")

                    # 從資料庫獲取動畫資訊
                    anime_info = self.db.get_anime_details_by_videosn(video_sn)
                    if anime_info:
                        # 創建一個假的 episode 字典用於生成視圖
                        episode = {
                            "videoSn": video_sn,
                            "animeSn": anime_info.get("animeSn"),
                            "title": anime_info.get("title", "Unknown"),
                            "volume": anime_info.get("volume", ""),
                            "cover": anime_info.get("cover_url", ""),
                        }

                        # 生成視圖
                        view = await self.generate_anime_view(episode)
                        if view:
                            # 關鍵：必須傳入 message_id 才能讓永久視圖在重啟後正常工作
                            message_id = msg_info.get("messageId") or msg_info.get(
                                "message_id"
                            )
                            if message_id:
                                # 🔑 修復：將 message_id 存入 view 實例，供 modal 使用
                                view.message_id = int(message_id)
                                self.bot.add_view(view, message_id=int(message_id))
                                logger.info(
                                    f"✅ [_restore_old_message_views] 已註冊永久視圖 message_id={message_id}"
                                )
                            else:
                                logger.warning(
                                    "⚠️ [_restore_old_message_views] 缺少 message_id，無法註冊永久視圖"
                                )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(
                        f"❌ [_restore_old_message_views] 復原視圖失敗 for message {msg_info.get('messageId')}: {e}"
                    )
                    continue

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [_restore_old_message_views] 失敗: {e}")

    async def _init_weekly_schedule_if_empty(self):
        """如果本週的週表為空，立即從 API 拉取（解決首次部署/非禮拜天重啟問題）"""
        try:
            await self.bot.wait_until_ready()
            today_schedule = self.get_today_schedule()
            if today_schedule:
                logger = logging.getLogger(__name__)
                logger.info(
                    f"✅ [_init_weekly_schedule_if_empty] 週表已有 {len(today_schedule)} 筆，跳過"
                )
                return

            logger = logging.getLogger(__name__)
            logger.info(
                "🔄 [_init_weekly_schedule_if_empty] 週表為空，立即從 API 拉取..."
            )
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] 無法拉取時程表 API")
                return

            now = datetime.now(TW_TZ)
            week_start_str = self.get_week_start_date(now, api_week=True)

            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)
                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get("scheduleTime", "")
                        if scheduled_time:
                            schedule_data.append(
                                {
                                    "day_of_week": day_of_week,
                                    "scheduled_time": scheduled_time,
                                    "anime_data": anime,
                                }
                            )

            if schedule_data:
                self.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(
                    f"✅ [_init_weekly_schedule_if_empty] 週表初始化完成: {len(schedule_data)} 筆"
                )

                # 清理孤兒記錄
                if hasattr(self.db, "clean_orphaned_records"):
                    orphan_stats = self.db.clean_orphaned_records(week_start_str)
                    if (
                        orphan_stats.get("messages", 0) > 0
                        or orphan_stats.get("notified", 0) > 0
                    ):
                        logger.info(
                            f"🧹 [_init_weekly_schedule_if_empty] 清理孤兒記錄: messages={orphan_stats.get('messages')}, notified={orphan_stats.get('notified')}"
                        )
            else:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] API 返回空時程表")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                f"❌ [_init_weekly_schedule_if_empty] 失敗: {e}", exc_info=True
            )

    # ==================== API 相關方法 ====================
    # 注意：API 呼叫已移至 push_core.AnimePushCore 統一管理
    # 保留 fetch_all_recent_anime_from_api 供 ranking_stats 使用
    async def fetch_all_recent_anime_from_api(self) -> List[Dict]:
        """獲取所有最近更新的動畫（用於排行榜/統計）"""
        return await self.push_core._fetch_new_anime_from_api()

    # ==================== 排程任務 ====================

    # 排程分發器：在「下一個待推送時刻」精確喚醒 → 推送 → 睡到下一個時刻
    # 簡化版：無預熱，時間到直接查 API 推送；重試邏輯在 push_core 內部處理
    async def _schedule_dispatcher(self):
        """背景任務：精確在每個 scheduled_time 喚醒並推送"""
        logger = logging.getLogger(__name__)
        logger.info("🚀 [_schedule_dispatcher] 排程分發器啟動")

        # 等待 bot ready，但設 timeout 防止卡死
        try:
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
            logger.info("✅ [_schedule_dispatcher] bot ready，開始執行排程分發")
        except asyncio.TimeoutError:
            logger.error("❌ [_schedule_dispatcher] wait_until_ready() timeout 60s，終止任務")
            return

        # 啟動時檢查 week_start_date 是否為本週（防止跨週重啟帶舊資料）
        now = datetime.now(TW_TZ)
        expected_week_start = self.get_week_start_date(now, api_week=True)
        logger.info(
            f"📅 [_schedule_dispatcher] 啟動驗證：期望週起始日期={expected_week_start}，今日={now.strftime('%Y-%m-%d %a')}"
        )

        while not self.bot.is_closed():
            try:
                now = datetime.now(TW_TZ)
                today_schedule = self.get_today_schedule()

                # Debug: log today's schedule status
                pending_count = sum(1 for item in today_schedule if not item["pushed"])
                logger.info(
                    f"🔍 [_schedule_dispatcher] 今日時程 {len(today_schedule)} 部動畫，待推送 {pending_count} 部"
                )

                # 如果 today_schedule 為空，嘗試從 API 拉取週表
                if not today_schedule:
                    logger.warning("⚠️ [_schedule_dispatcher] today_schedule 為空，嘗試從 API 拉取週表...")
                    await self._init_weekly_schedule_if_empty()
                    today_schedule = self.get_today_schedule()
                    if not today_schedule:
                        logger.warning("⚠️ [_schedule_dispatcher] 週表初始化後仍為空，睡到明天 00:00 重試")
                        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        sleep_seconds = (tomorrow - now).total_seconds()
                        await asyncio.sleep(sleep_seconds)
                        continue

                # 找出今天「有未推送動畫」且「時間 >= 現在」的最早時段
                next_scheduled = None
                for item in today_schedule:
                    if item["pushed"]:
                        continue
                    scheduled = item["scheduled_time"]
                    try:
                        datetime.strptime(scheduled, "%H:%M")  # 驗證格式
                        next_scheduled = scheduled
                        break
                    except ValueError as e:
                        logger.warning(f"⚙ 無法解析排程時間 '{scheduled}': {e}")
                    except Exception as e:
                        logger.error(f"❌ 處理排程時間錯誤 '{scheduled}': {e}", exc_info=True)

                if next_scheduled:
                    scheduled = next_scheduled
                    # 計算要睡多久（秒）
                    try:
                        sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ 無法解析時間 '{scheduled}': {e}")
                        continue

                    sleep_seconds = (sched_dt - now).total_seconds()

                    # 如果排程時間已過（負數），立即推送（catchup 情況）
                    if sleep_seconds < 0:
                        logger.info(f"⏰ [_schedule_dispatcher] {scheduled} 時間已過 ({abs(sleep_seconds):.0f}s)，立即推送")
                        sleep_seconds = 0
                    else:
                        logger.info(f"😴 [_schedule_dispatcher] 下一檔 {scheduled}，睡 {sleep_seconds:.0f} 秒")

                    # 睡到排程時間（最多 24 小時防呆）
                    if sleep_seconds > 0:
                        await asyncio.sleep(min(sleep_seconds, 86400))

                    # 時間到 → 推送（重試邏輯在 push_core 內部）
                    now = datetime.now(TW_TZ)
                    logger.info(f"⏰ [_schedule_dispatcher] 時間到 {scheduled}，開始推送（當前 {now.strftime('%H:%M:%S')}）")

                    success = await self.send_anime_push(
                        scheduled,
                        push_core.ANIME_CHANNEL_ID,
                    )
                    if success:
                        logger.info(f"✅ [_schedule_dispatcher] {scheduled} 推送完成")
                    else:
                        logger.warning(f"⚠️ [_schedule_dispatcher] {scheduled} 推送未完成（可能無匹配動畫或 API 暫時無回應），下一輪重試")
                        # 短暫等待避免緊迴圈
                        await asyncio.sleep(30)
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
        """每天晚上 22:00 拉取完整週表全量覆蓋（不做補推，補推由 dispatcher 自動處理）"""
        logger = logging.getLogger(__name__)
        result = await self.schedule_tracker.refresh_weekly_schedule()

        if not result.get("success"):
            if result.get("skipped"):
                return  # 非 22:00 靜默跳過
            logger.error(f"❌ [refresh_weekly_schedule] 週表刷新失敗: {result.get('error')}")
            return

        logger.info(
            f"✅ [refresh_weekly_schedule] 週表刷新完成: {result.get('total_count', 0)} 筆時程"
        )
        # 補推邏輯移至 dispatcher：重啟時會自動處理已過時段
        # 也可手動呼叫 catchup_missed_pushes()

    async def catchup_missed_pushes(self) -> int:
        """手動/啟動時補推：檢查今日已過去時段且未推送的項目"""
        logger = logging.getLogger(__name__)
        now = datetime.now(TW_TZ)
        current_time_str = now.strftime("%H:%M")
        today_schedule = self.get_today_schedule()

        missed_times = set()
        for item in today_schedule:
            if item["pushed"]:
                continue
            scheduled = item["scheduled_time"]
            try:
                if scheduled <= current_time_str:
                    missed_times.add(scheduled)
            except Exception as e:
                logger.error(f"❌ [catchup] 處理時刻錯誤 '{scheduled}': {e}")

        if not missed_times:
            logger.info("ℹ️ [catchup] 無漏推項目")
            return 0

        missed_sorted = sorted(missed_times)
        logger.info(f"📺 [catchup] 發現 {len(missed_sorted)} 個漏推時段，開始補推")
        success_count = 0
        for scheduled in missed_sorted:
            success = await self.send_anime_push(scheduled, push_core.ANIME_CHANNEL_ID)
            if success:
                success_count += 1
            await asyncio.sleep(1)
        logger.info(f"✅ [catchup] 補推完成：成功 {success_count}/{len(missed_sorted)}")
        return success_count

    @tasks.loop(hours=6)
    async def sync_episode_stats(self):
        """每 6 小時同步 episode 統計 + 檢查週日週統發送"""
        try:
            now = datetime.now(TW_TZ)
            logger.info(f"🔄 [sync_episode_stats] 開始同步 (time: {now.strftime('%Y-%m-%d %H:%M:%S')})")

            # 1. 同步 episode 統計數據（每 6 小時）
            await self.ranking_stats.sync_episode_stats()

            # 2. 檢查是否為週日 23:00，發送週統計
            if now.weekday() == 6 and now.hour == 23:
                logger.info("📊 [sync_episode_stats] 偵測到週日 23 時，嘗試發送週統計...")
                await self.ranking_stats.send_weekly_stats()
            else:
                logger.debug(f"⏭️ [sync_episode_stats] 非週統時間 ({now.strftime('%a %H:%M')})，僅同步統計")

        except Exception as e:
            logger.error(f"❌ [sync_episode_stats] 執行異常: {e}", exc_info=True)

    # ==================== 任務啟動和錯誤處理 ====================

    @refresh_weekly_schedule.before_loop
    async def before_refresh_weekly_schedule(self):
        """等待 bot 就緒，並對齊到每天晚上 22:00 執行"""
        logger = logging.getLogger(__name__)
        max_retries = 3
        retry_delay = 10  # 秒

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"🔄 [before_refresh_weekly_schedule] 嘗試啟動 (第 {attempt}/{max_retries} 次)"
                )

                # 等待 bot ready，設 timeout 防止永遠卡住
                try:
                    await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
                    logger.info("✅ [before_refresh_weekly_schedule] bot ready")
                except asyncio.TimeoutError:
                    logger.error(
                        "❌ [before_refresh_weekly_schedule] wait_until_ready() timeout 60s"
                    )
                    raise

                # 計算距離下一次 22:00 的秒數
                now = datetime.now(TW_TZ)
                next_run = now.replace(hour=22, minute=0, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)

                sleep_seconds = (next_run - now).total_seconds()
                logger.info(
                    f"⏳ [refresh_weekly_schedule] 首次執行將在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({sleep_seconds:.0f} 秒後)"
                )

                # 睡眠直到目標時間，可被取消
                await asyncio.sleep(sleep_seconds)
                logger.info(
                    "✅ [before_refresh_weekly_schedule] 對齊完成，任務即將開始"
                )
                return  # 成功啟動，離開重試迴圈

            except asyncio.CancelledError:
                logger.info("🛑 [before_refresh_weekly_schedule] 任務被取消")
                raise
            except Exception as e:
                logger.error(
                    f"❌ [before_refresh_weekly_schedule] 第 {attempt} 次嘗試失敗: {e}",
                    exc_info=True,
                )
                if attempt < max_retries:
                    logger.info(
                        f"⏳ [before_refresh_weekly_schedule] {retry_delay} 秒後重試..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical(
                        f"💥 [before_refresh_weekly_schedule] 重試 {max_retries} 次均失敗，任務將不會啟動！"
                    )
                    raise

    @refresh_weekly_schedule.error
    async def refresh_weekly_schedule_error(self, error):
        """處理任務異常"""
        logger = logging.getLogger(__name__)
        logger.error(f"❌ [refresh_weekly_schedule] 任務異常: {error}", exc_info=True)

    @sync_episode_stats.before_loop
    async def before_sync_episode_stats(self):
        """等待 bot 就緒"""
        logger = logging.getLogger(__name__)
        max_retries = 3
        retry_delay = 10

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"🔄 [before_sync_episode_stats] 嘗試啟動 (第 {attempt}/{max_retries} 次)"
                )
                await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
                logger.info("✅ [before_sync_episode_stats] bot ready")
                return
            except asyncio.CancelledError:
                logger.info("🛑 [before_sync_episode_stats] 任務被取消")
                raise
            except asyncio.TimeoutError:
                logger.error(
                    f"❌ [before_sync_episode_stats] 第 {attempt} 次 wait_until_ready() timeout"
                )
            except Exception as e:
                logger.error(
                    f"❌ [before_sync_episode_stats] 第 {attempt} 次嘗試失敗: {e}",
                    exc_info=True,
                )

            if attempt < max_retries:
                logger.info(f"⏳ [before_sync_episode_stats] {retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)
            else:
                logger.critical(
                    f"💥 [before_sync_episode_stats] 重試 {max_retries} 次均失敗，任務將不會啟動！"
                )
                raise

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
                video_sn = episode.get("videoSn")
                anime_sn = episode.get("animeSn")
                episode_num = episode.get("episodeNum", "")
                views = self._extract_view_count_from_episode(episode)
                score = episode.get("score", 0.0)

                if video_sn and anime_sn:
                    self.record_episode_stats(
                        video_sn, anime_sn, episode_num, views, score
                    )
                    processed_count += 1

            logger = logging.getLogger(__name__)
            logger.info(
                f"📊 [_sync_episode_stats_from_api] 同步了 {processed_count} 筆劇集統計數據"
            )
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                f"❌ [_sync_episode_stats_from_api] 同步失敗: {e}", exc_info=True
            )

    # ==================== 輔助類：AnimeVoteView (保持在主類中，因為它需要引用主類) ====================

    class AnimeVoteView(PersistentViewBase):
        """動畫投票視圖 - 6 個投票按鈕 + 評論按鈕 (永久視圖)

        繼承 PersistentViewBase 確保 timeout=None 且符合專案永久視圖規範。
        """

        # 投票類型配置
        VOTE_TYPES = {
            "masterpiece": ("神作", "🟩"),  # 綠
            "great": ("佳作", "🟦"),  # 藍
            "darkhorse": ("黑馬", "🟪"),  # 紫
            "decent": ("普作/小品", "🟨"),  # 黃
            "controversial": ("爭議作", "🟧"),  # 橙
            "disaster": ("雷作/糞作", "🟥"),  # 紅
        }

        def __init__(self, episode: Dict, anime_tracker: "AnimeTracker"):
            # 永久視圖設置：timeout=None 由 PersistentViewBase 自動處理
            super().__init__()
            self.episode = episode
            self.tracker = anime_tracker
            self.video_sn = episode.get("videoSn")
            self.anime_sn = episode.get("animeSn")
            self.message_id = None
            self.last_interaction_time = None  # 用於追蹤最後互動時間

            logger = logging.getLogger(__name__)
            logger.info(
                f"📌 [AnimeVoteView.__init__] 開始創建視圖，video_sn={self.video_sn}"
            )

            # 添加投票按鈕
            button_count = 0
            for vote_key, (vote_label, color_emoji) in self.VOTE_TYPES.items():
                # 所有投票按鈕都用灰色
                button_style = discord.ButtonStyle.secondary  # 灰色

                button = discord.ui.Button(
                    label=f"{color_emoji} {vote_label}",
                    custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                    style=button_style,
                )
                button.callback = self._vote_callback
                self.add_item(button)
                button_count += 1

            logger.info(f"✅ [AnimeVoteView.__init__] 添加了 {button_count} 個投票按鈕")

            # 添加評論按鈕
            comment_button = discord.ui.Button(
                label="💬 留言",
                custom_id=f"anime_comment_{self.video_sn}",
                style=discord.ButtonStyle.secondary,  # 灰色
            )
            comment_button.callback = self._comment_callback
            self.add_item(comment_button)

            logger.info(
                f"✅ [AnimeVoteView.__init__] 添加了評論按鈕，目前共有 {len(self.children)} 個項目"
            )

        async def _vote_callback(self, interaction: discord.Interaction):
            """處理投票按鈕點擊 - 投票 +2000 KK幣（每個用戶每條消息只適用一次）"""
            try:
                logger = logging.getLogger(__name__)
                logger.info(
                    f"🎯 [_vote_callback] 用戶 {interaction.user.name}({interaction.user.id}) 點擊投票按鈕"
                )
                logger.info(
                    f"   custom_id={interaction.custom_id}, message_id={interaction.message.id}"
                )

                # 🔑 關鍵：立即 defer() 回應 Discord，避免 3 秒超時
                await interaction.response.defer()
                logger.info("✅ [_vote_callback] defer() 已執行")

                # 記錄互動時間
                self.last_interaction_time = datetime.now(TW_TZ)

                # 解析投票類型
                vote_key = interaction.custom_id.replace("anime_vote_", "").rsplit(
                    "_", 1
                )[0]
                vote_label, _ = self.VOTE_TYPES.get(vote_key, ("未知", None))

                # 獲取用戶的匿名雜湊（用來防止同一用戶多次投票）
                user_hash = str(hash(interaction.user.id))[:10]

                # 取得動畫名稱
                anime_name = self.episode.get("title", "") if self.episode else ""

                # 記錄投票 - 使用 message.id 持久化視圖重啟後需要從 storage 獲取
                message_id = interaction.message.id if interaction.message else None
                vote_recorded = self.tracker.record_vote(
                    video_sn=self.video_sn,
                    anime_sn=self.anime_sn,
                    message_id=message_id,
                    vote_type=vote_key,
                    user_hash=user_hash,
                    anime_name=anime_name,
                )

                if not vote_recorded:
                    logger.error(
                        f"❌ [_vote_callback] 投票記錄失敗 (resource 回傳 False): user={interaction.user.name}, vote_key={vote_key}"
                    )
                else:
                    logger.info(
                        f"✅ [_vote_callback] 投票已記錄: {interaction.user.name} 投票了 {vote_label}"
                    )

                # === KK幣獎勵邏輯 (投票 +2000) ===
                reward_given = False
                try:
                    # 使用非同步 DB 適配器
                    # from db_adapter import set_user_field, get_user_field

                    # 檢查是否已發放過獎勵 - 使用 message_id
                    reward_message_id = (
                        interaction.message.id if interaction.message else None
                    )
                    if (
                        reward_message_id
                        and not self.tracker.db.is_reward_already_given(
                            interaction.user.id, reward_message_id, "vote"
                        )
                    ):
                        # 獲取當前 KK幣
                        current_kkcoin = (
                            await async_get_user_field(interaction.user.id, "kkcoin") or 0
                        )
                        new_kkcoin = int(current_kkcoin) + 2000

                        # 更新 KK幣
                        await async_set_user_field(interaction.user.id, "kkcoin", new_kkcoin)

                        # 記錄獎勵發放
                        self.tracker.db.record_reward(
                            user_id=interaction.user.id,
                            message_id=reward_message_id,
                            reward_type="vote",
                            reward_amount=2000,
                        )

                        logger.info(
                            f"💰 [_vote_callback] {interaction.user.name} 投票獲得 2000 KK幣，現在共有 {new_kkcoin} KK幣"
                        )
                        reward_given = True
                    else:
                        logger.info(
                            f"⏭️ [_vote_callback] {interaction.user.name} 已獲得過該消息的投票獎勵"
                        )
                except ImportError:
                    logger.warning(
                        "⚠️ [_vote_callback] db_adapter 未找到，無法獎勵 KK幣"
                    )
                except Exception as e:
                    logger.error(
                        f"❌ [_vote_callback] 獎勵 KK幣失敗: {e}", exc_info=True
                    )

                # 🔑 先發送 follow-up 確認給用戶（優先回應，避免延遲）
                try:
                    reward_text = (
                        "💰 +2000 KK幣獎勵已發放！"
                        if reward_given
                        else "⏭️ 您已領取過此推送的投票獎勵"
                    )
                    await interaction.followup.send(
                        f"✅ 投票成功！{vote_label}\n{reward_text}", ephemeral=True
                    )
                    logger.info(
                        f"✅ [_vote_callback] 已發送 follow-up 確認給 {interaction.user.name}"
                    )
                except Exception as followup_error:
                    logger.error(
                        f"❌ [_vote_callback] 發送 follow-up 失敗: {followup_error}"
                    )

                # 更新原始消息的 embed（非關鍵路徑，失敗不影響用戶體驗）
                try:
                    message_id = interaction.message.id if interaction.message else None
                    if message_id:
                        update_success = await self._update_message_stats(
                            message_id=message_id, channel=interaction.channel
                        )
                        if not update_success:
                            logger.warning(
                                f"⚠️ [_vote_callback] 消息統計更新失敗，但投票已記錄: message_id={message_id}"
                            )
                            # 通知用戶統計更新失敗
                            try:
                                await interaction.followup.send(
                                    "⚠️ 投票已記錄，但無法更新原訊息的統計顯示（可能是權限或訊息已刪除）",
                                    ephemeral=True,
                                )
                            except:
                                pass
                    logger.info(
                        f"✅ [_vote_callback] {interaction.user.name} 的投票已記錄"
                    )
                except Exception as update_error:
                    logger.error(
                        f"❌ [_vote_callback] 更新消息統計失敗: {update_error}",
                        exc_info=True,
                    )

            except Exception as e:
                logger.error(f"❌ [_vote_callback] 投票失敗: {e}", exc_info=True)
                try:
                    # 如果已經 defer 過了，用 followup；否則用 response
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            f"❌ 投票失敗: {str(e)[:50]}", ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ 投票失敗: {str(e)[:50]}", ephemeral=True
                        )
                except:
                    pass

        async def _comment_callback(self, interaction: discord.Interaction):
            """處理評論按鈕點擊 - 彈出評論輸入框"""
            try:
                logger = logging.getLogger(__name__)
                # 記錄互動時間
                self.last_interaction_time = datetime.now(TW_TZ)

                # 捕獲外部 self (AnimeVoteView) 供內部類別使用
                outer_self = self

                # 創建簡單的文本輸入模態框
                class CommentModal(discord.ui.Modal, title="留下匿名評論"):
                    comment_input = discord.ui.TextInput(
                        label="評論內容",
                        placeholder="寫下你對這部動畫的看法...",
                        max_length=200,
                        required=False,
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            comment = str(self.comment_input).strip()
                            if not comment:
                                await modal_interaction.response.send_message(
                                    "評論不能為空", ephemeral=True
                                )
                                return

                            # 獲取用戶匿名雜湊
                            user_hash = str(hash(modal_interaction.user.id))[:10]

                            # 🔑 修復：使用 outer_self.message_id（view 儲存的 message_id），因為 modal_interaction.message 為 None
                            message_id = outer_self.message_id
                            # 取得動畫名稱
                            anime_name = (
                                outer_self.episode.get("title", "")
                                if outer_self.episode
                                else ""
                            )
                            vote_recorded = outer_self.tracker.record_vote(
                                video_sn=outer_self.video_sn,
                                anime_sn=outer_self.anime_sn,
                                message_id=message_id,
                                vote_type="comment",
                                comment=comment,
                                user_hash=user_hash,
                                anime_name=anime_name,
                            )

                            if not vote_recorded:
                                logger.error(
                                    f"❌ [comment_submit] 評論記錄失敗 (resource 回傳 False): user={modal_interaction.user}"
                                )
                            else:
                                logger.info(
                                    f"💬 [comment] {modal_interaction.user} 留言: {comment[:30]}..."
                                )

                            # === KK幣獎勵邏輯 (評論 +3000) ===
                            reward_message = "✅ 評論已保存！感謝你的意見"
                            try:
                                # from db_adapter import set_user_field, get_user_field

                                # 檢查是否已發放過獎勵 - 使用 view 的 message_id
                                if (
                                    message_id
                                    and not outer_self.tracker.db.is_reward_already_given(
                                        modal_interaction.user.id, message_id, "comment"
                                    )
                                ):
                                    # 獲取當前 KK幣
                                    current_kkcoin = (
                                        await async_get_user_field(
                                            modal_interaction.user.id, "kkcoin"
                                        )
                                        or 0
                                    )
                                    new_kkcoin = int(current_kkcoin) + 3000

                                    # 更新 KK幣
                                    await async_set_user_field(
                                        modal_interaction.user.id, "kkcoin", new_kkcoin
                                    )

                                    # 記錄獎勵發放
                                    outer_self.tracker.db.record_reward(
                                        user_id=modal_interaction.user.id,
                                        message_id=message_id,
                                        reward_type="comment",
                                        reward_amount=3000,
                                    )

                                    logger.info(
                                        f"💰 [comment_submit] {modal_interaction.user} 評論獲得 3000 KK幣，現在共有 {new_kkcoin} KK幣"
                                    )
                                    reward_message = (
                                        "✅ 評論已保存！\n💰 +3000 KK幣獎勵已發放"
                                    )
                                else:
                                    logger.info(
                                        f"⏭️ [comment_submit] {modal_interaction.user} 已獲得過該消息的評論獎勵"
                                    )
                                    reward_message = "✅ 評論已保存！"
                            except ImportError:
                                logger.warning(
                                    "⚠️ [comment_submit] db_adapter 未找到，無法獎勵 KK幣"
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ [comment_submit] 獎勵 KK幣失敗: {e}",
                                    exc_info=True,
                                )

                            await modal_interaction.response.send_message(
                                reward_message, ephemeral=True
                            )

                            # 更新原始消息統計 - 使用 view 的 message_id
                            try:
                                if message_id:
                                    update_success = (
                                        await outer_self._update_message_stats(
                                            message_id=message_id,
                                            channel=modal_interaction.channel,
                                        )
                                    )
                                    if not update_success:
                                        logger.warning(
                                            f"⚠️ [comment_submit] 消息統計更新失敗: message_id={message_id}"
                                        )
                                        try:
                                            await modal_interaction.followup.send(
                                                "⚠️ 評論已保存，但無法更新原訊息的統計顯示",
                                                ephemeral=True,
                                            )
                                        except:
                                            pass
                                logger.info(
                                    f"✅ [comment_submit] {modal_interaction.user} 的評論已保存"
                                )
                            except Exception as update_error:
                                logger.error(
                                    f"❌ [comment_submit] 更新消息統計失敗: {update_error}",
                                    exc_info=True,
                                )
                        except Exception as e:
                            logger.error(
                                f"❌ [comment_submit] 保存評論失敗: {e}", exc_info=True
                            )
                            try:
                                await modal_interaction.response.send_message(
                                    f"❌ 評論失敗: {str(e)[:50]}", ephemeral=True
                                )
                            except:
                                pass

                # 發送 Modal（在 _comment_callback 中，不在 on_submit 中）
                await interaction.response.send_modal(CommentModal())

            except Exception as e:
                logger.error(f"❌ [_comment_callback] 評論失敗: {e}", exc_info=True)
                try:
                    await interaction.response.send_message(
                        f"❌ 無法開啟評論: {str(e)[:50]}", ephemeral=True
                    )
                except:
                    pass

        async def _update_message_stats(
            self, message_id: int, channel: discord.abc.Messageable = None
        ) -> bool:
            """更新消息中的投票統計 - 支持通過 message_id 獲取消息（持久化視圖重啟後需要）

            Returns:
                bool: True if update succeeded, False otherwise
            """
            try:
                logger = logging.getLogger(__name__)

                # 獲取消息對象
                message = None
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        logger.info(
                            f"📝 [_update_message_stats] 從頻道獲取消息 ID={message_id}"
                        )
                    except discord.NotFound:
                        logger.warning(
                            f"⚠️ [_update_message_stats] 消息不存在 ID={message_id}"
                        )
                        return False
                    except discord.Forbidden:
                        logger.error(
                            f"❌ [_update_message_stats] 無權限獲取消息 ID={message_id}"
                        )
                        return False
                    except Exception as e:
                        logger.error(
                            f"❌ [_update_message_stats] 獲取消息失敗: {e}",
                            exc_info=True,
                        )
                        return False

                if not message:
                    logger.warning(
                        f"⚠️ [_update_message_stats] 無法獲取消息 ID={message_id}"
                    )
                    return False

                logger.info(
                    f"📝 [_update_message_stats] 開始更新消息 ID={message.id}, 頻道 ID={message.channel.id}"
                )

                if not message.embeds:
                    logger.warning(
                        f"⚠️ [_update_message_stats] 消息沒有 embed, message_id={message.id}"
                    )
                    return False

                original_embed = message.embeds[0]
                logger.info(
                    f"✅ [_update_message_stats] 找到 embed, 標題={original_embed.title}"
                )

                # 獲取投票統計和評論 - 使用 message_id 查詢 DB
                stats = self.tracker.get_vote_stats(message_id)
                comments = self.tracker.get_vote_comments(message_id, limit=3)
                logger.info(
                    f"📊 [_update_message_stats] 投票統計: {stats}, 評論數: {len(comments)}"
                )

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
                # 🔑 修復：確保 color 和 timestamp 處理正確
                embed_color = original_embed.color
                if embed_color is None:
                    embed_color = discord.Color.from_rgb(178, 108, 196)  # 預設紫色

                embed_timestamp = original_embed.timestamp

                new_embed = discord.Embed(
                    title=original_embed.title,
                    description=original_embed.description,
                    color=embed_color,
                    timestamp=embed_timestamp,
                )

                # 複製原有的字段，除了統計和評論
                for field in original_embed.fields:
                    if field.name not in ["📊 投票統計", "💬 匿名評論"]:
                        new_embed.add_field(
                            name=field.name, value=field.value, inline=field.inline
                        )

                # 添加更新後的統計
                if stats_content:
                    new_embed.add_field(
                        name="📊 投票統計", value=stats_content, inline=False
                    )

                # 添加更新後的評論
                if comments_content:
                    new_embed.add_field(
                        name="💬 匿名評論", value=comments_content, inline=False
                    )

                # 複製 footer、author 等其他屬性
                if original_embed.footer:
                    new_embed.set_footer(
                        text=original_embed.footer.text,
                        icon_url=original_embed.footer.icon_url,
                    )
                if original_embed.author:
                    new_embed.set_author(
                        name=original_embed.author.name,
                        url=original_embed.author.url,
                        icon_url=original_embed.author.icon_url,
                    )
                if original_embed.image:
                    new_embed.set_image(url=original_embed.image.url)
                if original_embed.thumbnail:
                    new_embed.set_thumbnail(url=original_embed.thumbnail.url)

                # 編輯消息
                logger.info(
                    f"🔄 [_update_message_stats] 準備編輯消息 ID={message.id}, 頻道={message.channel.id}, 權限={message.channel.permissions_for(message.guild.me) if message.guild else 'DM'}"
                )
                await message.edit(embed=new_embed)
                logger.info(
                    f"✅ [_update_message_stats] 消息已成功編輯 ID={message.id}"
                )
                return True

            except discord.Forbidden as e:
                logger.error(
                    f"❌ [_update_message_stats] 權限不足無法編輯消息: {e}",
                    exc_info=True,
                )
                return False
            except discord.NotFound as e:
                logger.error(
                    f"❌ [_update_message_stats] 消息不存在或已被刪除: {e}",
                    exc_info=True,
                )
                return False
            except discord.HTTPException as e:
                logger.error(
                    f"❌ [_update_message_stats] Discord HTTP 錯誤 (可能 embed 過大或格式錯誤): {e}",
                    exc_info=True,
                )
                return False
            except Exception as e:
                logger.error(
                    f"❌ [_update_message_stats] 更新統計失敗: {e}", exc_info=True
                )
                return False

    # ==================== 診斷用指令 ====================

    @app_commands.command(
        name="anime_vote_debug", description="🔍 診斷動畫投票統計更新問題（管理員）"
    )
    @app_commands.describe(message_id="要檢查的訊息 ID")
    @app_commands.default_permissions(administrator=True)
    async def anime_vote_debug(self, interaction: discord.Interaction, message_id: str):
        """診斷指定訊息的投票統計更新狀態"""
        await interaction.response.defer(ephemeral=True)
        logger = logging.getLogger(__name__)

        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send("❌ 無效的訊息 ID", ephemeral=True)
            return

        # 1. 檢查資料庫中的投票統計
        stats = self.tracker.get_vote_stats(msg_id)
        comments = self.tracker.get_vote_comments(msg_id, limit=5)

        # 2. 嘗試獲取 Discord 訊息
        message = None
        fetch_error = None
        try:
            if interaction.channel:
                message = await interaction.channel.fetch_message(msg_id)
        except discord.NotFound:
            fetch_error = "訊息不存在 (已刪除或 ID 錯誤)"
        except discord.Forbidden:
            fetch_error = "無權限讀取該頻道訊息"
        except Exception as e:
            fetch_error = f"獲取失敗: {e}"

        # 3. 檢查是否在資料庫的 anime_messages 表中
        db_msg_info = None
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT messageId, videoSn, animeSn, anime_name, channelId, createdAt
                    FROM {ANIME_MESSAGES_TABLE}
                    WHERE messageId = ?
                """,
                    (msg_id,),
                )
                row = cursor.fetchone()
                if row:
                    db_msg_info = {
                        "messageId": row[0],
                        "videoSn": row[1],
                        "animeSn": row[2],
                        "anime_name": row[3],
                        "channelId": row[4],
                        "createdAt": row[5],
                    }
        except Exception as e:
            logger.error(f"❌ [anime_vote_debug] 查詢 anime_messages 失敗: {e}")

        # 建構回報
        embed = discord.Embed(
            title="🔍 動畫投票統計診斷",
            color=discord.Color.blue(),
            timestamp=datetime.now(TW_TZ),
        )
        embed.add_field(name="📨 訊息 ID", value=str(msg_id), inline=False)

        # 資料庫統計
        if stats:
            stats_text = "\n".join([f"{k}: {v} 票" for k, v in stats.items()])
        else:
            stats_text = "無投票記錄"
        embed.add_field(name="📊 資料庫投票統計", value=stats_text, inline=False)

        if comments:
            comments_text = "\n".join(
                [f"• {c[:50]}..." if len(c) > 50 else f"• {c}" for c in comments]
            )
        else:
            comments_text = "無評論"
        embed.add_field(name="💬 資料庫評論", value=comments_text, inline=False)

        # Discord 訊息狀態
        if message:
            embed.add_field(
                name="📨 Discord 訊息",
                value=f"✅ 找到 (頻道: {message.channel.name})",
                inline=False,
            )
            if message.embeds:
                embed.add_field(
                    name="📎 Embed 狀態",
                    value=f"✅ 有 {len(message.embeds)} 個 embed",
                    inline=False,
                )
                # 檢查 embed 是否已有統計欄位
                orig_embed = message.embeds[0]
                has_stats_field = any(
                    f.name == "📊 投票統計" for f in orig_embed.fields
                )
                has_comments_field = any(
                    f.name == "💬 匿名評論" for f in orig_embed.fields
                )
                embed.add_field(
                    name="📋 Embed 統計欄位",
                    value=f"投票統計: {'✅' if has_stats_field else '❌'}\n評論: {'✅' if has_comments_field else '❌'}",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="📎 Embed 狀態", value="❌ 訊息無 embed", inline=False
                )
        else:
            embed.add_field(
                name="📨 Discord 訊息",
                value=f"❌ {fetch_error or '未知錯誤'}",
                inline=False,
            )

        # 資料庫記錄
        if db_msg_info:
            embed.add_field(
                name="🗄️ anime_messages 記錄",
                value=f"videoSn: {db_msg_info['videoSn']}\nanimeSn: {db_msg_info['animeSn']}\n頻道: {db_msg_info['channelId']}\n時間: {db_msg_info['createdAt']}",
                inline=False,
            )
        else:
            embed.add_field(
                name="🗄️ anime_messages 記錄", value="❌ 找不到記錄", inline=False
            )

        # 權限檢查
        if message and message.guild:
            perms = message.channel.permissions_for(message.guild.me)
            embed.add_field(
                name="🔐 Bot 權限",
                value=f"管理訊息: {'✅' if perms.manage_messages else '❌'}\n嵌入連結: {'✅' if perms.embed_links else '❌'}\n讀取訊息: {'✅' if perms.read_messages else '❌'}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(
            f"🔍 [/anime_vote_debug] 管理員 {interaction.user} 診斷訊息 {msg_id}"
        )

    @app_commands.command(
        name="anime_vote_force_update",
        description="🔧 強制更新指定訊息的投票統計（管理員）",
    )
    @app_commands.describe(message_id="要更新的訊息 ID")
    @app_commands.default_permissions(administrator=True)
    async def anime_vote_force_update(
        self, interaction: discord.Interaction, message_id: str
    ):
        """強制觸發指定訊息的統計更新"""
        await interaction.response.defer(ephemeral=True)
        logger = logging.getLogger(__name__)

        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send("❌ 無效的訊息 ID", ephemeral=True)
            return

        success = await self._update_message_stats(msg_id, interaction.channel)
        if success:
            await interaction.followup.send(
                f"✅ 強制更新成功：訊息 {msg_id} 的投票統計已刷新", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ 強制更新失敗：請檢查日誌或使用 `/anime_vote_debug` 診斷",
                ephemeral=True,
            )
        logger.info(
            f"🔧 [/anime_vote_force_update] 管理員 {interaction.user} 強制更新訊息 {msg_id}, 結果: {success}"
        )

    @app_commands.command(
        name="anime_refresh", description="🔄 手動刷新動畫週表（緊急補推用）"
    )
    @app_commands.default_permissions(administrator=True)
    async def anime_refresh(self, interaction: discord.Interaction):
        """手動觸發週表刷新，解決自動刷新失敗或緊急補推需求"""
        await interaction.response.defer(ephemeral=True)
        logger = logging.getLogger(__name__)
        logger.info(f"🔄 [/anime_refresh] 管理員 {interaction.user} 觸發手動週表刷新")

        try:
            result = await self.refresh_weekly_schedule()

            if result.get("success"):
                embed = discord.Embed(
                    title="✅ 週表刷新成功",
                    description=f"週起始日期: {result['week_start_date']}\n今日時程: {len(result['today_schedule'])} 筆\n總計: {result['total_count']} 筆",
                    color=discord.Color.green(),
                )
                # 檢查是否有待推送項目
                pending = sum(
                    1 for item in result["today_schedule"] if not item.get("pushed")
                )
                if pending > 0:
                    embed.add_field(
                        name="⏳ 待補推項目",
                        value=f"{pending} 部動畫未推送",
                        inline=False,
                    )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(
                    f"✅ [/anime_refresh] 手動刷新完成: {result['total_count']} 筆"
                )
            else:
                error = result.get("error", "未知錯誤")
                skipped = result.get("skipped", False)
                if skipped:
                    await interaction.followup.send(
                        "⏭️ 跳過刷新：非執行時間（每天 22:00-22:59）", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ 刷新失敗: {error}", ephemeral=True
                    )
                logger.warning(f"⚠️ [/anime_refresh] 手動刷新失敗: {error}")
        except Exception as e:
            logger.error(f"❌ [/anime_refresh] 異常: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 執行異常: {e}", ephemeral=True)

    # ==================== 任務重啟包裝函數 ====================

    async def _wrap_task_with_restart(self, name: str, coro_func):
        """通用任務包裝器：異常時自動記錄並在 5 秒後重啟"""
        logger = logging.getLogger(__name__)
        while not self.bot.is_closed():
            try:
                await coro_func()
            except asyncio.CancelledError:
                logger.info(f"🛑 [{name}] 任務被取消")
                break
            except Exception as e:
                logger.error(
                    f"❌ [{name}] 任務異常終止，5 秒後重啟: {e}", exc_info=True
                )
                await asyncio.sleep(5)
                if not self.bot.is_closed():
                    logger.info(f"🔄 [{name}] 重啟任務...")


async def setup(bot: commands.Bot):
    """Setup 函數供 Discord.py 加載 Cog"""
    await bot.add_cog(AnimeTracker(bot))
