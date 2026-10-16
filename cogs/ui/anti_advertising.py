"""
防廣告系統 Cog - 預防不當廣告和邀請連結
監聽消息，檢測廣告內容，並採取相應措施（刪除、禁言、踢出）
"""

import discord
from discord.ext import commands, tasks
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dotenv import load_dotenv

from shared.utils.encoding_handler import setup_utf8_logging

load_dotenv()

# 這支必須自帶 handler：uibot 是用 client.start() 而非 client.run()，discord.py 的
# setup_logging 根本不會被呼叫，root logger 一個 handler 都沒有，訊息會掉進
# lastResort 的 WARNING 被吞掉；連 logging.getLogger(__name__).setLevel(INFO)
# 也救不回來（2026-10-11 recovery_cog 已踩過同一個坑）。
# 偵測與懲罰紀錄原本是 print，改成 logger 之後若沒有 handler 會整批消失，
# 所以直接沿用 setup_utf8_logging，順便拿到 UTF-8 安全輸出與台灣時間格式。
logger = setup_utf8_logging(__name__, logging.INFO)

# ==================== 配置 ====================
# 管理／版主身分組沿用 .env 既有的 ADMIN_ROLE_ID；未設定時為 0，代表停用該判斷
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))

# 廣告內容模式（正則表達式）
# 只保留英文關鍵詞與 Discord 連結：中文的「商店／購物／賣場」在台灣日常對話太常見，
# 誤判成本高於攔截收益，故移除；英文詞則確實有機器人在洗，且台灣日常少用。
ADVERTISING_PATTERNS = {
    # Discord 邀請連結
    "discord_invite": r"(?:https?://)?discord\.gg/\w+",
    # 站內「複製訊息連結」長成 discord.com/channels/...，社群日常很常用，
    # 用 (?!channels) 排除，只擋其他 discord 網域連結（例如 /invite/xxx）
    "discord_base": r"(?:https?://)?discord\.(?:com|gg|app)/(?!channels)",
    # 其他遊戲/社群邀請
    "invite_links": r"\b(?:join|invite|server)[\w./-]*",
    # 社群媒體推廣（YT 不列：社群偶爾會貼 YouTube 網址，擋掉會誤傷）
    "twitch": r"(?:https?://)?(?:www\.)?twitch\.tv/\w+",
    "tiktok": r"(?:https?://)?(?:www\.)?tiktok\.com/@\w+",
    "ig": r"(?:https?://)?(?:www\.)?instagram\.com/\w+",
    "telegram": r"(?:https?://)?t\.me/\w+",
    # 商業推廣（用 \b 邊界，避免 workshop 這類單字被當成 shop）
    "shop_links": r"\b(?:shop|store|mall)\b",
}

# 重複連結檢測設置
DUPLICATE_LINK_TIME_WINDOW = 300  # 時間窗口：5 分鐘
SPAM_MENTION_TIME_WINDOW = 60  # @everyone/@here 檢測窗口：60 秒

# @everyone/@here 被使用的次數 -> 懲罰對應表
SPAM_MENTION_PUNISHMENT = {
    1: {"action": "none", "description": "允許"},
    2: {"action": "delete", "description": "刪除 + 警告"},
    3: {"action": "mute", "mute_duration": 300, "description": "禁言 5 分鐘 + 刪除"},
    4: {"action": "mute", "mute_duration": 600, "description": "禁言 10 分鐘 + 刪除"},
    5: {"action": "mute", "mute_duration": 1800, "description": "禁言 30 分鐘 + 刪除"},
    6: {"action": "kick", "description": "踢出"},  # 6 次才踢出
}

# 同一連結被貼的次數 -> 懲罰對應表
SPAM_LINK_PUNISHMENT = {
    1: {"action": "none", "description": "允許"},  # 1-2 次：不動作
    2: {"action": "none", "description": "允許"},
    3: {"action": "warn", "description": "警告 + 刪除"},  # 3 次：警告
    4: {"action": "delete", "description": "刪除"},  # 4 次：刪除
    5: {
        "action": "mute",
        "mute_duration": 300,
        "description": "禁言 5 分鐘 + 刪除",
    },  # 5 次：禁言
    6: {"action": "mute", "mute_duration": 600, "description": "禁言 10 分鐘 + 刪除"},
    7: {"action": "mute", "mute_duration": 1200, "description": "禁言 20 分鐘 + 刪除"},
    8: {"action": "mute", "mute_duration": 1800, "description": "禁言 30 分鐘 + 刪除"},
}


