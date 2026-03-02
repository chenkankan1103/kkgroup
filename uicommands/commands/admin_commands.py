import discord
import asyncio
import datetime
from discord.ext import commands
from discord import app_commands
from db_adapter import get_all_users, set_user_field
from uicommands.views import LockerPanelView


class AdminCommands(commands.Cog):
    """管理員命令 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="update_forum_lockers", description="手動更新論壇中所有活躍用戶的置物櫃embed")
    @app_commands.checks.has_permissions(administrator=True)
    async def update_forum_lockers(self, interaction: discord.Interaction):
        """管理員命令：手動更新論壇中所有活躍用戶的置物櫃embed"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 獲取UI Cog
            user_panel_cog = self.bot.get_cog('UserPanel')
            if not user_panel_cog:
                await interaction.followup.send("❌ UserPanel Cog 未載入", ephemeral=True)
                return
            
            forum_channel = self.bot.get_channel(user_panel_cog.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                await interaction.followup.send("❌ 找不到論壇頻道", ephemeral=True)
                return
            
            all_users = get_all_users()
            # 活動較低的用戶先處理，保證活動較高的用戶在最後被更新，
            # 這樣它們的線程會因為新的消息而被提升至論壇頂端。
            # 活躍度用 last_activity 欄位（時間戳）。
            # 若同樣活躍，仍然優先處理有非預設紙娃娃的用戶。
            def _activity_key(u):
                last = u.get('last_activity') or 0
                # 負值次級排序以便裝備多的靠後更新
                equip_count = sum(1 for i in range(20) if u.get(f'equip_{i}', 0))
                return (last, -equip_count)

            all_users.sort(key=_activity_key)
            updated_count = 0
            failed_count = 0
            
            await interaction.followup.send(f"🔄 開始更新 {len(all_users)} 個用戶的置物櫃...", ephemeral=True)
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id')
                locker_message_id = user_data.get('locker_message_id')

                if not user_id or not thread_id or not locker_message_id:
                    continue

                try:
                    # use bot.fetch_channel/get_channel for compatibility
                    thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    if getattr(thread, 'archived', False):
                        continue

                    message = await thread.fetch_message(locker_message_id)
                    if not message:
                        continue

                    # Safety check: only update messages that are non-canonical to avoid
                    # regressing fixes (missing image or legacy buttons).
                    try:
                        from uicommands.utils.locker_embed_generator import message_needs_update
                        if not message_needs_update(message):
                            # message is canonical — but still ensure the new `locker_change_gender`
                            # button exists. If present, skip; otherwise fall through to update.
                            def _has_gender_button(msg):
                                try:
                                    for row in msg.components or []:
                                        for comp in row.children:
                                            cid = getattr(comp, 'custom_id', None) or comp.get('custom_id')
                                            if cid == 'locker_change_gender':
                                                return True
                                except Exception:
                                    pass
                                return False

                            if _has_gender_button(message):
                                continue
                            # else: proceed to update so the missing button will be added
                    except Exception:
                        # fallback to existing checks if helper not available
                        current_embed = None
                        try:
                            current_embed = message.embeds[0] if message.embeds else None
                        except Exception:
                            current_embed = None

                        current_image = None
                        current_footer = ''
                        try:
                            if current_embed and getattr(current_embed, 'image', None):
                                current_image = getattr(current_embed.image, 'url', None)
                            if current_embed and getattr(current_embed, 'footer', None):
                                current_footer = (getattr(current_embed.footer, 'text', '') or '')
                        except Exception:
                            current_image = None
                            current_footer = ''

                        def has_legacy_button(msg):
                            try:
                                for row in msg.components or []:
                                    for comp in row.children:
                                        cid = getattr(comp, 'custom_id', None) or comp.get('custom_id')
                                        if cid == 'locker_crop_info':
                                            return True
                            except Exception:
                                pass
                            return False

                        needs_update = False
                        if not current_image:
                            needs_update = True
                        elif 'MapleStory' not in (current_footer or ''):
                            needs_update = True
                        elif has_legacy_button(message):
                            needs_update = True

                        # if message looks canonical but lacks our new button, force an update
                        def _has_gender_button(msg):
                            try:
                                for row in msg.components or []:
                                    for comp in row.children:
                                        cid = getattr(comp, 'custom_id', None) or comp.get('custom_id')
                                        if cid == 'locker_change_gender':
                                            return True
                            except Exception:
                                pass
                            return False

                        if not needs_update and _has_gender_button(message):
                            continue
                        if not needs_update and not _has_gender_button(message):
                            needs_update = True

                        if not needs_update:
                            continue

                    # Build canonical embed (create_user_embed already applies MapleStory fallback)
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    embed = await user_panel_cog.create_user_embed(user_data, user)

                    # Ensure embed has an image (defensive) — compute MapleStory fallback if necessary
                    try:
                        img_url = (embed.image.url if getattr(embed, 'image', None) else None)
                    except Exception:
                        img_url = None
                    if not img_url:
                        try:
                            from uicommands.utils.image_utils import build_maplestory_api_url
                            api_url = build_maplestory_api_url(user_data, animated=True)
                            embed.set_image(url=api_url)
                        except Exception:
                            pass

                    view = LockerPanelView(user_panel_cog, user_id, thread)

                    await message.edit(embed=embed, view=view)
                    updated_count += 1
                    # 發送短暫消息來提升線程排序（會在 1 秒後自動刪除）
                    try:
                        await thread.send(content="🔼 活躍用戶更新", delete_after=1)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"⚠️ 更新用戶 {user_id} 的embed失敗: {e}")
                    failed_count += 1
                    continue

                await asyncio.sleep(1)
            
            await interaction.followup.send(
                f"✅ 更新完成！成功更新 {updated_count} 個置物櫃，失敗 {failed_count} 個", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ 更新失敗: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
