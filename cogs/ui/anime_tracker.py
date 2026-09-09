# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 雙系統推送
- 推送系統：使用 AnimePushCore (push_core.py) 基於 anime_push.db 的週表進行精準排程推送，生成 embed
- 輪詢系統：使用 SimpleAnimePushCore (push_core_simple.py) 基於 anime_push.db 的 anime_notified 表進行 15 分鐘輪詢，僅發送圖片+按鈕
兩系統互不共享狀態，各自使用獨立的資料庫連線（但實際指向同一 anime_push.db）
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import discord
from discord.ext import commands
from typing import Optional

from .push_core import AnimePushCore, AnimeDatabase as AnimePushDB
from .push_core_simple import (
    SimpleAnimePushCore,
    ANIME_PUSH_DB_PATH,
    ANIME_CHANNEL_ID,
    TW_TZ,
)

logger = logging.getLogger(__name__)


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤 Cog - 雙系統推送"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.schedule_core = None
        self.polling_core = None
        self.db = None
        self._running = False

    async def set_dependencies(self, db_path: str = None):
        """設置依賴元件 - 初始化兩個推送系統並啟動"""
        if self._running:
            logger.info("[AnimeTracker.set_dependencies] 已運行中，跳過")
            return

        db_path = db_path or str(ANIME_PUSH_DB_PATH)
        logger.info(f"🔧 [AnimeTracker.set_dependencies] 初始化雙系統推送: {db_path}")

        # 初始化獨立資料庫實例（不共享狀態）
        self.schedule_db = AnimePushDB(db_path)  # 推送系統專用連線
        self.polling_db = AnimePushDB(db_path)   # 輪詢系統專用連線

        # 初始化排程推送系統 (embed 版)
        self.schedule_core = AnimePushCore(self.schedule_db)
        self.schedule_core.set_bot(self.bot)

        # 初始化輪詢推送系統 (圖片版)
        self.polling_core = SimpleAnimePushCore(self.polling_db)
        self.polling_core.set_bot(self.bot)

        # 啟動兩個系統
        await self.schedule_core.start_polling(ANIME_CHANNEL_ID)
        await self.polling_core.start_polling(ANIME_CHANNEL_ID)

        self._running = True
        msg = "✅ [AnimeTracker.set_dependencies] 雙系統推送啟動完成 (排程+輪詢)"
        logger.info(msg)

    async def cog_load(self):
        """Cog 載入時執行的初始化"""
        self.logger.info("📺 [AnimeTracker.cog_load] 開始載入 Cog")

        # 如果依賴尚未設置，則自行初始化
        if not self._running:
            self.logger.info("🔧 [AnimeTracker.cog_load] 依賴尚未設置，嘗試自行初始化...")
            try:
                await self.set_dependencies(str(ANIME_PUSH_DB_PATH))
                self.logger.info("✅ [AnimeTracker.cog_load] 依賴自行初始化成功")
            except Exception as e:
                self.logger.error(f"❌ [AnimeTracker.cog_load] 依賴自行初始化失敗: {e}", exc_info=True)
        else:
            self.logger.info("🚀 [AnimeTracker.cog_load] AnimeTracker Cog 載入完成（依賴已就緒）")

    async def cog_unload(self):
        """Cog 卸載時清理"""
        self.logger.info("🛑 [AnimeTracker.cog_unload] 正在停止兩個推送系統...")
        if self._running:
            if self.schedule_core:
                await self.schedule_core.stop_polling()
            if self.polling_core:
                await self.polling_core.stop_polling()
            self._running = False
        self.logger.info("🛑 [AnimeTracker.cog_unload] 兩個推送系統已停止")

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot 就緒事件"""
        self.logger.info("📺 [AnimeTracker.on_ready] AnimeTracker Cog 收到 on_ready 事件")

    # ==================== 指令方法 ====================

    @commands.hybrid_command(name="anime_status", description="查看動畫推送系統狀態")
    @commands.has_permissions(administrator=True)
    async def anime_status(self, ctx: commands.Context):
        """查看動畫推送系統狀態"""
        if hasattr(ctx, 'response'):
            await ctx.response.defer(ephemeral=True)
            send_response = lambda content, ephemeral=True: ctx.followup.send(content, ephemeral=ephemeral)
        else:
            send_response = lambda content: ctx.send(content)

        try:
            status_lines = [
                "📊 **動畫推送系統狀態 (雙系統)**",
                f"🔄 總系統狀態: {'✅ 運行中' if self._running else '❌ 已停止'}",
                f"📊 資料庫: anime_push.db (獨立連線)",
            ]

            # 排程推送系統狀態
            if self.schedule_core:
                schedule_running = getattr(self.schedule_core, '_running', False)
                status_lines.append(f"⏰ 排程推送系統: {'✅ 運行中' if schedule_running else '❌ 已停止'}")

                if schedule_running and self.schedule_db:
                    try:
                        today_schedule = self.schedule_db.get_today_schedule()
                        pending_count = sum(1 for item in today_schedule
                                          if not item.get("pushed", False))
                        status_lines.append(f"📋 排程今日待推送: {pending_count} 項")
                    except Exception as e:
                        self.logger.warning(f"無法獲取排程統計: {e}")

            # 輪詢推送系統狀態
            if self.polling_core:
                polling_running = getattr(self.polling_core, '_running', False)
                status_lines.append(f"🔁 輪詢推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'}")

                if polling_running and self.polling_db:
                    try:
                        notified_count = len(self.polling_db.get_notified_video_sns()) if hasattr(self.polling_db, 'get_notified_video_sns') else 0
                        status_lines.append(f"📼 輪詢已通知動畫數: {notified_count}")
                    except Exception as e:
                        self.logger.warning(f"無法獲取輪詢統計: {e}")

            status_lines.extend([
                f"📋 推送表: anime_weekly_schedule",
                f"📝 通知記錄: anime_notified 表",
                f"⏱️ 排程機制: 智能睡眠直到下次排程時間 (最多30分鐘)",
                f"⏱️ 輪詢機制: 固定15分鐘輪詢",
            ])

            await send_response("\n".join(status_lines), ephemeral=True)
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker.anime_status] 查詢狀態失敗: {e}", exc_info=True)
            await send_response(f"❌ 查詢狀態時發生錯誤: {str(e)}", ephemeral=True)

    @commands.hybrid_command(name="anime_manual_check", description="手動觸發一次動畫檢查")
    @commands.has_permissions(administrator=True)
    async def anime_manual_check(self, ctx: commands.Context):
        """手動觸發一次動畫檢查與推送"""
        if hasattr(ctx, 'response'):
            await ctx.response.defer(ephemeral=True)
            send_response = lambda content, ephemeral=True: ctx.followup.send(content, ephemeral=ephemeral)
        else:
            send_response = lambda content: ctx.send(content)

        try:
            self.logger.info(f"🔄 [AnimeTracker.anime_manual_check] 手動檢查請求 by {ctx.author}")

            if not self.schedule_core or not self.polling_core:
                await send_response("❌ 推送核心未完全初始化", ephemeral=True)
                return

            # 手動觸發兩個系統的檢查
            await send_response("🔄 正在手動檢查排程推送系統...", ephemeral=True)
            await self.schedule_core._check_and_push(ANIME_CHANNEL_ID)

            await send_response("🔄 正在手動檢查輪詢推送系統...", ephemeral=True)
            await self.polling_core._check_and_push(ANIME_CHANNEL_ID)

            await send_response("✅ 手動檢查完成", ephemeral=True)
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker.anime_manual_check] 手動檢查失敗: {e}", exc_info=True)
            await send_response(f"❌ 手動檢查失敗: {str(e)}", ephemeral=True)


async def setup(bot):
    """設置 Cog 的入口點"""
    await bot.add_cog(AnimeTracker(bot))