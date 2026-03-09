import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# 用於更新用戶 KKcoin
from shop_commands.merchant.database import update_user_kkcoin, get_user_kkcoin

DATA_PATH = Path("data")
STORAGE_FILE = DATA_PATH / "red_envelopes.json"

# 可調整的行為參數
AWARD_AMOUNT = 2000
AWARD_RETRY_MAX = 3
PENDING_RETRY_INTERVAL = 30  # background worker 掃描間隔（秒）
AWARD_THREAD_TIMEOUT = 2.5   # to_thread 發放 timeout
AWARD_BALANCE_TIMEOUT = 1.5  # 讀取餘額 timeout
PERSISTENT_VIEW_WATCHDOG_INTERVAL = 300  # seconds between automatic persistent-view checks/repairs (5 minutes)


def _load_storage() -> Dict:
    if not STORAGE_FILE.exists():
        return {"messages": {}, "pending_awards": []}
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 向後相容：確保必要 keys 存在
            if "messages" not in data:
                data["messages"] = {}
            if "pending_awards" not in data:
                data["pending_awards"] = []
            return data
    except Exception:
        return {"messages": {}, "pending_awards": []}


def _save_storage(data: Dict):
    DATA_PATH.mkdir(exist_ok=True)
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 異步版本（避免阻塞事件循環）
async def _async_load_storage(timeout=3.0) -> Dict:
    """異步加載存儲（使用線程池避免阻塞）"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_load_storage),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning("[RED ENVELOPE] Timeout loading storage (>3s), returning empty")
        return {"messages": {}, "pending_awards": []}
    except Exception as e:
        logger.error(f"[RED ENVELOPE] Error loading storage: {e}")
        return {"messages": {}, "pending_awards": []}


async def _async_save_storage(data: Dict, timeout=2.0):
    """異步保存存儲（使用線程池避免阻塞）"""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_save_storage, data),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning("[RED ENVELOPE] Timeout saving storage (>2s)")
    except Exception as e:
        logger.error(f"[RED ENVELOPE] Error saving storage: {e}")


class RedEnvelopeView(discord.ui.View):
    """每個 message 對應一個 View（支援重啟後恢復）。

    - 使用 file（storage）記錄 claimed user ids，防止重複領取
    - 使用 asyncio.Lock 避免 race condition
    - Button 使用自訂 custom_id 以支援 bot 重啟後的 persistent view
    """

    def __init__(self, cog, activity_id: str, message_id: Optional[int], expiry_ts: float, claimed: Optional[List[int]] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.activity_id = activity_id
        self.message_id = message_id
        self.expiry_ts = expiry_ts
        self.claimed: List[int] = claimed or []
        self.lock = asyncio.Lock()

        # 使用 runtime button（可在啟動時用相同 custom_id 重建）
        btn = discord.ui.Button(label="領取紅包", style=discord.ButtonStyle.success, custom_id=f"red_envelope:{self.activity_id}")
        btn.callback = self._on_claim
        self.add_item(btn)

    async def _on_claim(self, interaction: discord.Interaction):
        """Handle button click. This wrapper ensures we always respond to the interaction
        and logs unexpected errors so production failures can be diagnosed.
        """
        start_ts = time.time()
        user_id = getattr(interaction.user, "id", None)
        logger.info("red_envelope: claim attempt user=%s message=%s activity=%s", user_id, self.message_id, self.activity_id)

        # Always try to defer first — if that fails, log and try to inform the user.
        try:
            await interaction.response.defer(ephemeral=True)
            # record defer timing to detect Discord 3s ack issues
            defer_elapsed = time.time() - start_ts
            logger.info("red_envelope: defer done user=%s message=%s defer_elapsed=%.3fs", user_id, self.message_id, defer_elapsed)
        except Exception:
            logger.exception("Failed to defer interaction (red_envelope) user=%s message=%s", user_id, self.message_id)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("⚠️ 伺服器忙碌，請稍後再試。", ephemeral=True)
                else:
                    await interaction.followup.send("⚠️ 伺服器忙碌，請稍後再試。", ephemeral=True)
            except Exception:
                logger.exception("Failed to notify user after defer failure user=%s message=%s", user_id, self.message_id)
            return

        try:
            now = time.time()
            if now >= self.expiry_ts:
                # 已過期：停用按鈕並回覆
                await self._expire_message()
                await interaction.followup.send("⚠️ 活動已結束，無法領取。", ephemeral=True)
                return

            async with self.lock:
                if user_id in self.claimed:
                    await interaction.followup.send("❌ 你已經領過一次紅包了（每人限領一次）。", ephemeral=True)
                    return

                # 記錄領取者（儘早寫入記憶以避免 race）
                self.claimed.append(user_id)

                # 嘗試發放 2000 KK 幣（帶重試），若短期失敗會加入 pending_awards 由 background worker 重試
                new_balance = None
                try:
                    new_balance = await self.cog._award_user_with_retries(user_id, amount=AWARD_AMOUNT)
                except Exception:
                    logger.exception("award_user_with_retries failed for user=%s message=%s", user_id, self.message_id)
                    new_balance = None

                if new_balance is None:
                    # 加入待處理清單，background worker 會自動重試
                    try:
                        await self.cog._add_pending_award(user_id, self.message_id, AWARD_AMOUNT)
                    except Exception:
                        logger.exception("_add_pending_award failed for user=%s message=%s", user_id, self.message_id)

                # 更新 storage
                try:
                    # ⏱️ 使用異步版本避免阻塞
                    storage = await _async_load_storage()
                    msg_key = str(self.message_id) if self.message_id else None
                    if msg_key and msg_key in storage.get("messages", {}):
                        storage["messages"][msg_key]["claimed"] = self.claimed
                        await _async_save_storage(storage)
                except Exception:
                    logger.exception("Failed to persist claimed list user=%s message=%s", user_id, self.message_id)

                # 更新 embed 顯示領取名單（同時顯示已發放獎勵）
                try:
                    message = interaction.message
                    embed = discord.Embed(
                        title="🧧 新年紅包",
                        description="點擊下方按鈕領取（每人只能領一次）。活動結束後此功能會自動停用並刪除相關資料與程式碼。",
                        color=0xE74C3C,
                    )
                    claimed_mentions = "\n".join(f"<@{uid}>" for uid in self.claimed)
                    embed.add_field(name="已領取", value=claimed_mentions or "尚未有人領取", inline=False)
                    if new_balance is not None:
                        embed.add_field(name="最近領取獎勵", value=f"<@{user_id}> 獲得 +2000 KKcoin（現有 {new_balance} KKcoin）", inline=False)
                    embed.set_footer(text=f"活動到期時間：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.expiry_ts))}")

                    await message.edit(embed=embed, view=self)
                except Exception:
                    logger.exception("Failed to edit red envelope message after claim user=%s message=%s", user_id, self.message_id)

                # 回覆使用者（一定會有一個 followup）
                try:
                    if new_balance is not None:
                        await interaction.followup.send(f"✅ 你已成功領取紅包並獲得 **{AWARD_AMOUNT} KKcoin**，目前餘額：{new_balance} KKcoin。", ephemeral=True)
                    else:
                        await interaction.followup.send("✅ 你已成功領取紅包（獎勵已加入重試佇列，稍後會自動發放）。", ephemeral=True)
                except Exception:
                    logger.exception("Failed to send followup after claim user=%s message=%s", user_id, self.message_id)

        except Exception:
            # 捕捉所有未預期的錯誤，並保證使用者看得到錯誤訊息而不是 'This interaction failed'
            logger.exception("Unhandled exception in RedEnvelopeView._on_claim user=%s message=%s", user_id, self.message_id)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 發生內部錯誤，請稍後重試。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 發生內部錯誤，請稍後重試。", ephemeral=True)
            except Exception:
                logger.exception("Also failed to notify user after an exception user=%s message=%s", user_id, self.message_id)
        finally:
            elapsed = time.time() - start_ts
            logger.info("red_envelope: claim finished user=%s message=%s elapsed=%.3fs", user_id, self.message_id, elapsed)
    async def _expire_message(self):
        # 停用按鈕（edit message）並從 storage 刪除
        try:
            if not self.message_id:
                return
            # ⏱️ 使用異步版本避免阻塞
            storage = await _async_load_storage()
            msg_key = str(self.message_id)

            # 先從 storage 取出 channel_id（避免刪除後無法查到 channel）
            channel_id = None
            entry = storage.get("messages", {}).get(msg_key)
            if entry:
                channel_id = entry.get("channel_id")

            # 刪除該活動資料（先備份 channel_id）
            if msg_key in storage.get("messages", {}):
                del storage["messages"][msg_key]
                await _async_save_storage(storage)

            # 直接使用 channel_id 去抓取訊息（不要再依賴已刪除的 storage）
            channel = None
            try:
                if channel_id:
                    channel = self.cog.bot.get_channel(channel_id) if hasattr(self.cog.bot, 'get_channel') else await self.cog._fetch_channel_for_message(self.message_id)
                else:
                    channel = await self.cog._fetch_channel_for_message(self.message_id)
            except Exception:
                channel = None

            if channel:
                try:
                    message = await channel.fetch_message(self.message_id)
                    # 將按鈕停用（將 view 裡的所有按鈕設為 disabled）
                    for item in self.children:
                        if hasattr(item, "disabled"):
                            item.disabled = True
                    # 更新 embed footer 說明活動已結束
                    embed = message.embeds[0] if message.embeds else discord.Embed(title="🧧 新年紅包")
                    embed.set_footer(text="活動已結束（按鈕已停用），相關臨時資料已移除。")
                    await message.edit(embed=embed, view=self)
                except discord.NotFound:
                    # message 被刪除，nothing to do
                    pass
        except Exception:
            pass


class NewYearRedEnvelope(commands.Cog):
    """臨時新年紅包活動：

    - /發紅包 (管理員) → 發送一則 embed + 領取按鈕
    - 每人只能領一次（以 user id 檢查 + 儲存在 data/red_envelopes.json）
    - 到期後（預設 24 小時）自動停用並刪除該活動的儲存資料
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 在啟動時恢復尚未到期的活動
        self._startup_task = bot.loop.create_task(self._restore_active_envelopes())
        # 啟動 background worker，處理 pending_awards 重試
        self._pending_worker_task = bot.loop.create_task(self._pending_awards_worker())
        # 啟動 watchdog：定期檢查並自動修復失效的 persistent views
        self._watchdog_task = bot.loop.create_task(self._persistent_view_watchdog())

    async def _fetch_channel_for_message(self, message_id: int) -> Optional[discord.abc.GuildChannel]:
        storage = _load_storage()
        entry = storage.get("messages", {}).get(str(message_id))
        if not entry:
            return None
        channel_id = entry.get("channel_id")
        return self.bot.get_channel(channel_id)

    async def _restore_active_envelopes(self):
        await self.bot.wait_until_ready()
        storage = _load_storage()
        now = time.time()
        for msg_id_str, info in list(storage.get("messages", {}).items()):
            try:
                expiry = info.get("expiry", 0)
                message_id = int(msg_id_str)
                activity_id = info.get("activity_id")
                claimed = info.get("claimed", [])
                if expiry <= now:
                    # 已過期，刪除存檔
                    del storage["messages"][msg_id_str]
                    _save_storage(storage)
                    continue

                # 嘗試將 view 加回 bot（支援重啟後的互動處理）
                view = RedEnvelopeView(self, activity_id=activity_id, message_id=message_id, expiry_ts=expiry, claimed=claimed)
                # 使用 message_id 讓 discord.py 將互動導回這個 view
                try:
                    # register message-specific + global view on restore
                    self.bot.add_view(view, message_id=message_id)
                    try:
                        self.bot.add_view(view)
                    except Exception:
                        pass
                    logger.info("Restored red envelope view message=%s expiry=%s", message_id, expiry)
                except Exception:
                    logger.exception("Failed to add_view for red envelope message=%s", message_id)

                # 同步在到期時間執行清理
                self.bot.loop.create_task(self._schedule_expiry(message_id, expiry))
            except Exception:
                continue

    async def _schedule_expiry(self, message_id: int, expiry_ts: float):
        now = time.time()
        wait = max(0, expiry_ts - now)
        await asyncio.sleep(wait)
        storage = _load_storage()
        entry = storage.get("messages", {}).get(str(message_id))
        if not entry:
            return
        # 嘗試停用 message 上的按鈕並刪除資料
        activity_id = entry.get("activity_id")
        view = RedEnvelopeView(self, activity_id=activity_id, message_id=message_id, expiry_ts=expiry_ts, claimed=entry.get("claimed", []))
        await view._expire_message()

        # 如果沒有剩下的活動資料，則刪除該臨時模組檔案（移除整個邏輯）
        try:
            storage = _load_storage()
            if not storage.get("messages"):
                module_path = Path(__file__).resolve()
                if module_path.exists():
                    try:
                        os.remove(module_path)
                    except Exception:
                        pass

                # 嘗試移除對應的 __pycache__ 檔案（視情況而定）
                try:
                    pycache_dir = module_path.parent / "__pycache__"
                    if pycache_dir.exists():
                        for p in pycache_dir.glob("new_year_red_envelope*.pyc"):
                            try:
                                p.unlink()
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    # ---------------------------
    # Pending-award (retry) 機制
    # ---------------------------
    async def _award_user_with_retries(self, user_id: int, amount: int = AWARD_AMOUNT) -> Optional[int]:
        """同步地使用執行緒嘗試給予金幣，內部帶重試與 backoff。回傳新餘額或 None。"""
        try:
            from db_adapter import add_user_field, get_user_field
        except Exception:
            return None

        for attempt in range(AWARD_RETRY_MAX):
            try:
                await asyncio.wait_for(asyncio.to_thread(add_user_field, user_id, 'kkcoin', amount), timeout=AWARD_THREAD_TIMEOUT)
                new_balance = await asyncio.wait_for(asyncio.to_thread(get_user_field, user_id, 'kkcoin', 0), timeout=AWARD_BALANCE_TIMEOUT)
                return new_balance
            except Exception:
                # 指數退避
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue

        return None

    async def _add_pending_award(self, user_id: int, message_id: int, amount: int = AWARD_AMOUNT):
        """將未成功的發放加入 storage.pending_awards（避免重複）。"""
        storage = await _async_load_storage()
        storage.setdefault("pending_awards", [])
        # 避免重複加入
        for p in storage["pending_awards"]:
            if p.get("user_id") == user_id and p.get("message_id") == message_id and p.get("amount") == amount:
                return

        storage["pending_awards"].append({
            "user_id": user_id,
            "message_id": message_id,
            "amount": amount,
            "attempts": 0,
            "created_at": time.time(),
            "last_try": None,
            "next_try": time.time() + PENDING_RETRY_INTERVAL,
        })
        await _async_save_storage(storage)

    async def _pending_awards_worker(self):
        """背景工作：定期掃描 pending_awards 並重試發放。"""
        await self.bot.wait_until_ready()
        while True:
            try:
                # ⏱️ 使用異步版本以避免阻塞事件循環
                storage = await _async_load_storage()
                pending = list(storage.get("pending_awards", []))
                now = time.time()
                changed = False
                for item in pending:
                    if item.get("next_try", 0) > now:
                        continue

                    user_id = item["user_id"]
                    message_id = item["message_id"]
                    amount = item.get("amount", AWARD_AMOUNT)
                    attempts = item.get("attempts", 0)

                    new_balance = await self._award_user_with_retries(user_id, amount=amount)
                    if new_balance is not None:
                        # 移除 pending 並更新 embed（若 message 仍存在）
                        storage = await _async_load_storage()
                        storage["pending_awards"] = [p for p in storage.get("pending_awards", []) if not (p.get("user_id")==user_id and p.get("message_id")==message_id and p.get("amount")==amount)]
                        await _async_save_storage(storage)
                        changed = True

                        # 更新訊息 embed（顯示已發放）
                        try:
                            channel = await self._fetch_channel_for_message(message_id)
                            if channel:
                                msg = await channel.fetch_message(message_id)
                                embed = discord.Embed(
                                    title="🧧 新年紅包",
                                    description="點擊下方按鈕領取（每人只能領一次）。活動結束後此功能會自動停用並刪除相關資料與程式碼。",
                                    color=0xE74C3C,
                                )
                                # 讀取最新 claimed list
                                storage_after = await _async_load_storage()
                                claimed = storage_after.get("messages", {}).get(str(message_id), {}).get("claimed", [])
                                embed.add_field(name="已領取", value="\n".join(f"<@{uid}>" for uid in claimed) or "尚未有人領取", inline=False)
                                embed.add_field(name="最近領取獎勵", value=f"<@{user_id}> 獲得 +{amount} KKcoin（現有 {new_balance} KKcoin）", inline=False)
                                embed.set_footer(text=f"活動到期時間：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(storage_after.get('messages', {}).get(str(message_id), {}).get('expiry', 0)))}")
                                await msg.edit(embed=embed)
                        except Exception:
                            pass
                    else:
                        # 更新 attempts/next_try
                        storage = await _async_load_storage()
                        for p in storage.get("pending_awards", []):
                            if p.get("user_id") == user_id and p.get("message_id") == message_id and p.get("amount") == amount:
                                p["attempts"] = p.get("attempts", 0) + 1
                                p["last_try"] = time.time()
                                backoff = min(300, PENDING_RETRY_INTERVAL * (2 ** p["attempts"]))
                                p["next_try"] = time.time() + backoff
                                break
                        await _async_save_storage(storage)
                        changed = True

                # 休息一段時間再繼續掃描
                await asyncio.sleep(PENDING_RETRY_INTERVAL)
            except Exception:
                await asyncio.sleep(PENDING_RETRY_INTERVAL)
                continue

    async def _repair_message(self, message_id: int, info: Dict) -> str:
        """Attempt to repair a single stored message:
        - re-register view if button exists but bot lost registration
        - re-add components (edit message) and register view if button missing
        - increment missing_count and remove storage after repeated failures
        Returns a short status string for logging.
        """
        now = time.time()
        expiry = info.get("expiry", 0)
        if expiry <= now:
            return "expired"

        channel = await self._fetch_channel_for_message(message_id)
        if not channel:
            info["missing_count"] = info.get("missing_count", 0) + 1
            return "channel-missing"

        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            info["missing_count"] = info.get("missing_count", 0) + 1
            return "message-not-found"
        except Exception:
            logger.exception("red_envelope: failed to fetch message=%s during repair", message_id)
            return "fetch-error"

        # check whether the interactive button component is present
        button_present = False
        for comp in getattr(msg, "components", []):
            for child in getattr(comp, "children", []):
                cid = getattr(child, "custom_id", None)
                if cid and cid.startswith("red_envelope:"):
                    button_present = True
                    break
            if button_present:
                break

        activity_id = info.get("activity_id")
        claimed = info.get("claimed", [])
        expiry_ts = info.get("expiry", 0)

        if button_present:
            # ensure our bot has the view registered so interactions route correctly
            try:
                view = RedEnvelopeView(self, activity_id=activity_id, message_id=message_id, expiry_ts=expiry_ts, claimed=claimed)
                self.bot.add_view(view, message_id=message_id)
                info.pop("missing_count", None)
                return "re-registered"
            except Exception:
                logger.exception("red_envelope: failed to add_view for message=%s", message_id)
                return "add-view-failed"

        # button not present -> try to repair message components and re-register
        try:
            view = RedEnvelopeView(self, activity_id=activity_id, message_id=message_id, expiry_ts=expiry_ts, claimed=claimed)
            embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🧧 新年紅包")
            await msg.edit(embed=embed, view=view)
            self.bot.add_view(view, message_id=message_id)
            info.pop("missing_count", None)
            return "repaired-components"
        except Exception:
            logger.exception("red_envelope: failed to repair components for message=%s", message_id)
            info["missing_count"] = info.get("missing_count", 0) + 1
            return "repair-failed"

    async def _persistent_view_watchdog(self):
        """Background watchdog that periodically checks stored messages and attempts
        automated repairs for missing/expired/mis-registered persistent views.
        """
        await self.bot.wait_until_ready()
        interval = PERSISTENT_VIEW_WATCHDOG_INTERVAL
        while True:
            try:
                storage = _load_storage()
                now = time.time()
                for mid_str, info in list(storage.get("messages", {}).items()):
                    try:
                        message_id = int(mid_str)
                        status = await self._repair_message(message_id, info)
                        if status in ("re-registered", "repaired-components"):
                            logger.info("red_envelope.watchdog: repaired message=%s status=%s", message_id, status)
                            _save_storage(storage)
                        elif status in ("message-not-found", "channel-missing"):
                            logger.warning("red_envelope.watchdog: message=%s status=%s missing_count=%s", message_id, status, info.get("missing_count"))
                            # if missing repeatedly, remove storage entry
                            if info.get("missing_count", 0) >= 3:
                                logger.info("red_envelope.watchdog: removing message=%s after repeated missing", message_id)
                                del storage[ mid_str ]
                                _save_storage(storage)
                        elif status == "expired":
                            # schedule expiry cleanup immediately
                            try:
                                view = RedEnvelopeView(self, activity_id=info.get("activity_id"), message_id=message_id, expiry_ts=info.get("expiry", 0), claimed=info.get("claimed", []))
                                await view._expire_message()
                            except Exception:
                                pass
                            # remove storage entry
                            if mid_str in storage.get("messages", {}):
                                del storage[ mid_str ]
                                _save_storage(storage)
                    except Exception:
                        logger.exception("red_envelope.watchdog: failure while checking message %s", mid_str)
                    await asyncio.sleep(0.12)
            except Exception:
                logger.exception("red_envelope.watchdog: unexpected error in loop")
            await asyncio.sleep(interval)

    @app_commands.command(name="發紅包", description="(管理員) 發送臨時新年紅包 — 每人限領一次，明天自動停用")
    async def send_red_envelope(self, interaction: discord.Interaction, hours: Optional[int] = 24):
        # 只有管理員可以發
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 你沒有權限使用這個指令。", ephemeral=True)
            return

        if hours <= 0 or hours > 72:
            await interaction.response.send_message("⚠️ hours 必須介於 1 到 72 小時之間。", ephemeral=True)
            return

        await interaction.response.defer()

        expiry_ts = time.time() + (hours * 3600)
        activity_id = uuid.uuid4().hex[:12]

        embed = discord.Embed(
            title="🧧 新年紅包",
            description="點擊下方按鈕領取你的新年紅包（每人只能領一次）。活動會在到期時自動停用並刪除領取資料。",
            color=0xE74C3C,
        )
        embed.add_field(name="已領取", value="尚未有人領取", inline=False)
        embed.set_footer(text=f"活動到期時間：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry_ts))}")

        view = RedEnvelopeView(self, activity_id=activity_id, message_id=None, expiry_ts=expiry_ts, claimed=[])
        channel = interaction.channel
        message = await channel.send(embed=embed, view=view)

        # 記錄 message_id 並存檔
        view.message_id = message.id
        storage = _load_storage()
        storage.setdefault("messages", {})[str(message.id)] = {
            "guild_id": interaction.guild.id if interaction.guild else None,
            "channel_id": channel.id,
            "message_id": message.id,
            "activity_id": activity_id,
            "expiry": expiry_ts,
            "claimed": [],
        }
        _save_storage(storage)

        # 註冊 persistent view（在重啟後仍能接受互動）
        try:
            # register both message-specific and global view to reduce risk of transient mapping loss
            self.bot.add_view(view, message_id=message.id)
            try:
                self.bot.add_view(view)
            except Exception:
                # registering global view may be optional depending on library state
                pass
            logger.info("Registered new red envelope view message=%s activity=%s expiry=%s", message.id, activity_id, expiry_ts)
        except Exception:
            logger.exception("Failed to register view for red envelope message=%s", message.id)

        # 確認已寫入 storage
        logger.info("Saved red envelope to storage message=%s activity=%s expiry=%s", message.id, activity_id, expiry_ts)

        # 安排到期清理
        self.bot.loop.create_task(self._schedule_expiry(message.id, expiry_ts))

        await interaction.followup.send(f"✅ 已在本頻道發送新年紅包（活動 {hours} 小時）。", ephemeral=True)

    @app_commands.command(name="紅包修復", description="(管理員) 立即檢查並修復所有紅包 persistent view")
    async def red_envelope_repair(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 你沒有權限使用這個指令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        storage = _load_storage()
        msgs = storage.get("messages", {})
        if not msgs:
            await interaction.followup.send("目前沒有正在進行的紅包活動。", ephemeral=True)
            return

        lines = []
        for mid_str, info in list(msgs.items()):
            try:
                mid = int(mid_str)
            except Exception:
                continue
            status = await self._repair_message(mid, info)
            lines.append(f"message={mid} status={status} missing_count={info.get('missing_count',0)}")

        _save_storage(storage)
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    @app_commands.command(name="紅包狀態", description="(管理員) 檢查目前新年紅包活動狀態（檢查 storage + message components）")
    async def red_envelope_status(self, interaction: discord.Interaction):
        """管理員專用：檢查 data/red_envelopes.json 中的活動、嘗試抓取訊息並檢查按鈕 custom_id 是否仍存在。"""
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 你沒有權限使用這個指令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        storage = _load_storage()
        msgs = storage.get("messages", {})
        if not msgs:
            await interaction.followup.send("目前沒有正在進行的紅包活動。", ephemeral=True)
            return

        lines = []
        for mid_str, info in msgs.items():
            try:
                mid = int(mid_str)
            except Exception:
                continue
            ch_id = info.get("channel_id")
            expiry = info.get("expiry", 0)
            claimed = info.get("claimed", [])

            fetchable = False
            button_present = False
            try:
                channel = self.bot.get_channel(ch_id) or await self._fetch_channel_for_message(mid)
                if channel:
                    msg = await channel.fetch_message(mid)
                    fetchable = True
                    # inspect components for our custom_id prefix
                    for comp in msg.components:
                        for child in getattr(comp, "children", []):
                            cid = getattr(child, "custom_id", "")
                            if cid and cid.startswith("red_envelope:"):
                                button_present = True
                                break
                        if button_present:
                            break
            except Exception:
                pass

            lines.append(f"- message={mid} channel={ch_id} expiry={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))} claimed={len(claimed)} fetchable={fetchable} button={button_present}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="紅包掃描", description="(管理員) 掃描頻道/訊息並回復遺失的紅包 persistent view（會註冊 View 並將訊息加入 storage）")
    async def red_envelope_scan(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, message_id: Optional[int] = None, limit: Optional[int] = 200):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 你沒有權限使用這個指令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        target_channel = channel or interaction.channel
        results = []

        if message_id:
            status = await self._rescue_message(target_channel, message_id)
            results.append(f"message={message_id} status={status}")
        else:
            try:
                async for msg in target_channel.history(limit=limit):
                    # quick check for component
                    has_red = False
                    for comp in getattr(msg, 'components', []):
                        for child in getattr(comp, 'children', []):
                            cid = getattr(child, 'custom_id', None)
                            if cid and cid.startswith('red_envelope:'):
                                has_red = True
                                break
                        if has_red:
                            break
                    if not has_red:
                        continue

                    status = await self._rescue_message(target_channel, msg.id)
                    results.append(f"message={msg.id} status={status}")
            except Exception:
                logger.exception("red_envelope.scan: failed to iterate channel history %s", getattr(target_channel, 'id', None))

        if not results:
            await interaction.followup.send("未找到任何可回復的紅包訊息。", ephemeral=True)
            return

        await interaction.followup.send("\n".join(results), ephemeral=True)

    async def _parse_claimed_from_embed(self, embed: discord.Embed) -> List[int]:
        """Extract user ids from the embed field named '已領取' (format: <@id> lines)."""
        if not embed:
            return []
        for f in embed.fields:
            if f.name == "已領取":
                text = f.value or ""
                ids = []
                for part in text.split():
                    if part.startswith("<@") and part.endswith(">"):
                        try:
                            uid = int(part.strip("<@!>"))
                            ids.append(uid)
                        except Exception:
                            continue
                return ids
        return []

    def _parse_expiry_from_footer(self, footer_text: str) -> Optional[float]:
        """Parse footer like '活動到期時間：YYYY-MM-DD HH:MM:SS' to a timestamp. Return None on failure."""
        if not footer_text:
            return None
        try:
            if "活動到期時間：" in footer_text:
                ts_part = footer_text.split("活動到期時間：", 1)[1].strip()
                # try common format
                t_struct = time.strptime(ts_part, "%Y-%m-%d %H:%M:%S")
                return time.mktime(t_struct)
        except Exception:
            return None
        return None

    async def _rescue_message(self, channel: discord.abc.Messageable, message_id: int) -> str:
        """Attempt to rescue a Discord message that contains a red_envelope component but
        is not present in storage. Returns a status string for logging/reporting.
        """
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return "fetch-failed"

        # find red envelope button
        found_cid = None
        for comp in getattr(msg, "components", []):
            for child in getattr(comp, "children", []):
                cid = getattr(child, "custom_id", None)
                if cid and cid.startswith("red_envelope:"):
                    found_cid = cid
                    break
            if found_cid:
                break

        if not found_cid:
            return "no-red-envelope-component"

        activity_id = found_cid.split(":", 1)[1]

        # check storage whether message already recorded
        storage = _load_storage()
        if str(message_id) in storage.get("messages", {}):
            # ensure view registered
            try:
                info = storage[ str(message_id) ]
                view = RedEnvelopeView(self, activity_id=info.get("activity_id"), message_id=message_id, expiry_ts=info.get("expiry", 0), claimed=info.get("claimed", []))
                self.bot.add_view(view, message_id=message_id)
                try:
                    self.bot.add_view(view)
                except Exception:
                    pass
                return "already-in-storage-registered-view"
            except Exception:
                return "already-in-storage-failed-register"

        # reconstruct claimed and expiry from embed
        embed = msg.embeds[0] if msg.embeds else None
        claimed = await self._parse_claimed_from_embed(embed)
        expiry_ts = None
        if embed and embed.footer and getattr(embed.footer, 'text', None):
            expiry_ts = self._parse_expiry_from_footer(embed.footer.text)
        if not expiry_ts:
            expiry_ts = time.time() + 24 * 3600

        # save to storage
        storage.setdefault("messages", {})[str(message_id)] = {
            "guild_id": getattr(msg.guild, 'id', None) if hasattr(msg, 'guild') else None,
            "channel_id": getattr(msg.channel, 'id', None),
            "message_id": message_id,
            "activity_id": activity_id,
            "expiry": expiry_ts,
            "claimed": claimed,
        }
        _save_storage(storage)

        # register view
        try:
            view = RedEnvelopeView(self, activity_id=activity_id, message_id=message_id, expiry_ts=expiry_ts, claimed=claimed)
            self.bot.add_view(view, message_id=message_id)
            try:
                self.bot.add_view(view)
            except Exception:
                pass
            return "rescued-and-registered"
        except Exception:
            logger.exception("red_envelope: failed to register view during rescue message=%s", message_id)
            return "rescued-but-register-failed"

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Fallback handler: if a component interaction arrives whose custom_id
        starts with `red_envelope:` but the library didn't dispatch to our View,
        catch it here and route to the same claim logic (resilient against
        transient view-registration loss).
        """
        try:
            data = getattr(interaction, 'data', {}) or {}
            cid = data.get('custom_id') if isinstance(data, dict) else None
            if not cid or not isinstance(cid, str) or not cid.startswith('red_envelope:'):
                return

            # if already handled by discord.py view, do nothing
            try:
                if interaction.response.is_done():
                    return
            except Exception:
                pass

            activity_id = cid.split(':', 1)[1]
            storage = _load_storage()
            # find message by activity_id
            for mid_str, info in storage.get('messages', {}).items():
                if info.get('activity_id') == activity_id:
                    message_id = int(mid_str)
                    view = RedEnvelopeView(self, activity_id=activity_id, message_id=message_id, expiry_ts=info.get('expiry', 0), claimed=info.get('claimed', []))
                    logger.info('red_envelope.fallback: handling interaction activity=%s message=%s', activity_id, message_id)
                    await view._on_claim(interaction)
                    return

            # not found in storage — attempt to rescue from the message itself (auto-recover)
            rescued = False
            try:
                # if interaction.message available, try to rebuild storage + register view
                msg = getattr(interaction, 'message', None)
                if msg:
                    try:
                        status = await self._rescue_message(msg.channel, msg.id)
                        logger.info('red_envelope.fallback: rescue attempt for message=%s status=%s', getattr(msg, 'id', None), status)
                        if status in ('rescued-and-registered', 'already-in-storage-registered-view'):
                            # now dispatch to claim handler
                            view = RedEnvelopeView(self, activity_id=activity_id, message_id=msg.id, expiry_ts=_load_storage().get('messages', {}).get(str(msg.id), {}).get('expiry', time.time()), claimed=_load_storage().get('messages', {}).get(str(msg.id), {}).get('claimed', []))
                            await view._on_claim(interaction)
                            rescued = True
                    except Exception:
                        logger.exception('red_envelope.fallback: rescue inner failure for message=%s', getattr(msg, 'id', None))

                if not rescued:
                    if not interaction.response.is_done():
                        await interaction.response.send_message('⚠️ 此活動已失效或找不到。', ephemeral=True)
                    else:
                        await interaction.followup.send('⚠️ 此活動已失效或找不到。', ephemeral=True)
            except Exception:
                logger.exception('red_envelope.fallback: failed to inform user activity=%s', activity_id)
        except Exception:
            logger.exception('red_envelope.fallback: unexpected error')


async def setup(bot: commands.Bot):
    await bot.add_cog(NewYearRedEnvelope(bot))
