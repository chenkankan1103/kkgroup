# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 簡化版 15分鐘輪詢

核心邏輯：每 15 分鐘輪詢 API → 比對已通知 → 推送新動畫
使用獨立資料庫：anime_push.db
移除所有複雜週表/排程器/統計系統
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio
import discord
from discord.ext import commands
from typing import Optional

from .push_core_simple import (
    SimpleAnimePushCore,
    AnimePushDB,
    ANIME_PUSH_DB_PATH,
    ANIME_CHANNEL_ID,
    TW_TZ,
)

logger = logging.getLogger(__name__)


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤 Cog - 簡化版 15分鐘輪詢"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.push_core = None
        self.db = None
        self._polling_task = None
        self._running = False

    async def set_dependencies(self, db_path: str = None):
        """設置依賴元件 - 簡化版：只初始化推送核心並啟動輪詢"""
        if self._running:
            logger.info("[AnimeTracker.set_dependencies] 已運行中，跳過")
            return

        db_path = db_path or str(ANIME_PUSH_DB_PATH)
        logger.info(f"🔧 [AnimeTracker.set_dependencies] 初始化簡化推送系統: {db_path}")

        # 初始化資料庫和推送核心
        self.db = AnimePushDB(db_path)
        self.push_core = SimpleAnimePushCore(self.db)
        self.push_core.set_bot(self.bot)

        # 啟動 15 分鐘輪詢
        await self.push_core.start_polling(ANIME_CHANNEL_ID)

        self._running = True
        msg = "✅ [AnimeTracker.set_dependencies] 簡化推送系統啟動完成 (15分鐘輪詢)"
        logger.info(msg)

    async def cog_load(self):
        """Cog 載入時執行的初始化"""
        self.logger.info("📺 [AnimeTracker.cog_load] 開始載入 Cog")

        # 如果依賴尚未設置，則自行初始化
        if not self._running:
            self.logger.info("🔧 [AnimeTracker.cog_load] 依賴尚未設置，嘗試自行初始化...")
            try:
                from .push_core_simple import ANIME_PUSH_DB_PATH
                await self.set_dependencies(str(ANIME_PUSH_DB_PATH))
                self.logger.info("✅ [AnimeTracker.cog_load] 依賴自行初始化成功")
            except Exception as e:
                self.logger.error(f"❌ [AnimeTracker.cog_load] 依賴自行初始化失敗: {e}", exc_info=True)
        else:
            self.logger.info("🚀 [AnimeTracker.cog_load] AnimeTracker Cog 載入完成（依賴已就緒）")

    async def cog_unload(self):
        """Cog 卸載時清理"""
        self.logger.info("🛑 [AnimeTracker.cog_unload] 正在停止輪詢...")
        if self.push_core:
            await self.push_core.stop_polling()
        self._running = False
        self.logger.info("🛑 [AnimeTracker.cog_unload] 輪詢已停止")

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
                "📊 **動畫推送系統狀態 (簡化版 15分鐘輪詢)**",
                f"🔄 輪詢狀態: {'✅ 運行中' if self._running else '❌ 已停止'}",
                f"📊 資料庫: anime_push.db",
                f"📋 推送記錄: 由 anime_notified 表管理",
                f"⏱️ 輪詢間隔: 15 分鐘 (900 秒)",
            ]

            if self.push_core:
                notified_count = len(self.push_core.db.get_notified_video_sns())
                status_lines.append(f"📝 已通知動畫數: {notified_count}")

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

            if not self.push_core:
                await send_response("❌ 推送核心未初始化", ephemeral=True)
                return

            # 手動觸發一次檢查
            await self.push_core._check_and_push(ANIME_CHANNEL_ID)

            await send_response("✅ 手動檢查已完成", ephemeral=True)
        except Exception as e:
            self.logger.error(f"❌ [AnimeTracker.anime_manual_check] 手動檢查失敗: {e}", exc_info=True)
            await send_response(f"❌ 手動檢查失敗: {str(e)}", ephemeral=True)


async def setup(bot):
    """設置 Cog 的入口點"""
    await bot.add_cog(AnimeTracker(bot))