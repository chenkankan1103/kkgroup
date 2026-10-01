"""
置物櫃事件監聽器

職責：收到置物櫃相關事件 → 呼叫 update_locker_message() 刷新該用戶的置物櫃訊息。

設計原則（單一真相）：
- 所有 embed 生成一律交給 cogs/ui/utils/locker_embed_generator.update_locker_message()，
  這裡不再自己組 embed。過去這裡有一套獨立的 embed 產生邏輯，會跟 canonical 版本打架，
  而且刷新時只送 embeds 不送 view，會把置物櫃的按鈕整排弄不見。
- 事件名稱必須與 dispatch() 的字串一致：dispatch("full_refresh", ...) → on_full_refresh。
  歷史上唯一的發送端用了 "locker_full_refresh"，名稱對不上，靜默失效、不會報錯。
- 發送端（locker_sync_loop）刻意放在這個 Cog 內：它只由 uibody.setup() 建立，
  保證 uibot 只有一份，不會三隻 bot 各發一次。
"""

import asyncio

import discord
from discord.ext import commands, tasks

from db_adapter import get_all_users, get_user_field
from cogs.ui.events import FullRefreshEvent
from cogs.ui.utils.locker_embed_generator import update_locker_message

# 掃描間隔（分鐘）
SYNC_INTERVAL_MINUTES = 10
# 每輪最多刷新幾個人，避免一次打爆 Discord API
MAX_UPDATES_PER_CYCLE = 15
# 每次刷新之間的間隔秒數（節流）
UPDATE_GAP_SECONDS = 1.5
# 用來判斷「有變化」的欄位
WATCHED_FIELDS = ("kkcoin", "hp")


class LockerEventListenerCog(commands.Cog):
    """置物櫃事件監聽 + 變更偵測"""

    def __init__(self, bot, user_panel_cog):
        self.bot = bot
        self.cog = user_panel_cog
        # {user_id: (kkcoin, hp)} 上一輪看到的快照
        self._last_seen = {}
        self.locker_sync_loop.start()

    def cog_unload(self):
        self.locker_sync_loop.cancel()

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------
    async def _refresh(self, user_id: int) -> bool:
        """刷新單一用戶的置物櫃訊息。所有事件都走這裡。"""
        thread_id = get_user_field(user_id, "thread_id")
        if not thread_id:
            return False

        try:
            thread = self.bot.get_channel(thread_id)
            if thread is None:
                thread = await self.bot.fetch_channel(thread_id)
        except Exception as e:
            print(f"⚠️ [LockerEvent] 取不到 thread {thread_id}: {e}")
            return False

        if not isinstance(thread, discord.Thread):
            return False

        # 已知 message_id 就直接抓，省掉 update_locker_message 內部掃 30 筆歷史
        message_obj = None
        message_id = get_user_field(user_id, "locker_message_id")
        if message_id:
            try:
                message_obj = await thread.fetch_message(message_id)
            except Exception:
                message_obj = None

        try:
            return await update_locker_message(
                thread=thread,
                user_id=user_id,
                message_obj=message_obj,
                bot=self.bot,
                cog=self.cog,
            )
        except Exception as e:
            print(f"❌ [LockerEvent] 刷新 user {user_id} 失敗: {e}")
            return False

    # ------------------------------------------------------------------
    # 事件監聽（名稱須與 dispatch 字串一致）
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_full_refresh(self, event: FullRefreshEvent):
        await self._refresh(event.user_id)

    @commands.Cog.listener()
    async def on_equipment_changed(self, event):
        await self._refresh(event.user_id)

    @commands.Cog.listener()
    async def on_currency_changed(self, event):
        await self._refresh(event.user_id)

    @commands.Cog.listener()
    async def on_health_changed(self, event):
        await self._refresh(event.user_id)

    @commands.Cog.listener()
    async def on_inventory_changed(self, event):
        await self._refresh(event.user_id)

    @commands.Cog.listener()
    async def on_sync_requested(self, event):
        await self._refresh(event.user_id)

    # ------------------------------------------------------------------
    # 發送端：定時比對 KK幣／血量，有變才發事件
    # ------------------------------------------------------------------
    @tasks.loop(minutes=SYNC_INTERVAL_MINUTES)
    async def locker_sync_loop(self):
        try:
            users = await asyncio.to_thread(get_all_users)
        except Exception as e:
            print(f"⚠️ [LockerSync] 讀取用戶失敗: {e}")
            return

        first_run = not self._last_seen
        current = {}
        changed = []

        for user in users:
            user_id = user.get("user_id")
            if not user_id or not user.get("thread_id"):
                continue
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                continue

            snapshot = tuple(user.get(f) for f in WATCHED_FIELDS)
            current[user_id] = snapshot
            if not first_run and self._last_seen.get(user_id) != snapshot:
                changed.append(user_id)

        # 首輪只建立基準，不觸發，避免開機時全員同時被刷新
        if first_run:
            self._last_seen = current
            print(f"📋 [LockerSync] 建立基準快照：{len(current)} 位用戶")
            return

        if not changed:
            return

        print(f"🔄 [LockerSync] 偵測到 {len(changed)} 位用戶有變化，開始刷新")

        for user_id in changed[:MAX_UPDATES_PER_CYCLE]:
            # 只有真的送出刷新才更新基準；被上限擋掉的人維持舊快照，下輪會再被抓到
            self._last_seen[user_id] = current[user_id]
            self.bot.dispatch("full_refresh", FullRefreshEvent(user_id, {"*"}))
            await asyncio.sleep(UPDATE_GAP_SECONDS)

        if len(changed) > MAX_UPDATES_PER_CYCLE:
            print(
                f"⏭️ [LockerSync] 本輪上限 {MAX_UPDATES_PER_CYCLE} 人，"
                f"剩 {len(changed) - MAX_UPDATES_PER_CYCLE} 人下輪處理"
            )

    @locker_sync_loop.before_loop
    async def _before_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    """由 uibody.setup() 直接建立本 Cog，不在此處 add_cog。"""
    pass
