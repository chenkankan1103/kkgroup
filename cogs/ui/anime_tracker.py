# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 增強版排程推送系統
- 增強版推送系統：使用 SimpleAnimePushCore (push_core_simple.py) 基於 anime_push.db
  實現精準排程推送與15分鐘輪詢備案機制
- 排程推送：基於 anime_weekly_schedule 表在實際播出時間精確推送
- 備案機制：連續3次失敗後自動切換至15分鐘輪詢，恢復條件為成功推送
- 單一資料庫連線：各組件共用同一 anime_push.db 連線
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import discord
from discord.ext import commands, tasks
from typing import Optional
import sys
from pathlib import Path

# Add kkgroup directory to sys.path for absolute imports
kkgroup_dir = Path(__file__).resolve().parent.parent.parent
if str(kkgroup_dir) not in sys.path:
    sys.path.insert(0, str(kkgroup_dir))

from cogs.ui.push_core_simple import (
    SimpleAnimePushCore,
    AnimePushDB,
    ANIME_PUSH_DB_PATH,
    ANIME_CHANNEL_ID,
    TW_TZ,
)
from cogs.ui.schedule_tracker import AnimeScheduleTracker

logger = logging.getLogger(__name__)


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤 Cog - 增強版排程推送系統 (含15分鐘輪詢備案)"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.polling_core = None
        self.db = None
        self.schedule_tracker = None
        self._running = False
        self._push_tick = 0

    async def set_dependencies(self, db_path: str = None):
        """設置依賴元件 - 初始化增強版推送系統並啟動"""
        if self._running:
            # 已初始化過：僅重新註冊按鈕視圖（冪等）。cog_load 早於 on_ready 的
            # logging 設定，第一次執行的日誌會遺失，此處的日誌可見可驗證
            logger.info(
                "[AnimeTracker.set_dependencies] 已運行中，跳過（僅重新註冊視圖）"
            )
            await self.reregister_push_views()
            return

        db_path = db_path or str(ANIME_PUSH_DB_PATH)
        logger.info(
            f"🔧 [AnimeTracker.set_dependencies] 初始化增強版推送系統: {db_path}"
        )

        # 初始化資料庫實例
        self.db = AnimePushDB(db_path)

        # 初始化增強版推送系統 (排程推送 + 15分鐘輪詢備案)
        self.polling_core = SimpleAnimePushCore(self.db)
        self.polling_core.set_bot(self.bot)

        # 啟動推送系統（2026-09-17 修復：改用 tasks.loop 每分鐘檢查。
        # 舊版 start_polling 用 asyncio.create_task 建立循環，task 異常會被困在
        # 無人讀取的 task 物件中（self._task 強引用阻擋 GC），「Task exception
        # was never retrieved」永不觸發 → 推送循環靜默死亡、44 小時零日誌零推送。
        # tasks.loop 每圈接例外、自癒，且錯誤會記入日誌）
        self.polling_core._running = True
        if not self.push_check_loop.is_running():
            self.push_check_loop.start()

        # 初始化週表排程管理器（每天 02:00 刷新 anime_push.db 的 anime_weekly_schedule）
        self.schedule_tracker = AnimeScheduleTracker(str(ANIME_PUSH_DB_PATH))
        self.schedule_tracker.set_dependencies(
            self.bot, self.db, self.polling_core, anime_tracker=self
        )

        # 啟動週表刷新循環（refresh_weekly_schedule 內建 02:00 時間閘門）
        if not self.weekly_schedule_refresh_loop.is_running():
            self.weekly_schedule_refresh_loop.start()

        self._running = True
        msg = "✅ [AnimeTracker.set_dependencies] 增強版推送系統啟動完成 (排程+輪詢備案+週表刷新)"
        logger.info(msg)

        # bot 重啟後重新註冊已推送訊息的按鈕視圖。discord.py 的視圖註冊是
        # in-memory 的，重啟後全部清空，而 AnimePushView 的 custom_id 依集數
        # 動態產生、無法在啟動時全域註冊；未重新註冊時，舊訊息的投票/留言
        # 按鈕點擊會被 dispatch_view 直接丟棄（Discord 顯示「應用程式沒有回應」）
        await self.reregister_push_views()

    async def reregister_push_views(self):
        """掃描推送頻道近期歷史，重建已推送訊息的按鈕視圖並依 message_id 綁定"""
        if not self.bot or not self.db:
            return
        # 延遲載入避免循環匯入（與 push_core_simple._check_and_push 相同模式）
        from shared.utils.embed_views import AnimePushView

        try:
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if channel is None:
                logger.warning(
                    f"⚠️ [AnimeTracker.reregister] 找不到推送頻道 {ANIME_CHANNEL_ID}"
                )
                return

            registered = 0
            seen: set[int] = set()
            async for message in channel.history(limit=300, oldest_first=False):
                if message.id in seen or not message.components:
                    continue
                # 從按鈕 custom_id 辨識動畫推送訊息並解析 video_sn
                video_sn = None
                for row in message.components:
                    for child in row.children:
                        cid = getattr(child, "custom_id", None)
                        if cid and cid.startswith("anime_vote_"):
                            try:
                                video_sn = int(cid.rsplit("_", 1)[1])
                            except (ValueError, IndexError):
                                video_sn = None
                            break
                    if video_sn is not None:
                        break
                if video_sn is None:
                    continue
                seen.add(message.id)

                # AnimePushView 建構需要 videoSn 與 animeSn 同時存在
                info = self.db.get_notified_info(video_sn)
                if not info:
                    logger.warning(
                        f"⚠️ [AnimeTracker.reregister] videoSn={video_sn} "
                        f"不在 anime_notified，跳過"
                    )
                    continue
                anime_sn, anime_name = info
                view = AnimePushView(
                    {"videoSn": video_sn, "animeSn": anime_sn, "title": anime_name},
                    db_adapter=self.db,
                )
                view.message_id = message.id  # 讓留言也能精確記錄到該則 embed
                self.bot.add_view(view, message_id=message.id)
                registered += 1

            logger.info(
                f"✅ [AnimeTracker.reregister] 已重新註冊 {registered} 則"
                f"動畫推送訊息的按鈕視圖"
            )
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.reregister] 失敗: {e}", exc_info=True)

    async def cog_load(self):
        """Cog 載入時執行的初始化"""
        self.logger.info("📺 [AnimeTracker.cog_load] 開始載入 Cog")

        # 如果依賴尚未設置，則自行初始化
        if not self._running:
            self.logger.info(
                "🔧 [AnimeTracker.cog_load] 依賴尚未設置，嘗試自行初始化..."
            )
            try:
                await self.set_dependencies(str(ANIME_PUSH_DB_PATH))
                self.logger.info("✅ [AnimeTracker.cog_load] 依賴自行初始化成功")
            except Exception as e:
                self.logger.error(
                    f"❌ [AnimeTracker.cog_load] 依賴自行初始化失敗: {e}", exc_info=True
                )
        else:
            self.logger.info(
                "🚀 [AnimeTracker.cog_load] AnimeTracker Cog 載入完成（依賴已就緒）"
            )

    async def cog_unload(self):
        """Cog 卸載時清理"""
        self.logger.info("🛑 [AnimeTracker.cog_unload] 正在停止推送系統...")
        if self.push_check_loop.is_running():
            self.push_check_loop.cancel()
        if self.weekly_schedule_refresh_loop.is_running():
            self.weekly_schedule_refresh_loop.cancel()
        if self._running:
            if self.polling_core:
                await self.polling_core.stop_polling()
            self._running = False
        self.logger.info("🛑 [AnimeTracker.cog_unload] 推送系統已停止")

    @tasks.loop(minutes=1)
    async def push_check_loop(self):
        """每分鐘檢查排程推送（2026-09-17 修復：取代易無聲死亡的智能睡眠循環）

        tasks.loop 每圈接例外並繼續（自癒），不像 asyncio.create_task 的 task
        異常會被困在無人讀取的 task 物件中導致靜默死亡。
        """
        if not self.polling_core:
            return
        self._push_tick += 1
        try:
            # 排程推送：每分鐘檢查（_check_and_push 內建 ±1 分鐘容差與
            # is_notified 防重複，同一時刻只會推送一次）
            await self.polling_core._check_and_push(ANIME_CHANNEL_ID)
            # 備案安全網：每 15 分鐘輪詢 API 最新動畫
            # （排程表遺漏的新集數靠此補推，歷史上 51187 即由此路徑推出）
            if self._push_tick % 15 == 0:
                await self.polling_core._check_and_push_polling(ANIME_CHANNEL_ID)
            # 心跳：每小時一筆 INFO，證明循環存活
            # （2026-09-15~17 靜默失效 44 小時無從診斷的教訓）
            if self._push_tick % 60 == 0:
                logger.info(
                    f"💓 [push_check_loop] 循環存活心跳（第 {self._push_tick} 分鐘）"
                )
        except Exception as e:
            logger.error(f"❌ [push_check_loop] 檢查失敗: {e}", exc_info=True)

    @push_check_loop.before_loop
    async def before_push_check_loop(self):
        """等待 bot 就緒後再開始推送檢查循環"""
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=30)
    async def weekly_schedule_refresh_loop(self):
        """每天 02:00 時段刷新週表（refresh_weekly_schedule 內建時間閘門擋掉非 2 點時段）"""
        try:
            result = await self.schedule_tracker.refresh_weekly_schedule()
            if result.get("success"):
                self.logger.info(
                    f"✅ [weekly_schedule_refresh_loop] 週表刷新完成: {result.get('total_count')} 個時刻"
                )
        except Exception as e:
            self.logger.error(
                f"❌ [weekly_schedule_refresh_loop] 週表刷新失敗: {e}", exc_info=True
            )

    @weekly_schedule_refresh_loop.before_loop
    async def before_weekly_schedule_refresh_loop(self):
        """等待 bot 就緒後再開始刷新循環"""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot 就緒事件"""
        self.logger.info(
            "📺 [AnimeTracker.on_ready] AnimeTracker Cog 收到 on_ready 事件"
        )

    # ==================== 指令方法 ====================

    @commands.hybrid_command(name="anime_status", description="查看動畫推送系統狀態")
    @commands.has_permissions(administrator=True)
    async def anime_status(self, ctx: commands.Context):
        """查看動畫推送系統狀態"""
        if hasattr(ctx, "response"):
            await ctx.response.defer(ephemeral=True)
            send_response = lambda content, ephemeral=True: ctx.followup.send(
                content, ephemeral=ephemeral
            )
        else:
            send_response = lambda content: ctx.send(content)

        try:
            status_lines = [
                "📊 **動畫推送系統狀態 (增強版)**",
                f"🔄 總系統狀態: {'✅ 運行中' if self._running else '❌ 已停止'}",
                f"📊 資料庫: anime_push.db",
            ]

            # 推送系統狀態 (現在是增強版：排程推送 + 15分鐘輪詢備案)
            if self.polling_core:
                polling_running = getattr(self.polling_core, "_running", False)
                in_fallback = getattr(self.polling_core, "_in_fallback", False)
                fail_count = getattr(self.polling_core, "_fail_count", 0)
                max_failures = getattr(self.polling_core, "_max_failures", 3)

                if in_fallback:
                    status_lines.append(
                        f"⏰ 推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'} (備案模式: 15分鐘輪詢)"
                    )
                    status_lines.append(f"📉 失敗計數: {fail_count}/{max_failures}")
                else:
                    status_lines.append(
                        f"⏰ 推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'} (排程模式)"
                    )
                    status_lines.append(f"📊 失敗計數: {fail_count}/{max_failures}")

                if polling_running and self.db:
                    try:
                        # 顯示今日待推送數量
                        today_schedule = self.db.get_today_schedule()
                        pending_count = sum(
                            1
                            for item in today_schedule
                            if not item.get("pushed", False)
                        )
                        status_lines.append(f"📋 推程今日待推送: {pending_count} 項")

                        # 顯示已通知的動畫數
                        notified_count = (
                            len(self.db.get_notified_video_sns())
                            if hasattr(self.db, "get_notified_video_sns")
                            else 0
                        )
                        status_lines.append(f"📼 已通知動畫數: {notified_count}")
                    except Exception as e:
                        self.logger.warning(f"無法獲取推送統計: {e}")

            status_lines.extend(
                [
                    f"📋 推送表: anime_weekly_schedule",
                    f"📝 通知記錄: anime_notified 表",
                    f"⏱️ 排程機制: tasks.loop 每分鐘檢查 (±1分鐘容差)",
                    f"⏱️ 備案機制: 每15分鐘輪詢 API 補推排程遺漏的新集數",
                ]
            )

            await send_response("\n".join(status_lines), ephemeral=True)
        except Exception as e:
            self.logger.error(
                f"❌ [AnimeTracker.anime_status] 查詢狀態失敗: {e}", exc_info=True
            )
            await send_response(f"❌ 查詢狀態時發生錯誤: {str(e)}", ephemeral=True)

    @commands.hybrid_command(
        name="anime_manual_check", description="手動觸發一次動畫檢查"
    )
    @commands.has_permissions(administrator=True)
    async def anime_manual_check(self, ctx: commands.Context):
        """手動觸發一次動畫檢查與推送"""
        if hasattr(ctx, "response"):
            await ctx.response.defer(ephemeral=True)
            send_response = lambda content, ephemeral=True: ctx.followup.send(
                content, ephemeral=ephemeral
            )
        else:
            send_response = lambda content: ctx.send(content)

        try:
            self.logger.info(
                f"🔄 [AnimeTracker.anime_manual_check] 手動檢查請求 by {ctx.author}"
            )

            if not self.polling_core:
                await send_response("❌ 推送核心未完全初始化", ephemeral=True)
                return

            # 手動觸發增強版推送系統的檢查 (包含排程推送和輪詢備案)
            await send_response("🔄 正在手動檢查增強版推送系統...", ephemeral=True)
            await self.polling_core._check_and_push(ANIME_CHANNEL_ID)

            await send_response("✅ 手動檢查完成", ephemeral=True)
        except Exception as e:
            self.logger.error(
                f"❌ [AnimeTracker.anime_manual_check] 手動檢查失敗: {e}", exc_info=True
            )
            await send_response(f"❌ 手動檢查失敗: {str(e)}", ephemeral=True)


async def setup(bot):
    """設置 Cog 的入口點"""
    await bot.add_cog(AnimeTracker(bot))
