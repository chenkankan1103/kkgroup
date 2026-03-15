"""
防廣告系統 Cog - 預防不當廣告和邀請連結
監聽消息，檢測廣告內容，並採取相應措施（刪除、禁言、踢出）
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import re
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dotenv import load_dotenv
from db_adapter import get_user_field, set_user_field

load_dotenv()

# ==================== 配置 ====================
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", 0))

# 廣告內容模式（正則表達式）
ADVERTISING_PATTERNS = {
    # Discord 邀請連結
    'discord_invite': r'(?:https?://)?discord\.gg/\w+',
    'discord_base': r'(?:https?://)?discord\.(com|gg|app)/',
    
    # 其他遊戲/社群邀請
    'invite_links': r'(?:https?://)?(?:join|invite|server)[\w\.\/-]*',
    
    # 社群媒體推廣
    'twitch': r'(?:https?://)?(?:www\.)?twitch\.tv/\w+',
    'youtube': r'(?:https?://)?(?:www\.)?youtube\.com/(?:c|channel|user)',
    'tiktok': r'(?:https?://)?(?:www\.)?tiktok\.com/@\w+',
    'ig': r'(?:https?://)?(?:www\.)?instagram\.com/\w+',
    'telegram': r'(?:https?://)?t\.me/\w+',
    
    # 商業推廣
    'shop_links': r'(?:shop|store|mall|商店|購物|賣場)',
}

# 違規等級
VIOLATION_LEVELS = {
    'low': {'warning_count': 1, 'mute_duration': 300},        # 5分鐘禁言
    'medium': {'warning_count': 2, 'mute_duration': 1800},    # 30分鐘禁言
    'high': {'warning_count': 3, 'mute_duration': 3600},      # 1小時禁言
    'critical': {'warning_count': 4, 'mute_duration': 86400}, # 1天禁言 + 踢出
}

# 重複連結檢測設置
DUPLICATE_LINK_TIME_WINDOW = 300  # 時間窗口：5 分鐘

# 同一連結被貼的次數 -> 懲罰對應表
SPAM_LINK_PUNISHMENT = {
    1: {'action': 'none', 'description': '允許'},           # 1-2 次：不動作
    2: {'action': 'none', 'description': '允許'},
    3: {'action': 'warn', 'description': '警告 + 刪除'},    # 3 次：警告
    4: {'action': 'delete', 'description': '刪除'},         # 4 次：刪除
    5: {'action': 'mute', 'mute_duration': 300, 'description': '禁言 5 分鐘 + 刪除'},  # 5 次：禁言
    6: {'action': 'mute', 'mute_duration': 600, 'description': '禁言 10 分鐘 + 刪除'},
    7: {'action': 'mute', 'mute_duration': 1200, 'description': '禁言 20 分鐘 + 刪除'},
    8: {'action': 'mute', 'mute_duration': 1800, 'description': '禁言 30 分鐘 + 刪除'},
}

class AntiAdvertising(commands.Cog):
    """防廣告系統 - 檢測並處理不當廣告行為"""
    
    def __init__(self, bot):
        self.bot = bot
        self.violations: Dict[int, List[datetime]] = {}  # 追蹤過去 24 小時的違規
        self.muted_users: Dict[int, datetime] = {}  # 追蹤禁言狀態
        self.duplicate_links: Dict[str, List[datetime]] = {}  # 追蹤重複連結 {連結: [timestamp, ...]}
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
                return (pattern_name, matches[0] if isinstance(matches[0], str) else str(matches[0]))
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
            ts for ts in self.duplicate_links[link]
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
                v for v in self.violations[user_id] 
                if (now - v).total_seconds() < 86400
            ]
        
        violation_count = len(self.violations.get(user_id, []))
        
        if violation_count >= 4:
            return 'critical'
        elif violation_count >= 3:
            return 'high'
        elif violation_count >= 2:
            return 'medium'
        else:
            return 'low'
    
    def _add_violation(self, user_id: int):
        """記錄一次違規"""
        if user_id not in self.violations:
            self.violations[user_id] = []
        self.violations[user_id].append(datetime.utcnow())
    
    # ==================== 執行措施 ====================
    async def _handle_violation(self, 
                               message: discord.Message, 
                               pattern_type: str,
                               matched_content: str,
                               spam_count: int = 0):
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
        punishment = SPAM_LINK_PUNISHMENT.get(spam_count, SPAM_LINK_PUNISHMENT[8])  # 超過 8 次用最高懲罰
        action = punishment['action']
        description = punishment['description']
        
        print(f"📢 連結 #{spam_count}: {matched_content}")
        print(f"   懲罰: {description}")
        
        # 1. 刪除消息（只有 delete/mute 需要刪除，warn 僅警告）
        deleted = False
        if action in ['delete', 'mute']:
            try:
                await message.delete()
                deleted = True
                print(f"🗑️ 已刪除消息")
            except discord.Forbidden:
                print(f"⚠️ 無法刪除消息 - 權限不足")
        
        # 2. 根據懲罰類型執行
        try:
            if action == 'warn':
                # 發送警告 Embed
                embed = discord.Embed(
                    title="⚠️ 廣告連結警告",
                    description=f"檢測到同一連結在短時間內被多次貼文。\n\n"
                                f"此連結已被貼 **{spam_count} 次**，請勿再發送相同連結。",
                    color=discord.Color.orange()
                )
                embed.add_field(name="📎 連結內容", value=f"`{matched_content[:100]}`", inline=False)
                embed.add_field(
                    name="⚖️ 後續懲罰",
                    value="第 4 次：刪除\n第 5 次：禁言 5 分鐘\n",
                    inline=False
                )
                embed.set_footer(text=f"若再次違規將自動執行懲罰")
                
                try:
                    await user.send(embed=embed)
                except:
                    # 無法 DM，嘗試在頻道發送（短期）
                    try:
                        await message.channel.send(
                            f"{user.mention} {embed.description}",
                            delete_after=30
                        )
                    except:
                        pass
            
            elif action == 'mute':
                # 禁言處理
                mute_duration = punishment['mute_duration']
                await self._mute_user(
                    message.guild, 
                    user, 
                    mute_duration, 
                    f"廣告濫用 - 同一連結被貼 {spam_count} 次"
                )
                
                # 發送禁言通知
                embed = discord.Embed(
                    title="🔇 禁言通知",
                    description=f"因為同一連結被貼 **{spam_count} 次**，您已被禁言。",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="⏱️ 禁言時長",
                    value=f"{mute_duration // 60} 分鐘",
                    inline=False
                )
                embed.add_field(
                    name="📎 違規連結",
                    value=f"`{matched_content[:100]}`",
                    inline=False
                )
                
                try:
                    await user.send(embed=embed)
                except:
                    pass
        
        except discord.Forbidden:
            print(f"⚠️ 無法對 {user.name} 進行懲罰 - 權限不足")
    
    async def _mute_user(self, guild: discord.Guild, user: discord.Member, duration: int, reason: str):
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
    
    def _is_admin(self, user: discord.Member) -> bool:
        """檢查使用者是否為管理員"""
        if isinstance(user, discord.User):
            return user.id == self.bot.owner_id
        
        return (
            user.guild_permissions.administrator or
            ADMIN_ROLE_ID and discord.utils.get(user.roles, id=ADMIN_ROLE_ID) or
            MOD_ROLE_ID and discord.utils.get(user.roles, id=MOD_ROLE_ID)
        )
    
    # ==================== 事件監聽 ====================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """監聽所有消息並檢測廣告"""
        
        # 忽略機器人和私訊
        if message.author.bot or not message.guild:
            return
        
        # 忽略管理員消息
        if self._is_admin(message.author):
            return
        
        # 檢測廣告
        result = self._detect_advertising(message.content)
        if result:
            pattern_type, matched_content = result
            print(f"📢 檢測到廣告: {message.author.name} 在 #{message.channel.name}")
            print(f"   類型: {pattern_type}, 內容: {matched_content}")
            
            # 追蹤重複連結
            spam_count = self._track_duplicate_link(matched_content)
            print(f"   累計次數: {spam_count}")
            
            # 當重複次數 >= 3 時才觸發懲罰
            if spam_count >= 3:
                await self._handle_violation(message, pattern_type, matched_content, spam_count)
    
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """監聽編輯的消息"""
        
        # 忽略機器人和私訊
        if after.author.bot or not after.guild:
            return
        
        # 忽略管理員消息
        if self._is_admin(after.author):
            return
        
        # 檢測廣告
        result = self._detect_advertising(after.content)
        if result:
            pattern_type, matched_content = result
            print(f"🔄 編輯消息中檢測到廣告: {after.author.name}")
            
            # 追蹤重複連結
            spam_count = self._track_duplicate_link(matched_content)
            print(f"   累計次數: {spam_count}")
            
            # 當重複次數 >= 3 時才觸發懲罰
            if spam_count >= 3:
                await self._handle_violation(after, pattern_type, matched_content, spam_count)
    
    # ==================== 背景任務 ====================
    @tasks.loop(minutes=5)
    async def cleanup_mutes(self):
        """清理過期的禁言記錄和重複連結追蹤"""
        now = discord.utils.utcnow()
        
        # 清理過期禁言
        expired = [user_id for user_id, until in self.muted_users.items() if now >= until]
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
                (uid, ts) for uid, ts in records
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
    
    @cleanup_mutes.before_loop
    async def before_cleanup_mutes(self):
        await self.bot.wait_until_ready()
    
    # ==================== 管理命令 ====================
    @app_commands.command(name="ad_violations", description="檢查使用者的廣告違規歷史")
    @app_commands.describe(user="要檢查的使用者")
    async def check_violations(self, interaction: discord.Interaction, user: discord.User):
        """查詢使用者的廣告違規記錄"""
        
        violations = get_user_field(user.id, 'ad_violations') or []
        
        if not violations:
            await interaction.response.send_message(
                f"✅ {user.mention} 沒有廣告違規記錄",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"📋 {user.name} 的廣告違規記錄",
            color=discord.Color.orange()
        )
        
        for i, violation in enumerate(violations[-5:], 1):  # 顯示最新 5 筆
            timestamp = datetime.fromisoformat(violation['timestamp']).strftime('%Y-%m-%d %H:%M')
            embed.add_field(
                name=f"違規 #{i}",
                value=f"**類型**: {violation['type']}\n"
                      f"**時間**: {timestamp}\n"
                      f"**等級**: {violation['level']}\n"
                      f"**頻道**: {violation['channel']}",
                inline=False
            )
        
        embed.footer.text = f"共 {len(violations)} 筆記錄 | 只顯示最新 5 筆"
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="unmute", description="解除使用者禁言 (管理員用)")
    @app_commands.describe(user="要解除禁言的使用者")
    async def unmute_user(self, interaction: discord.Interaction, user: discord.Member):
        """手動解除禁言"""
        
        if not self._is_admin(interaction.user):
            await interaction.response.send_message("❌ 只有管理員可以使用此命令", ephemeral=True)
            return
        
        try:
            await user.timeout(None, reason="管理員手動解除")
            await interaction.response.send_message(
                f"✅ 已解除 {user.mention} 的禁言",
                ephemeral=True
            )
            print(f"🔊 {interaction.user.name} 解除了 {user.name} 的禁言")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 無法解除禁言 - 權限不足",
                ephemeral=True
            )
    
    @app_commands.command(name="clear_violations", description="清除使用者的違規記錄 (管理員用)")
    @app_commands.describe(user="要清除的使用者")
    async def clear_violations(self, interaction: discord.Interaction, user: discord.User):
        """清除使用者的違規記錄"""
        
        if not self._is_admin(interaction.user):
            await interaction.response.send_message("❌ 只有管理員可以使用此命令", ephemeral=True)
            return
        
        set_user_field(user.id, 'ad_violations', [])
        if user.id in self.violations:
            del self.violations[user.id]
        
        await interaction.response.send_message(
            f"✅ 已清除 {user.mention} 的所有違規記錄",
            ephemeral=True
        )
        print(f"🧹 {interaction.user.name} 清除了 {user.name} 的所有違規記錄")
    
    @app_commands.command(name="ad_settings", description="檢查防廣告系統設置")
    async def ad_settings(self, interaction: discord.Interaction):
        """顯示防廣告系統設置"""
        
        embed = discord.Embed(
            title="🛡️ 防廣告系統設置",
            color=discord.Color.blue(),
            description="目前的防廣告機制和重複連結懲罰"
        )
        
        # 顯示檢測類型
        detected_types = "\n".join([f"• {k.replace('_', ' ').title()}" for k in ADVERTISING_PATTERNS.keys()])
        embed.add_field(name="📢 檢測類型", value=detected_types, inline=False)
        
        # 顯示重複連結懲罰表
        punishment_info = ""
        for count in range(1, 9):
            punishment = SPAM_LINK_PUNISHMENT.get(count, SPAM_LINK_PUNISHMENT[8])
            action_emoji = {'none': '✅', 'warn': '⚠️', 'delete': '🗑️', 'mute': '🔇'}.get(punishment['action'], '❓')
            punishment_info += f"\n**{count} 次**: {action_emoji} {punishment['description']}"
        
        embed.add_field(name="📊 重複連結懲罰", value=punishment_info, inline=False)
        
        # 顯示系統設置
        spam_info = (
            f"⏱️ **時間窗口**: {DUPLICATE_LINK_TIME_WINDOW//60} 分鐘\n"
            f"🎯 **觸發條件**: 同一連結在時間窗口內被貼 3 次以上\n"
            f"📍 **計數方式**: 不區分使用者，全部頻道累計\n"
            f"⚡ **自動升級**: 超過 8 次使用最高懲罰"
        )
        embed.add_field(name="⚙️ 系統設置", value=spam_info, inline=False)
        
        # 提供幫助
        embed.add_field(
            name="📖 常用命令",
            value="• `/ad_violations @user` - 檢查違規記錄\n"
                  "• `/unmute @user` - 解除禁言\n"
                  "• `/clear_violations @user` - 清除記錄\n"
                  "• `/ad_settings` - 查看此設置",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# 載入 Cog
async def setup(bot):
    await bot.add_cog(AntiAdvertising(bot))
