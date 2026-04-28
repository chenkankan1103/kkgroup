# -*- coding: utf-8 -*-
"""
UIBot 管理員指令 - 置物櫃批量操作
"""

import discord
from discord.ext import commands
from discord import app_commands
from db_adapter import get_all_users, get_user
from cogs.ui.utils.locker_embed_generator import update_locker_message
import asyncio
import logging

logger = logging.getLogger(__name__)

class AdminLockerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="admin_refresh_all_lockers",
        description="🔄 [管理員] 批量刷新所有用戶的置物櫃（包含紙娃娃）"
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_refresh_all_lockers(self, interaction: discord.Interaction):
        """
        刷新所有用戶的置物櫃
        
        效果：
        - 更新所有用戶的置物櫃訊息
        - 重新渲染紙娃娃圖片
        - 更新置物櫃統計數據
        
        耗時：大約 10 秒（取決於用戶數量）
        """
        await interaction.response.defer()
        
        try:
            # 取得所有用戶
            all_users = get_all_users()
            total = len(all_users)
            
            logger.info(f"🔄 【批量刷新指令】開始刷新 {total} 個用戶的置物櫃")
            
            # 發送進度訊息
            progress_msg = await interaction.followup.send(
                f"🔄 開始批量刷新所有置物櫃...\n"
                f"📊 總用戶數：{total}\n"
                f"⏱️ 預計耗時：{max(5, total // 20)} 秒\n\n"
                f"正在處理中... 0/{total}"
            )
            
            success_count = 0
            fail_count = 0
            
            # 取得 UserPanel cog（在 uibody.py）
            user_panel_cog = self.bot.get_cog("UserPanel")
            if not user_panel_cog:
                logger.error("❌ 找不到 UserPanel cog")
                await interaction.followup.send("❌ 找不到 UserPanel cog，無法刷新")
                return
            
            # 遍歷所有用戶，更新置物櫃
            for i, user_data in enumerate(all_users):
                try:
                    user_id = user_data.get('user_id')
                    if not user_id:
                        fail_count += 1
                        continue
                    
                    # 檢查用戶是否已有置物櫃線程
                    thread_id = user_data.get('thread_id', 0)
                    
                    if thread_id:
                        # === 路徑 A：用戶已有置物櫃，直接更新 ===
                        try:
                            # 獲取 thread 物件
                            forum_channel = self.bot.get_channel(user_panel_cog.FORUM_CHANNEL_ID)
                            if not forum_channel:
                                fail_count += 1
                                logger.warning(f"⚠️ 無法獲取論壇頻道")
                                continue
                            
                            # 先從快取取得
                            thread = forum_channel.get_thread(thread_id)
                            
                            # 如果快取無效，嘗試從 API 獲取
                            if not thread:
                                try:
                                    thread = await self.bot.fetch_channel(thread_id)
                                except discord.NotFound:
                                    thread = None
                                except Exception:
                                    thread = None
                            
                            # 如果 thread 存在，更新其中的置物櫃訊息
                            if thread:
                                locker_message_id = user_data.get('locker_message_id')
                                message_obj = None
                                
                                # 如果有存儲的訊息 ID，嘗試獲取訊息物件
                                if locker_message_id:
                                    try:
                                        message_obj = await thread.fetch_message(locker_message_id)
                                    except discord.NotFound:
                                        message_obj = None
                                    except Exception:
                                        message_obj = None
                                
                                # 調用 update_locker_message 更新
                                success = await update_locker_message(
                                    thread=thread,
                                    user_id=user_id,
                                    message_obj=message_obj,
                                    bot=self.bot,
                                    cog=user_panel_cog
                                )
                                
                                if success:
                                    success_count += 1
                                    logger.debug(f"✅ 已更新用戶 {user_id} 的置物櫃（更新現有訊息）")
                                else:
                                    fail_count += 1
                                    logger.warning(f"⚠️ 用戶 {user_id} 的置物櫃更新失敗")
                            else:
                                # thread 不存在，將 thread_id 重設為 0，轉為路徑 B（創建新的）
                                from db_adapter import set_user_field
                                set_user_field(user_id, 'thread_id', 0)
                                fail_count += 1
                                logger.warning(f"⚠️ 用戶 {user_id} 的 thread 無效，已重設")
                        
                        except Exception as e:
                            fail_count += 1
                            logger.warning(f"⚠️ 更新用戶 {user_id} 失敗: {e}")
                    
                    else:
                        # === 路徑 B：用戶無置物櫃，創建新的 ===
                        try:
                            user = await self.bot.fetch_user(int(user_id))
                            if user:
                                # 呼叫 get_or_create_user_thread 創建新的
                                thread = await user_panel_cog.get_or_create_user_thread(user)
                                if thread:
                                    success_count += 1
                                    logger.debug(f"✅ 已為用戶 {user_id} 創建新置物櫃")
                                else:
                                    fail_count += 1
                                    logger.warning(f"⚠️ 用戶 {user_id} 的置物櫃建立失敗（無法建立）")
                            else:
                                fail_count += 1
                        except discord.NotFound:
                            fail_count += 1
                            logger.warning(f"⚠️ 用戶 {user_id} 不存在")
                        except Exception as user_err:
                            fail_count += 1
                            logger.warning(f"⚠️ 建立用戶 {user_id} 置物櫃失敗: {user_err}")
                    
                    # 每 5 個更新一次進度顯示
                    if (i + 1) % 5 == 0 or i == total - 1:
                        progress_text = (
                            f"🔄 批量刷新進度\n\n"
                            f"📊 進度：{i + 1}/{total} ({(i + 1) / total * 100:.0f}%)\n"
                            f"✅ 成功：{success_count}\n"
                            f"❌ 失敗：{fail_count}\n\n"
                            f"處理中..."
                        )
                        try:
                            await progress_msg.edit(content=progress_text)
                        except:
                            pass
                    
                    # 避免 Discord API 頻率限制
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    fail_count += 1
                    logger.error(f"❌ 處理用戶 {user_data.get('user_id')} 時出錯: {e}")
            
            # 完成訊息
            success_rate = (success_count / total * 100) if total > 0 else 0
            embed = discord.Embed(
                title="✅ 批量刷新置物櫃完成！",
                description=(
                    f"🔄 已完成所有用戶置物櫃更新\n\n"
                    f"✅ 成功：**{success_count}** 個\n"
                    f"❌ 失敗：**{fail_count}** 個\n"
                    f"📊 成功率：**{success_rate:.1f}%**\n\n"
                    f"⏱️ 執行時間：立即完成"
                ),
                color=0x00ff00
            )
            embed.set_footer(text=f"執行者：{interaction.user.name} | 時間：{discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            await progress_msg.delete()
            await interaction.followup.send(embed=embed)
            
            logger.info(f"✅ 【批量刷新指令】完成：{success_count}/{total} 成功")
            
        except Exception as e:
            logger.error(f"❌ 批量刷新指令異常: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:200]}")

async def setup(bot):
    """載入此 Cog"""
    await bot.add_cog(AdminLockerCommands(bot))
    print("✅ 已加載 AdminLockerCommands cog")
