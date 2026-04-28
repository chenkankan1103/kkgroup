#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量更新所有置物櫃紙娃娃的管理命令
使用: /admin_refresh_all_paperdolls
"""

import discord
from discord.ext import commands
from discord import app_commands
from db_adapter import get_all_users
from cogs.ui.utils import paperdoll_manager


class AdminPaperdollCommands(commands.Cog):
    """管理員 - 紙娃娃相關命令"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="admin_refresh_all_paperdolls",
        description="[管理員] 刷新所有置物櫃的紙娃娃圖片"
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_refresh_all_paperdolls(self, interaction: discord.Interaction):
        """批量刷新所有置物櫃的紙娃娃圖片"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            users = get_all_users()
            total = len(users)
            success = 0
            failed = 0
            stunned = 0
            
            await interaction.followup.send(f"🔄 開始刷新 {total} 個用戶的紙娃娃...", ephemeral=True)
            
            for u in users:
                try:
                    url = paperdoll_manager.build_api_url(u)
                    if url:
                        success += 1
                        if u.get('is_stunned') == 1:
                            stunned += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    print(f"❌ 用戶 {u.get('user_id')}: {e}")
            
            result_msg = (
                f"✅ 紙娃娃刷新完成！\n\n"
                f"📊 結果:\n"
                f"  - 成功: {success}\n"
                f"  - 失敗: {failed}\n"
                f"  - 其中暈倒狀態: {stunned}\n\n"
                f"💡 提醒: 用戶需要按置物櫃中的「更新面板」按鈕才能看到最新的紙娃娃圖片"
            )
            
            await interaction.followup.send(result_msg, ephemeral=True)
            
        except Exception as e:
            import traceback
            print(f"❌ 批量刷新失敗: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(f"❌ 刷新失敗: {e}", ephemeral=True)


async def setup(bot):
    """設置 Cog"""
    await bot.add_cog(AdminPaperdollCommands(bot))
