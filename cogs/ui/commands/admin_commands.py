import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from db_adapter import get_all_users, set_user_field

from ..utils.locker_embed_generator import (message_needs_update,
                                            update_locker_message)


class AdminCommands(commands.Cog):
    """管理員命令 Cog"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="update_forum_lockers",
        description="手動更新論壇中所有活躍用戶的置物櫃embed",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def update_forum_lockers(self, interaction: discord.Interaction):
        """管理員命令：手動更新論壇中所有活躍用戶的置物櫃embed"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 獲取UI Cog
            user_panel_cog = self.bot.get_cog("UserPanel")
            if not user_panel_cog:
                await interaction.followup.send(
                    "❌ UserPanel Cog 未載入", ephemeral=True
                )
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
                last = u.get("last_activity") or 0
                # 負值次級排序以便裝備多的靠後更新
                equip_count = sum(1 for i in range(20) if u.get(f"equip_{i}", 0))
                return (last, -equip_count)

            all_users.sort(key=_activity_key)
            updated_count = 0
            failed_count = 0

            await interaction.followup.send(
                f"🔄 開始更新 {len(all_users)} 個用戶的置物櫃...", ephemeral=True
            )

            for user_data in all_users:
                user_id = user_data.get("user_id")
                thread_id = user_data.get("thread_id")
                locker_message_id = user_data.get("locker_message_id")

                if not user_id or not thread_id:
                    continue

                try:
                    # use bot.fetch_channel/get_channel for compatibility
                    thread = self.bot.get_channel(
                        thread_id
                    ) or await self.bot.fetch_channel(thread_id)
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, "thread_id", None)
                        set_user_field(user_id, "locker_message_id", None)
                        continue
                    if getattr(thread, "archived", False):
                        continue

                    message = None
                    if locker_message_id:
                        try:
                            message = await thread.fetch_message(locker_message_id)
                        except discord.NotFound:
                            set_user_field(user_id, "locker_message_id", None)
                        except Exception:
                            message = None

                    # Safety check: only update messages that are non-canonical to avoid
                    # regressing fixes (missing image or legacy buttons).
                    if message:

                        def _has_gender_button(msg):
                            try:
                                for row in msg.components or []:
                                    for comp in row.children:
                                        cid = getattr(
                                            comp, "custom_id", None
                                        ) or comp.get("custom_id")
                                        if cid == "locker_change_gender":
                                            return True
                            except Exception:
                                pass
                            return False

                        if not message_needs_update(message) and _has_gender_button(
                            message
                        ):
                            continue

                    success = await update_locker_message(
                        thread=thread,
                        user_id=user_id,
                        message_obj=message,
                        bot=self.bot,
                        cog=user_panel_cog,
                    )

                    if not success:
                        failed_count += 1
                        continue

                    updated_count += 1
                except Exception as e:
                    print(f"⚠️ 更新用戶 {user_id} 的embed失敗: {e}")
                    failed_count += 1
                    continue

                await asyncio.sleep(1)

            await interaction.followup.send(
                f"✅ 更新完成！成功更新 {updated_count} 個置物櫃，失敗 {failed_count} 個",
                ephemeral=True,
            )

        except Exception as e:
            await interaction.followup.send(f"❌ 更新失敗: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
