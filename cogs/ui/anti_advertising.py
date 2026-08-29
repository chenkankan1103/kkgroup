"""
防廣告系統 Cog - 預防不當廣告和邀請連結
監聽消息，檢測廣告內容，並採取相應措施（刪除、禁言、踢出）
"""

import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

# ==================== 配置 ====================
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", 0))

# 廣告內容模式（正則表達式）
ADVERTISING_PATTERNS = {
    # Discord 邀請連結
    "discord_invite": r"(?:https?://)?discord\.gg/\w+",
    "discord_base": r"(?:https?://)?discord\.(com|gg|app)/",
    # 其他遊戲/社群邀請
    "invite_links": r"(?:https?://)?(?:join|invite|server)[\w\.\/-]*",
    # 社群媒體推廣
    "twitch": r"(?:https?://)?(?:www\.)?twitch\.tv/\w+",
    "youtube": r"(?:https?://)?(?:www\.)?youtube\.com/(?:c|channel|user)",
    "tiktok": r"(?:https?://)?(?:www\.)?tiktok\.com/@\w+",
    "ig": r"(?:https?://)?(?:www\.)?instagram\.com/\w+",
    "telegram": r"(?:https?://)?t\.me/\w+",
    # 商業推廣
    "shop_links": r"(?:shop|store|mall|商店|購物|賣場)",
}

# 違規等級
VIOLATION_LEVELS = {
    "low": {"warning_count": 1, "mute_duration": 300},  # 5分鐘禁言
    "medium": {"warning_count": 2, "mute_duration": 1800},  # 30分鐘禁言
    "high": {"warning_count": 3, "mute_duration": 3600},  # 1小時禁言
    "critical": {"warning_count": 4, "mute_duration": 86400},  # 1天禁言 + 踢出
}