class AntiAdvertising(commands.Cog):
    """防廣告系統 - 檢測並處理不當廣告行為"""

    def __init__(self, bot):
        self.bot = bot
        self.muted_users: Dict[int, datetime] = {}  # 追蹤禁言狀態
        # 追蹤重複連結 {(user_id, 連結): [timestamp, ...]}
        # 一定要分使用者：原本用全伺服器共用一個計數，第 3 個貼的人（可能是無辜的）
        # 反而會被打，真正在洗的人卻沒事。
        self.duplicate_links: Dict[tuple[int, str], List[datetime]] = {}
        self.spam_mentions: Dict[
            int, List[datetime]
        ] = {}  # 追蹤 @everyone/@here 使用 {user_id: [timestamp, ...]}
        self.cleanup_mutes.start()
        logger.info("✅ 防廣告系統已初始化")

    def cog_unload(self):
        """卸載時停止任務"""
        self.cleanup_mutes.cancel()
        logger.info("❌ 防廣告系統已卸載")

    # ==================== 廣告檢測 ====================
    def _detect_advertising(self, content: str) -> Optional[tuple[str, str]]:
        """
        檢測消息中的廣告內容
        返回: (檢測到的類型, 匹配的內容) 或 None
        """
        for pattern_name, pattern in ADVERTISING_PATTERNS.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                return (
                    pattern_name,
                    matches[0] if isinstance(matches[0], str) else str(matches[0]),
                )
        return None

    def _track_duplicate_link(self, user_id: int, link: str) -> int:
        """
        追蹤單一使用者重複貼同一連結的次數，並順手清掉過期記錄

        時間一律用 discord.utils.utcnow()（帶時區）；用 datetime.utcnow()（不帶時區）
        相減會直接丟 TypeError，把背景清理任務整個弄死。

        返回: 該使用者在時間窗口內貼此連結的次數
        """
        now = discord.utils.utcnow()
        key = (user_id, link)

        records = [
            ts
            for ts in self.duplicate_links.get(key, [])
            if (now - ts).total_seconds() < DUPLICATE_LINK_TIME_WINDOW
        ]
        records.append(now)
        self.duplicate_links[key] = records

        return len(records)

    def _track_spam_mention(self, user_id: int) -> int:
        """
        追蹤 @everyone/@here 使用次數
        返回: 該用戶在時間窗口內使用的總次數
        """
        now = discord.utils.utcnow()

        # 初始化追蹤
        if user_id not in self.spam_mentions:
            self.spam_mentions[user_id] = []

        # 清理超出時間窗口的記錄
        self.spam_mentions[user_id] = [
            ts
            for ts in self.spam_mentions[user_id]
            if (now - ts).total_seconds() < SPAM_MENTION_TIME_WINDOW
        ]

        # 添加新記錄
        self.spam_mentions[user_id].append(now)

        # 返回總次數
        return len(self.spam_mentions[user_id])

    def _detect_spam_mention(self, message: discord.Message) -> bool:
        """
        檢測是否有 @everyone 或 @here 標籤
        返回: True 如果存在危險的 mention
        """
        # 檢查 mention 物件
        if message.mentions:
            # 如果消息提及超過基本數量的人，可能是濫用
            if len(message.mentions) > 10:
                return True

        # 檢查 mention_everyone 標誌（@everyone/@here）
        if message.mention_everyone:
            return True

        # 檢查文字中是否包含 @everyone/@here
        if re.search(r"@everyone|@here", message.content, re.IGNORECASE):
            return True

        return False

    # ==================== 執行措施 ====================
    async def _notify_user(
        self,
        channel: discord.abc.Messageable,
        user: discord.Member,
        embed: discord.Embed,
        fallback_text: Optional[str] = None,
    ):
        """
        通知違規使用者：先私訊，私訊關閉時退回頻道短暫訊息

        收斂成單一入口，避免每個懲罰分支各自 try/except 而行為不一致
        （原本 warn 有頻道備援、mute 沒有，且用裸 except 把所有錯誤吞掉）。
        """
        try:
            await user.send(embed=embed)
            return
        except discord.Forbidden:
            pass  # 對方關閉私訊，改用頻道備援
        except discord.HTTPException as e:
            logger.warning("⚠️ 無法私訊 %s: %s", user.name, e)
            return

        if not fallback_text:
            return

        try:
            await channel.send(f"{user.mention} {fallback_text}", delete_after=30)
        except discord.HTTPException as e:
            logger.warning("⚠️ 無法在頻道通知 %s: %s", user.name, e)

    async def _handle_violation(
        self,
        message: discord.Message,
        pattern_type: str,
        matched_content: str,
        spam_count: int = 0,
    ):
        """
        根據重複連結計數決定懲罰

        Args:
            message: Discord 消息物件
            pattern_type: 廣告類型
            matched_content: 符合的連結內容
            spam_count: 該使用者在時間窗口內貼此連結的次數

        懲罰對應表：
        - 1-2 次：不動作
        - 3 次：警告 + 刪除
        - 4 次：刪除（會通知）
        - 5+ 次：禁言（時間遞增）+ 刪除
        """
        user = message.author

        # 跳過管理員和機器人
        if user.bot or self._is_admin(user):
            return

        # 根據計數獲取懲罰
        punishment = SPAM_LINK_PUNISHMENT.get(
            spam_count, SPAM_LINK_PUNISHMENT[8]
        )  # 超過 8 次用最高懲罰
        action = punishment["action"]
        description = punishment["description"]

        logger.info("📢 連結 #%s (%s): %s", spam_count, pattern_type, matched_content)
        logger.info("   懲罰: %s", description)

        # 1. 刪除消息（警告以上都刪，與懲罰表描述一致）
        if action in ["warn", "delete", "mute"]:
            try:
                await message.delete()
                logger.info("🗑️ 已刪除消息")
            except discord.Forbidden:
                logger.warning("⚠️ 無法刪除消息 - 權限不足")
            except discord.HTTPException as e:
                logger.warning("⚠️ 刪除消息失敗: %s", e)

        # 2. 根據懲罰類型執行
        try:
            if action == "warn":
                # 發送警告 Embed
                embed = discord.Embed(
                    title="⚠️ 廣告連結警告",
                    description=f"檢測到同一連結在短時間內被多次貼文。\n\n"
                    f"此連結已被貼 **{spam_count} 次**，請勿再發送相同連結。",
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="📎 連結內容", value=f"`{matched_content[:100]}`", inline=False
                )
                embed.add_field(
                    name="⚖️ 後續懲罰",
                    value="第 4 次：刪除\n第 5 次：禁言 5 分鐘\n",
                    inline=False,
                )
                embed.set_footer(text="若再次違規將自動執行懲罰")

                await self._notify_user(
                    message.channel, user, embed, fallback_text=embed.description
                )

            elif action == "delete":
                # 原本這裡是靜默刪除，使用者完全不知道發生什麼事，補上通知
                embed = discord.Embed(
                    title="🗑️ 訊息已刪除",
                    description=f"同一連結已被貼 **{spam_count} 次**，該訊息已刪除。",
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="📎 連結內容", value=f"`{matched_content[:100]}`", inline=False
                )

                await self._notify_user(
                    message.channel, user, embed, fallback_text=embed.description
                )

            elif action == "mute":
                # 禁言處理
                mute_duration = punishment["mute_duration"]
                await self._mute_user(
                    message.guild,
                    user,
                    mute_duration,
                    f"廣告濫用 - 同一連結被貼 {spam_count} 次",
                )

                # 發送禁言通知
                embed = discord.Embed(
                    title="🔇 禁言通知",
                    description=f"因為同一連結被貼 **{spam_count} 次**，您已被禁言。",
                    color=discord.Color.red(),
                )
                embed.add_field(
                    name="⏱️ 禁言時長", value=f"{mute_duration // 60} 分鐘", inline=False
                )
                embed.add_field(
                    name="📎 違規連結", value=f"`{matched_content[:100]}`", inline=False
                )

                await self._notify_user(
                    message.channel, user, embed, fallback_text=embed.description
                )

        except discord.Forbidden:
            logger.warning("⚠️ 無法對 %s 進行懲罰 - 權限不足", user.name)

    async def _mute_user(
        self, guild: discord.Guild, user: discord.Member, duration: int, reason: str
    ):
        """
        禁言使用者指定時間（秒）
        使用 Discord timeout 功能
        """
        try:
            until = discord.utils.utcnow() + timedelta(seconds=duration)
            await user.timeout(until, reason=reason)
            self.muted_users[user.id] = until
            logger.info("🔇 已禁言 %s %s 秒 - %s", user.name, duration, reason)
        except discord.Forbidden:
            logger.warning("⚠️ 無法禁言 %s - 權限不足", user.name)
        except discord.HTTPException as e:
            logger.warning("⚠️ 禁言 %s 失敗: %s", user.name, e)

    async def _handle_spam_mention_violation(
        self, message: discord.Message, mention_count: int
    ):
        """
        根據 @everyone/@here 計數決定懲罰

        懲罰對應表：
        - 2 次：刪除 + 警告
        - 3-5 次：禁言（時間遞增）+ 刪除
        - 6+ 次：踢出
        """
        user = message.author

        # 跳過管理員和機器人
        if user.bot or self._is_admin(user):
            return

        # 根據計數獲取懲罰
        punishment = SPAM_MENTION_PUNISHMENT.get(
            mention_count, SPAM_MENTION_PUNISHMENT[6]
        )  # 超過 6 次用踢出
        action = punishment["action"]
        description = punishment["description"]

        logger.info("🚨 @everyone/@here #%s: %s", mention_count, description)

        # 1. 刪除消息
        try:
            await message.delete()
            logger.info("🗑️ 已刪除訊息")
        except discord.Forbidden:
            logger.warning("⚠️ 無法刪除訊息 - 權限不足")
        except discord.HTTPException as e:
            logger.warning("⚠️ 刪除訊息失敗: %s", e)

        # 2. 根據懲罰類型執行
        try:
            if action == "delete":
                # 發送警告
                embed = discord.Embed(
                    title="⚠️ @everyone/@here 警告",
                    description=f"您在短時間內使用了 @everyone/@here 標籤 **{mention_count} 次**。\n\n請停止這種行為，否則將被禁言。",
                    color=discord.Color.orange(),
                )
                await self._notify_user(
                    message.channel, user, embed, fallback_text=embed.description
                )

            elif action == "mute":
                mute_duration = punishment["mute_duration"]
                await self._mute_user(
                    message.guild,
                    user,
                    mute_duration,
                    f"濫用 @everyone/@here - 第 {mention_count} 次",
                )

                embed = discord.Embed(
                    title="🔇 禁言通知",
                    description=f"因為您在短時間內多次使用 @everyone/@here（**{mention_count} 次**），您已被禁言。",
                    color=discord.Color.red(),
                )
                embed.add_field(
                    name="⏱️ 禁言時長", value=f"{mute_duration // 60} 分鐘", inline=False
                )
                await self._notify_user(
                    message.channel, user, embed, fallback_text=embed.description
                )

            elif action == "kick":
                # 踢出是最後手段
                await self._kick_user(
                    user, f"濫用 @everyone/@here 標籤超過 {mention_count} 次"
                )

        except discord.Forbidden:
            logger.warning("⚠️ 無法對 %s 進行懲罰 - 權限不足", user.name)

    async def _kick_user(self, user: discord.Member, reason: str) -> bool:
        """
        踢出使用者
        """
        try:
            await user.kick(reason=reason)
            logger.info("🚪 已踢出 %s - %s", user.name, reason)
            return True
        except discord.Forbidden:
            logger.warning("⚠️ 無法踢出 %s - 權限不足", user.name)
            return False
        except discord.HTTPException as e:
            logger.warning("⚠️ 踢出 %s 失敗: %s", user.name, e)
            return False

    def _is_admin(self, user: discord.Member) -> bool:
        """
        檢查使用者是否為管理員／機器人擁有者

        回傳真正的 bool：原本寫成 `A or B and C or D and E` 的短路鏈，會把
        Role 物件本身當成回傳值，呼叫端 `if self._is_admin(...)` 剛好能用，
        但只要有人寫 `is True` 或 `== True` 就會踩雷。
        """
        if user.id == self.bot.owner_id:
            return True

        if getattr(user, "guild_permissions", None) and (
            user.guild_permissions.administrator
        ):
            return True

        return bool(ADMIN_ROLE_ID and discord.utils.get(user.roles, id=ADMIN_ROLE_ID))

    # ==================== 事件監聽 ====================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """監聽所有新消息並檢測廣告、洗版、帳號盜用行為"""

        # 忽略機器人和私訊
        if message.author.bot or not message.guild:
            return

        # 忽略管理員消息
        if self._is_admin(message.author):
            return

        user = message.author

        # ==================== 檢測 1: @everyone/@here 濫用 =====================
        has_spam_mention = self._detect_spam_mention(message)
        if has_spam_mention:
            mention_count = self._track_spam_mention(user.id)
            logger.info(
                "🚨 檢測到 @everyone/@here: %s (第 %s 次)", user.name, mention_count
            )

            if mention_count >= 2:
                await self._handle_spam_mention_violation(message, mention_count)
            else:
                logger.info("ℹ️ 第一次 @everyone/@here，暫不懲罰。")
            return

        # ==================== 檢測 2: 廣告連結 =====================
        result = self._detect_advertising(message.content)
        if result:
            pattern_type, matched_content = result
            logger.info(
                "📢 檢測到廣告: %s 在 #%s (類型: %s, 內容: %s)",
                user.name,
                message.channel.name,
                pattern_type,
                matched_content,
            )

            # 追蹤重複連結（必須帶 user.id：不分使用者的話，第 3 個貼的人會替
            # 真正在洗的人背鍋）
            spam_count = self._track_duplicate_link(user.id, matched_content)
            logger.info("   累計次數: %s", spam_count)

            # 當重複次數 >= 3 時才觸發懲罰
            if spam_count >= 3:
                await self._handle_violation(
                    message, pattern_type, matched_content, spam_count
                )

    # ==================== 背景任務 ====================
    @tasks.loop(minutes=5)
    async def cleanup_mutes(self):
        """清理過期的禁言記錄和重複連結追蹤"""
        now = discord.utils.utcnow()

        # 清理過期禁言
        expired = [
            user_id for user_id, until in self.muted_users.items() if now >= until
        ]
        for user_id in expired:
            del self.muted_users[user_id]

        if expired:
            logger.info("🧹 清理了 %s 個過期禁言記錄", len(expired))

        # 清理過期的重複連結追蹤
        # 用 list(...) 先快照：邊迭代邊 del 會丟 RuntimeError
        cleaned_links = 0

        for key, records in list(self.duplicate_links.items()):
            kept = [
                ts
                for ts in records
                if (now - ts).total_seconds() < DUPLICATE_LINK_TIME_WINDOW
            ]

            if kept:
                self.duplicate_links[key] = kept
            else:
                del self.duplicate_links[key]
                cleaned_links += 1

        if cleaned_links > 0:
            logger.info("🧹 清理了 %s 個過期的連結追蹤記錄", cleaned_links)

        # 清理過期的 @everyone/@here 計數
        self._cleanup_spam_mention_records()

    @cleanup_mutes.before_loop
    async def before_cleanup_mutes(self):
        await self.bot.wait_until_ready()

    def _cleanup_spam_mention_records(self):
        """
        定期清理過期的 @everyone/@here 計數記錄
        """
        # 時間一律用 discord.utils.utcnow()（帶時區），與 _track_spam_mention 一致
        now = discord.utils.utcnow()
        users_to_clean = []

        for user_id, records in self.spam_mentions.items():
            # 清理超出時間窗口的記錄
            self.spam_mentions[user_id] = [
                ts
                for ts in records
                if (now - ts).total_seconds() < SPAM_MENTION_TIME_WINDOW
            ]

            # 如果沒有記錄了，標記為移除
            if not self.spam_mentions[user_id]:
                users_to_clean.append(user_id)

        # 移除空的用戶記錄
        for user_id in users_to_clean:
            del self.spam_mentions[user_id]

        if users_to_clean:
            logger.info(
                "🧹 清理了 %s 個過期的 @everyone/@here 計數記錄", len(users_to_clean)
            )

    # ==================== 管理命令 ====================


# 載入 Cog
async def setup(bot):
    await bot.add_cog(AntiAdvertising(bot))
