# -*- coding: utf-8 -*-
"""
UI 模組管理員命令
==========================================
置物櫃紙娃娃相關的管理員命令

指令：
- /admin_refresh_all_paperdolls - 刷新所有置物櫃紙娃娃（UIBot）
"""

import discord
from discord.ext import commands
from discord import app_commands
from db_adapter import get_all_users
from cogs.ui.utils import paperdoll_manager


class UIAdminCommands(commands.Cog):
    """【UI 模組】管理員命令
    
    負責置物櫃、紙娃娃等 UI 相關的管理功能。
    只在 UIBot 中載入。
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="admin_refresh_all_paperdolls",
        description="[UIBot 管理員] 刷新所有置物櫃的紙娃娃圖片 - 驗證 URL 生成狀態"
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_refresh_all_paperdolls(self, interaction: discord.Interaction):
        """
        批量刷新所有用戶的紙娃娃 URL 生成
        
        功能：
        - 驗證所有 254 個用戶的紙娃娃數據完整性
        - 測試 paperdoll_manager 的 API URL 生成
        - 統計 is_stunned 狀態的用戶
        - 顯示詳細的成功/失敗報告
        
        用途：
        - 系統健康檢查
        - 數據驗證
        - 排除紙娃娃顯示問題
        """
        await interaction.response.defer(ephemeral=True)
        
        try:
            users = get_all_users()
            total = len(users)
            success = 0
            failed = 0
            stunned = 0
            
            await interaction.followup.send(f"🔄 開始驗證 {total} 個用戶的紙娃娃 URL...", ephemeral=True)
            
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
                f"✅ 紙娃娃 URL 驗證完成！\n\n"
                f"📊 驗證結果:\n"
                f"  - 總用戶: {total}\n"
                f"  - URL 生成成功: {success}\n"
                f"  - URL 生成失敗: {failed}\n"
                f"  - 其中暈倒狀態 (is_stunned=1): {stunned}\n\n"
                f"💡 說明:\n"
                f"  此命令只驗證 URL 生成，不影響置物櫃顯示。\n"
                f"  用戶需要按置物櫃中的「🔄 更新面板」按鈕才能看到紙娃娃圖片。"
            )
            
            await interaction.followup.send(result_msg, ephemeral=True)
            
        except Exception as e:
            import traceback
            print(f"❌ 驗證失敗: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(f"❌ 驗證失敗: {e}", ephemeral=True)


async def setup(bot):
    """設置 Cog - 負責載入此命令模組"""
    await bot.add_cog(UIAdminCommands(bot))
