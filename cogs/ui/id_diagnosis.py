#!/usr/bin/env python3
"""
Discord ID 偏差診斷與修復工具
利用 Discord 機器人 API 檢驗 user_data.db 中的 user_id 是否與實際 Discord 成員 ID 一致
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from typing import Optional, Dict, List, Tuple
import os

GUILD_ID = 1133112693356773416
DB_PATH = './user_data.db'

class IDDiagnosisCog(commands.Cog):
    """ID 偏差診斷 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.issues = []
    
    @app_commands.command(
        name="check_user_ids",
        description="🔍 檢驗資料庫中的 user_id 是否與 Discord 成員 ID 相符"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_user_ids(self, interaction: discord.Interaction):
        """診斷 ID 偏差"""
        await interaction.response.defer(thinking=True)
        
        try:
            guild = interaction.guild
            if not guild:
                await interaction.followup.send("❌ 無法取得伺服器信息", ephemeral=True)
                return
            
            # 連接資料庫
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 獲取資料庫中的所有用戶
            cursor.execute("SELECT user_id, nickname FROM users")
            db_users = {row[0]: row[1] for row in cursor.fetchall()}
            
            issues = []
            missing_members = []
            
            # 檢查每個資料庫用戶是否在 Discord 中存在
            print(f"🔍 檢查 {len(db_users)} 個資料庫用戶...")
            
            for db_user_id, db_nickname in db_users.items():
                try:
                    # 嘗試從 Discord 取得成員
                    member = await guild.fetch_member(db_user_id)
                    
                    # 檢查昵稱是否匹配
                    discord_name = member.nick or member.name
                    
                    if db_nickname and db_nickname != discord_name:
                        issues.append({
                            'type': '昵稱不符',
                            'user_id': db_user_id,
                            'db_nickname': db_nickname,
                            'discord_name': discord_name,
                            'member': member
                        })
                
                except discord.NotFound:
                    # 用戶不在 Discord 中
                    missing_members.append({
                        'user_id': db_user_id,
                        'db_nickname': db_nickname
                    })
                except Exception as e:
                    print(f"❌ 檢查 user_id={db_user_id} 時出錯: {e}")
            
            # 檢查 Discord 中的成員是否在資料庫中
            print(f"🔄 檢查 Discord 成員...")
            dc_user_ids = set()
            async for member in guild.fetch_members(limit=None):
                if member.bot:
                    continue
                dc_user_ids.add(member.id)
                
                if member.id not in db_users:
                    issues.append({
                        'type': '缺失用戶',
                        'user_id': member.id,
                        'discord_name': member.nick or member.name,
                        'member': member
                    })
            
            # 生成報告
            report = f"**ID 偏差診斷報告**\n\n"
            report += f"📊 統計:\n"
            report += f"  資料庫用戶: {len(db_users)}\n"
            report += f"  Discord 成員: {len(dc_user_ids)}\n"
            report += f"  ⚠️ 發現問題: {len(issues)}\n"
            report += f"  ❌ 缺失成員: {len(missing_members)}\n\n"
            
            if issues:
                report += "**問題詳情:**\n"
                for i, issue in enumerate(issues[:10], 1):  # 只顯示前 10 個
                    report += f"\n{i}. {issue['type']}\n"
                    report += f"   User ID: `{issue['user_id']}`\n"
                    if issue['type'] == '昵稱不符':
                        report += f"   資料庫: `{issue['db_nickname']}`\n"
                        report += f"   Discord: `{issue['discord_name']}`\n"
                    elif issue['type'] == '缺失用戶':
                        report += f"   Discord 名稱: `{issue.get('discord_name', 'N/A')}`\n"
                
                if len(issues) > 10:
                    report += f"\n... 還有 {len(issues) - 10} 個問題"
            
            if missing_members:
                report += f"\n\n**缺失的 Discord 成員:**\n"
                for item in missing_members[:5]:
                    report += f"- User ID: `{item['user_id']}` (昵稱: {item['db_nickname']})\n"
                if len(missing_members) > 5:
                    report += f"... 還有 {len(missing_members) - 5} 個\n"
            
            conn.close()
            
            # 發送報告
            if len(report) > 2000:
                # 分段發送
                chunks = [report[i:i+2000] for i in range(0, len(report), 2000)]
                for chunk in chunks:
                    await interaction.followup.send(chunk, ephemeral=True)
            else:
                await interaction.followup.send(report, ephemeral=True)
        
        except Exception as e:
            print(f"❌ 診斷失敗: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 診斷失敗: {str(e)}", ephemeral=True)
    
    @app_commands.command(
        name="list_id_issues",
        description="📋 列出所有 ID 偏差的用戶"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def list_id_issues(self, interaction: discord.Interaction):
        """列出 ID 問題列表"""
        await interaction.response.defer(thinking=True)
        
        try:
            guild = interaction.guild
            
            # 連接資料庫
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 獲取所有用戶
            cursor.execute("SELECT user_id, nickname FROM users ORDER BY nickname")
            db_users = cursor.fetchall()
            
            problem_list = []
            
            for db_user_id, db_nickname in db_users:
                try:
                    member = await guild.fetch_member(db_user_id)
                    discord_name = member.nick or member.name
                    
                    if db_nickname and db_nickname != discord_name:
                        problem_list.append((db_user_id, db_nickname, discord_name))
                except:
                    pass
            
            conn.close()
            
            # 列出問題
            if not problem_list:
                await interaction.followup.send("✅ 沒有發現 ID 偏差問題", ephemeral=True)
                return
            
            # 分頁顯示
            report = f"**ID 偏差清單** (共 {len(problem_list)} 個)\n\n"
            
            for i, (uid, db_nick, dc_nick) in enumerate(problem_list, 1):
                report += f"{i}. **{db_nick}**\n"
                report += f"   User ID: `{uid}`\n"
                report += f"   Discord 名稱: `{dc_nick}`\n\n"
                
                if len(report) > 1800:
                    await interaction.followup.send(report, ephemeral=True)
                    report = ""
            
            if report:
                await interaction.followup.send(report, ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"❌ 錯誤: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IDDiagnosisCog(bot))