# 重複連結檢測設置
DUPLICATE_LINK_TIME_WINDOW = 300  # 時間窗口：5 分鐘
SPAM_MENTION_TIME_WINDOW = 60  # @everyone/@here 檢測窗口：60 秒
CROSS_CHANNEL_SPAM_TIME_WINDOW = 60  # 跨頻道洗版檢測：60 秒
CROSS_CHANNEL_SPAM_THRESHOLD = 5  # 在多少個不同頻道發送就算嚴重洗版（踢出門檻）

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
        self.violations: Dict[int, List[datetime]] = {}  # 追蹤過去 24 小時的違規
        self.muted_users: Dict[int, datetime] = {}  # 追蹤禁言狀態
        self.duplicate_links: Dict[str, List[datetime]] = (
            {}
        )  # 追蹤重複連結 {連結: [timestamp, ...]}
        self.spam_mentions: Dict[int, List[datetime]] = (
            {}
        )  # 追蹤 @everyone/@here 使用 {user_id: [timestamp, ...]}
        self.cross_channel_spam: Dict[int, List[dict]] = (
            {}
        )  # 追蹤跨頻道洗版 {user_id: [{channel_id, content, timestamp}, ...]}
        self.cleanup_mutes.start()
        print("✅ 防廣告系統已初始化")

    def cog_unload(self):
        """卸載時停止任務"""
        self.cleanup_mutes.cancel()
        print("❌ 防廣告系統已卸載")

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

    def _track_duplicate_link(self, link: str) -> int:
        """
        追蹤重複連結，清理過期記錄
        返回: 該連結在時間窗口內的總次數（不區分使用者）
        """
        now = datetime.utcnow()

        # 初始化追蹤
        if link not in self.duplicate_links:
            self.duplicate_links[link] = []

        # 清理超出時間窗口的記錄
        self.duplicate_links[link] = [
            ts
            for ts in self.duplicate_links[link]
            if (now - ts).total_seconds() < DUPLICATE_LINK_TIME_WINDOW
        ]

        # 添加新記錄
        self.duplicate_links[link].append(now)

        # 返回總次數
        return len(self.duplicate_links[link])

    def _get_violation_level(self, user_id: int) -> str:
        """
        根據 24 小時內的違規次數判斷違規等級
        """
        now = datetime.utcnow()

        # 清理 24 小時外的違規記錄
        if user_id in self.violations:
            self.violations[user_id] = [
                v for v in self.violations[user_id] if (now - v).total_seconds() < 86400
            ]

        violation_count = len(self.violations.get(user_id, []))

        if violation_count >= 4:
            return "critical"
        elif violation_count >= 3:
            return "high"
        elif violation_count >= 2:
            return "medium"
        else:
            return "low"

    def _add_violation(self, user_id: int):
        """記錄一次違規"""
        if user_id not in self.violations:
            self.violations[user_id] = []
        self.violations[user_id].append(datetime.utcnow())

    def _track_spam_mention(self, user_id: int) -> int:
        """
        追蹤 @everyone/@here 使用次數
        返回: 該用戶在時間窗口內使用的總次數
        """
        now = datetime.utcnow()

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

    def _track_cross_channel_spam(
        self, user_id: int, channel_id: int, content: str
    ) -> int:
        """
        追蹤跨頻道洗版
        返回: 在不同頻道發送相同/相似內容的頻道數量
        """
        now = datetime.utcnow()

        # 初始化用戶追蹤
        if user_id not in self.cross_channel_spam:
            self.cross_channel_spam[user_id] = []

        # 清理超出時間窗口的記錄
        self.cross_channel_spam[user_id] = [
            record
            for record in self.cross_channel_spam[user_id]
            if (now - record["timestamp"]).total_seconds()
            < CROSS_CHANNEL_SPAM_TIME_WINDOW
        ]

        # 添加新記錄
        self.cross_channel_spam[user_id].append(
            {
                "channel_id": channel_id,
                "content": content[:100],  # 只存前 100 字
                "timestamp": now,
            }
        )

        # 計算有多少個不同的頻道
        unique_channels = set(
            record["channel_id"] for record in self.cross_channel_spam[user_id]
        )
        return len(unique_channels)

    def _is_account_compromised(
        self, message: discord.Message, cross_channel_count: int
    ) -> bool:
        """
        判斷帳號是否可能被盜
        條件：在非常多個頻道跨頻道發送（5+ 頻道），且有附帶內容
        """
        # 只有在非常嚴重的跨頻道洗版時才判定為被盜
        # 門檻很高：5+ 頻道 + 附帶內容
        if (
            cross_channel_count >= CROSS_CHANNEL_SPAM_THRESHOLD
            and len(message.attachments) > 0
        ):
            return True

        return False

    # ==================== 執行措施 ====================
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
            spam_count: 該連結在時間窗口內被貼的總次數

        懲罰對應表：
        - 1-2 次：不動作
        - 3 次：警告 + 刪除
        - 4 次：刪除
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

        print(f"📢 連結 #{spam_count}: {matched_content}")
        print(f"   懲罰: {description}")

        # 1. 刪除消息（只有 delete/mute 需要刪除，warn 僅警告）
        deleted = False
        if action in ["delete", "mute"]:
            try:
                await message.delete()
                deleted = True
                print("🗑️ 已刪除消息")
            except discord.Forbidden:
                print("⚠️ 無法刪除消息 - 權限不足")

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

                try:
                    await user.send(embed=embed)
                except:
                    # 無法 DM，嘗試在頻道發送（短期）
                    try:
                        await message.channel.send(
                            f"{user.mention} {embed.description}", delete_after=30
                        )
                    except:
                        pass

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
                    name="⏱️ 禁言時長",
                    value=f"{mute_duration // 60} 分鐘",
                    inline=False,
                )
                embed.add_field(
                    name="📎 違規連結", value=f"`{matched_content[:100]}`", inline=False
                )

                try:
                    await user.send(embed=embed)
                except:
                    pass

        except discord.Forbidden:
            print(f"⚠️ 無法對 {user.name} 進行懲罰 - 權限不足")

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
            print(f"🔇 已禁言 {user.name} {duration} 秒 - {reason}")
        except discord.Forbidden:
            print(f"⚠️ 無法禁言 {user.name} - 權限不足")

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

        print(f"🚨 @everyone/@here #{mention_count}: {description}")

        # 1. 刪除消息
        try:
            await message.delete()
            print("🗑️ 已刪除訊息")
        except discord.Forbidden:
            print("⚠️ 無法刪除訊息 - 權限不足")

        # 2. 根據懲罰類型執行
        try:
            if action == "delete":
                # 發送警告
                embed = discord.Embed(
                    title="⚠️ @everyone/@here 警告",
                    description=f"您在短時間內使用了 @everyone/@here 標籤 **{mention_count} 次**。\n\n請停止這種行為，否則將被禁言。",
                    color=discord.Color.orange(),
                )
                try:
                    await user.send(embed=embed)
                except:
                    pass

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
                    name="⏱️ 禁言時長",
                    value=f"{mute_duration // 60} 分鐘",
                    inline=False,
                )
                try:
                    await user.send(embed=embed)
                except:
                    pass

            elif action == "kick":
                # 踢出是最後手段
                kicked = await self._kick_user(
                    user, f"濫用 @everyone/@here 標籤超過 {mention_count} 次"
                )
                print(f"🚪 已踢出 {user.name}")

        except discord.Forbidden:
            print(f"⚠️ 無法對 {user.name} 進行懲罰 - 權限不足")

    async def _kick_user(self, user: discord.Member, reason: str):
        """
        踢出使用者
        """
        try:
            await user.kick(reason=reason)
            print(f"🚪 已踢出 {user.name} - {reason}")
            return True
        except discord.Forbidden:
            print(f"⚠️ 無法踢出 {user.name} - 權限不足")
            return False

    async def _delete_user_messages(
        self, guild: discord.Guild, user: discord.Member, time_window: int = 300
    ):
        """
        刪除使用者過去 N 秒內在所有頻道的訊息
        """
        deleted_count = 0
        cutoff_time = discord.utils.utcnow() - timedelta(seconds=time_window)

        for channel in guild.text_channels:
            try:
                async for message in channel.history(limit=100):
                    if (
                        message.author.id == user.id
                        and message.created_at > cutoff_time
                    ):
                        try:
                            await message.delete()
                            deleted_count += 1
                        except discord.Forbidden:
                            continue
            except discord.Forbidden:
                continue

        print(f"🗑️ 已刪除 {user.name} 的 {deleted_count} 則訊息")
        return deleted_count

    def _is_admin(self, user: discord.Member) -> bool:
        """檢查使用者是否為管理員"""
        if isinstance(user, discord.User):
            return user.id == self.bot.owner_id

        return (
            user.guild_permissions.administrator
            or ADMIN_ROLE_ID
            and discord.utils.get(user.roles, id=ADMIN_ROLE_ID)
            or MOD_ROLE_ID
            and discord.utils.get(user.roles, id=MOD_ROLE_ID)
        )

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
            print(f"🚨 檢測到 @everyone/@here: {user.name} (第 {mention_count} 次)")

            if mention_count >= 2:
                await self._handle_spam_mention_violation(message, mention_count)
            else:
                print("ℹ️ 第一次 @everyone/@here，暫不懲罰。")
            return

        # ==================== 檢測 2: 廣告連結 =====================
        result = self._detect_advertising(message.content)
        if result:
            pattern_type, matched_content = result
            print(f"📢 檢測到廣告: {user.name} 在 #{message.channel.name}")
            print(f"   類型: {pattern_type}, 內容: {matched_content}")

            # 追蹤重複連結
            spam_count = self._track_duplicate_link(matched_content)
            print(f"   累計次數: {spam_count}")

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
            print(f"🧹 清理了 {len(expired)} 個過期禁言記錄")

        # 清理過期的重複連結追蹤
        cleaned_links = 0
        links_to_remove = []

        for link, records in self.duplicate_links.items():
            # 保留時間窗口內的記錄
            self.duplicate_links[link] = [
                ts
                for ts in records
                if (now - ts).total_seconds() < DUPLICATE_LINK_TIME_WINDOW
            ]

            # 如果連結沒有時間窗口內的記錄，標記為移除
            if not self.duplicate_links[link]:
                links_to_remove.append(link)
                cleaned_links += 1

        # 移除空的連結記錄
        for link in links_to_remove:
            del self.duplicate_links[link]

        if cleaned_links > 0:
            print(f"🧹 清理了 {cleaned_links} 個過期的連結追蹤記錄")

        # 清理過期的 @everyone/@here 計數
        await self._cleanup_spam_mention_records()

        # 清理跨頻道洗版記錄
        await self._cleanup_cross_channel_records()

    @cleanup_mutes.before_loop
    async def before_cleanup_mutes(self):
        await self.bot.wait_until_ready()

    async def _cleanup_spam_mention_records(self):
        """
        定期清理過期的 @everyone/@here 計數記錄
        """
        now = datetime.utcnow()
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
            print(f"🧹 清理了 {len(users_to_clean)} 個過期的 @everyone/@here 計數記錄")

    async def _cleanup_cross_channel_records(self):
        """
        定期清理過期的跨頻道洗版記錄
        """
        now = datetime.utcnow()
        users_to_clean = []

        for user_id, records in self.cross_channel_spam.items():
            # 清理超出時間窗口的記錄
            self.cross_channel_spam[user_id] = [
                record
                for record in records
                if (now - record["timestamp"]).total_seconds()
                < CROSS_CHANNEL_SPAM_TIME_WINDOW
            ]

            # 如果沒有記錄了，標記為移除
            if not self.cross_channel_spam[user_id]:
                users_to_clean.append(user_id)

        # 移除空的用戶記錄
        for user_id in users_to_clean:
            del self.cross_channel_spam[user_id]

        if users_to_clean:
            print(f"🧹 清理了 {len(users_to_clean)} 個過期的跨頻道洗版記錄")

    # ==================== 管理命令 ====================


# 載入 Cog
async def setup(bot):
    await bot.add_cog(AntiAdvertising(bot))
