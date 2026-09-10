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
from discord.ext import commands
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

logger = logging.getLogger(__name__)


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤 Cog - 增強版排程推送系統 (含15分鐘輪詢備案)"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.polling_core = None
        self.db = None
        self._running = False

    async def set_dependencies(self, db_path: str = None):
        """設置依賴元件 - 初始化增強版推送系統並啟動"""
        if self._running:
            logger.info("[AnimeTracker.set_dependencies] 已運行中，跳過")
            return

        db_path = db_path or str(ANIME_PUSH_DB_PATH)
        logger.info(f"🔧 [AnimeTracker.set_dependencies] 初始化增強版推送系統: {db_path}")

        # 初始化資料庫實例
        self.db = AnimePushDB(db_path)

        # 初始化增強版推送系統 (排程推送 + 15分鐘輪詢備案)
        self.polling_core = SimpleAnimePushCore(self.db)
        self.polling_core.set_bot(self.bot)

        # 啟動推送系統
        await self.polling_core.start_polling(ANIME_CHANNEL_ID)

        self._running = True
        msg = "✅ [AnimeTracker.set_dependencies] 增強版推送系統啟動完成 (排程+輪詢備案)"
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
        self.logger.info("🛑 [AnimeTracker.cog_unload] 正在停止推送系統...")
        if self._running:
            if self.polling_core:
                await self.polling_core.stop_polling()
            self._running = False
        self.logger.info("🛑 [AnimeTracker.cog_unload] 推送系統已停止")

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
                "📊 **動畫推送系統狀態 (增強版)**",
                f"🔄 總系統狀態: {'✅ 運行中' if self._running else '❌ 已停止'}",
                f"📊 資料庫: anime_push.db",
            ]

            # 推送系統狀態 (現在是增強版：排程推送 + 15分鐘輪詢備案)
            if self.polling_core:
                polling_running = getattr(self.polling_core, '_running', False)
                in_fallback = getattr(self.polling_core, '_in_fallback', False)
                fail_count = getattr(self.polling_core, '_fail_count', 0)
                max_failures = getattr(self.polling_core, '_max_failures', 3)

                if in_fallback:
                    status_lines.append(f"⏰ 推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'} (備案模式: 15分鐘輪詢)")
                    status_lines.append(f"📉 失敗計數: {fail_count}/{max_failures}")
                else:
                    status_lines.append(f"⏰ 推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'} (排程模式)")
                    status_lines.append(f"📊 失敗計數: {fail_count}/{max_failures}")

                if polling_running and self.db:
                    try:
                        # 顯示今日待推送數量
                        today_schedule = self.db.get_today_schedule()
                        pending_count = sum(1 for item in today_schedule
                                          if not item.get("pushed", False))
                        status_lines.append(f"📋 推程今日待推送: {pending_count} 項")

                        # 顯示已通知的動畫數
                        notified_count = len(self.db.get_notified_video_sns()) if hasattr(self.db, 'get_notified_video_sns') else 0
                        status_lines.append(f"📼 已通知動畫數: {notified_count}")
                    except Exception as e:
                        self.logger.warning(f"無法獲取推送統計: {e}")

            status_lines.extend([
                f"📋 推送表: anime_weekly_schedule",
                f"📝 通知記錄: anime_notified 表",
                f"⏱️ 排程機制: 智能睡眠直到下次排程時間 (最多30分鐘)",
                f"⏱️ 備案機制: 連續{max_failures}次失敗後切換到15分鐘輪詢",
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

            if not self.polling_core:
                await send_response("❌ 推送核心未完全初始化", ephemeral=True)
                return

            # 手動觸發增強版推送系統的檢查 (包含排程推送和輪詢備案)
            await send_response("🔄 正在手動檢查增強版推送系統...", ephemeral=True)
            await self.polling_core._check_and_push(ANIME_CHANNEL_ID)

            await send_response("✅ 手動檢查完成", ephemeral=True)
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker.anime_manual_check] 手動檢查失敗: {e}", exc_info=True)
            await send_response(f"❌ 手動檢查失敗: {str(e)}", ephemeral=True)


async def setup(bot):
    """設置 Cog 的入口點"""
    await bot.add_cog(AnimeTracker(bot))