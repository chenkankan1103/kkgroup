# -*- coding: utf-8 -*-
"""
進階會員身分權過期管理系統增強版
- 增強日誌記錄
- 添加管理員命令給予有時效的角色
- 監控機制
"""

import sqlite3
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Optional
import os
import traceback

DB_PATH = os.getenv("DB_PATH", "user_data.db")

class EnhancedRoleExpirationManager(commands.Cog):
    """增強的角色過期管理系統"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_id = int(os.getenv("GUILD_ID", 0))
        
    @app_commands.command(
        name="grant_temporary_role",
        description="⚙️ 管理員：給予用戶臨時身分（帶過期時間）"
    )
    @app_commands.describe(
        user="要給予身分的用戶",
        role="要給予的身分",
        duration_days="持續天數（1-365天）"
    )
    async def grant_temporary_role(
        self, 
        interaction: discord.Interaction,
        user: discord.User,
        role: discord.Role,
        duration_days: int = 7
    ):
        """
        給予用戶臨時身分
        
        Args:
            user: 目標用戶
            role: 要給予的身分
            duration_days: 持續天數
        """
        try:
            # 檢查權限
            if interaction.user.id != int(os.getenv("ADMIN_USER_ID", 0)):
                await interaction.response.send_message(
                    "❌ 你沒有權限使用此命令！",
                    ephemeral=True
                )
                return
            
            # 驗證參數
            if duration_days < 1 or duration_days > 365:
                await interaction.response.send_message(
                    "❌ 持續時間必須在 1-365 天之間！",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            guild = interaction.guild
            member = guild.get_member(user.id)
            
            if not member:
                await interaction.followup.send(
                    f"❌ {user.mention} 不是此伺服器的成員！",
                    ephemeral=True
                )
                return
            
            # 計算過期時間
            duration_seconds = duration_days * 86400
            expires_at = datetime.now() + timedelta(seconds=duration_seconds)
            
            # 給予角色
            await member.add_roles(role)
            
            # 記錄到數據庫
            success = self._save_role_purchase(
                user_id=user.id,
                guild_id=guild.id,
                role_id=role.id,
                role_name=role.name,
                duration_seconds=duration_seconds
            )
            
            if success:
                log_msg = (
                    f"✅ 成功給予 {user.mention} "
                    f"身分 **{role.name}**\n"
                    f"⏱️ 持續時間：{duration_days} 天\n"
                    f"📅 到期時間：{expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                log_msg = (
                    f"⚠️ 已給予 {user.mention} 身分 **{role.name}**，"
                    f"但記錄到期時間失敗！\n"
                    f"請稍後手動檢查"
                )
            
            await interaction.followup.send(log_msg, ephemeral=True)
            
            # 記錄到文件
            self._log_action(
                f"GRANT_TEMP_ROLE",
                f"User: {user.id}, Role: {role.id}, "
                f"Duration: {duration_days}d, Expires: {expires_at.isoformat()}"
            )
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ 操作失敗：{str(e)[:100]}",
                ephemeral=True
            )
    
    @app_commands.command(
        name="check_my_roles",
        description="查看你的臨時身分有效期"
    )
    async def check_my_roles(self, interaction: discord.Interaction):
        """查看用戶自己的臨時身分"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_roles = self._get_user_roles(
                interaction.user.id,
                interaction.guild.id
            )
            
            if not user_roles:
                await interaction.followup.send(
                    "你沒有任何臨時身分",
                    ephemeral=True
                )
                return
            
            current_time = datetime.now()
            embed = discord.Embed(
                title="⏱️ 你的臨時身分",
                color=discord.Color.blue()
            )
            
            for role_id, role_name, expires_at_str in user_roles:
                expires_at = datetime.fromisoformat(expires_at_str)
                remaining = expires_at - current_time
                
                if remaining.total_seconds() <= 0:
                    status = "⚠️ 已過期"
                    days = 0
                else:
                    days = remaining.days
                    hours = remaining.seconds // 3600
                    status = f"⏰ 剩餘 {days}d {hours}h"
                
                embed.add_field(
                    name=f"🎭 {role_name}",
                    value=f"{status}\n到期：{expires_at.strftime('%Y-%m-%d %H:%M')}",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ 查詢失敗：{str(e)}",
                ephemeral=True
            )
    
    # ========== 內部方法 ==========
    
    def _save_role_purchase(
        self,
        user_id: int,
        guild_id: int,
        role_id: int,
        role_name: str,
        duration_seconds: int
    ) -> bool:
        """保存角色購買記錄"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            expires_at = datetime.now() + timedelta(seconds=duration_seconds)
            
            cursor.execute("""
                INSERT OR REPLACE INTO role_expirations 
                (user_id, guild_id, role_id, role_name, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (user_id, guild_id, role_id, role_name, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            self._log_action(
                "SAVE_PURCHASE",
                f"User: {user_id}, Role: {role_name}, Expires: {expires_at.isoformat()}"
            )
            
            return True
            
        except Exception as e:
            self._log_action(
                "SAVE_PURCHASE_ERROR",
                f"User: {user_id}, Role: {role_name}, Error: {str(e)}"
            )
            return False
    
    def _get_user_roles(
        self,
        user_id: int,
        guild_id: int
    ) -> list:
        """獲取用戶的臨時身分"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT role_id, role_name, expires_at
                FROM role_expirations
                WHERE user_id = ? AND guild_id = ? AND is_active = 1
                ORDER BY expires_at DESC
            """, (user_id, guild_id))
            
            results = cursor.fetchall()
            conn.close()
            
            return results
            
        except Exception as e:
            self._log_action("GET_USER_ROLES_ERROR", str(e))
            return []
    
    def _log_action(self, action: str, details: str):
        """記錄操作到日誌和標準輸出"""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = f"[{timestamp}] [{action}] {details}"
            
            # 記錄到文件
            with open("/tmp/role_expiration.log", "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")
                f.flush()
            
            # 同時打印到控制台
            print(f"[RoleManager] {log_entry}")
            
        except Exception as e:
            print(f"[RoleManager] ❌ 日誌記錄失敗: {e}")


async def setup(bot: commands.Bot):
    """加載此 Cog"""
    await bot.add_cog(EnhancedRoleExpirationManager(bot))
    print("[RoleExpiration] Enhanced Cog loaded")
