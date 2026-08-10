"""
置物櫃管理員命令 - 檢查和初始化會員置物櫃

功能：
1. /locker_check <user> - 檢查特定會員是否有置物櫃
2. /locker_init <user> - 為會員初始化置物櫃
3. /locker_check_all - 檢查所有會員的置物櫃狀況
4. /locker_fix_missing - 批量為沒有置物櫃的會員初始化
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db_adapter import get_all_users, set_user_field, get_user
import json
import os


class LockerAdminCog(commands.Cog):
    """置物櫃管理員命令"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="locker_check", description="檢查特定會員是否有置物櫃")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="要檢查的會員")
    async def locker_check(self, interaction: discord.Interaction, user: discord.User):
        """檢查會員是否有置物櫃（是否有植物記錄）"""
        await interaction.response.defer(ephemeral=True)

        try:
            user_data = get_user(user.id)

            if not user_data:
                await interaction.followup.send(
                    f"❌ 找不到會員 {user.mention} 的資料", ephemeral=True
                )
                return

            # 檢查置物櫃字段
            plants_json = user_data.get("cannabis_plants", "[]")
            inventory_json = user_data.get("cannabis_inventory", "{}")

            # 解析 JSON
            try:
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []

                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = (
                        inventory_json if isinstance(inventory_json, dict) else {}
                    )
            except json.JSONDecodeError:
                plants = []
                inventory = {}

            # 檢查結果
            has_plants = len(plants) > 0
            has_inventory = len(inventory) > 0
            has_locker = has_plants or has_inventory

            embed = discord.Embed(
                title=f"📦 {user.display_name} 的置物櫃狀況",
                color=discord.Color.green() if has_locker else discord.Color.red(),
            )

            embed.add_field(
                name="置物櫃狀態",
                value="✅ 已初始化" if has_locker else "❌ 未初始化",
                inline=False,
            )

            embed.add_field(
                name="🌱 植物",
                value=f"{len(plants)} 株" if has_plants else "無植物",
                inline=True,
            )

            embed.add_field(
                name="📦 庫存",
                value=f"{len(inventory)} 種類別" if has_inventory else "無庫存",
                inline=True,
            )

            if has_plants:
                plant_info = []
                for plant in plants[:5]:  # 最多顯示5株
                    plant_info.append(
                        f"• {plant.get('seed_type', '未知')} "
                        f"({plant.get('status', '未知')})"
                    )
                if len(plants) > 5:
                    plant_info.append(f"... 還有 {len(plants) - 5} 株")
                embed.add_field(
                    name="植物清單", value="\n".join(plant_info), inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ 檢查失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="locker_init", description="為會員初始化置物櫃並建立 thread"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="要初始化的會員")
    async def locker_init(self, interaction: discord.Interaction, user: discord.User):
        """為沒有置物櫃的會員初始化，並自動建立 thread 和置物櫃頁面"""
        await interaction.response.defer(ephemeral=True)

        try:
            user_data = get_user(user.id)

            if not user_data:
                await interaction.followup.send(
                    f"❌ 找不到會員 {user.mention} 的資料\n"
                    f"提示：會員可能尚未註冊系統",
                    ephemeral=True,
                )
                return

            # 檢查是否已有置物櫃
            plants_json = user_data.get("cannabis_plants", "[]")
            inventory_json = user_data.get("cannabis_inventory", "{}")

            try:
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []

                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = (
                        inventory_json if isinstance(inventory_json, dict) else {}
                    )
            except json.JSONDecodeError:
                plants = []
                inventory = {}

            has_locker = len(plants) > 0 or len(inventory) > 0

            if has_locker:
                await interaction.followup.send(
                    f"⚠️ {user.mention} 已經有置物櫃了\n"
                    f"• 植物: {len(plants)} 株\n"
                    f"• 庫存: {len(inventory)} 種",
                    ephemeral=True,
                )
                return

            # 初始化置物櫃
            success = True
            success &= set_user_field(user.id, "cannabis_plants", "[]")
            success &= set_user_field(user.id, "cannabis_inventory", "{}")

            if not success:
                await interaction.followup.send(
                    "❌ 初始化失敗，請檢查資料庫連接", ephemeral=True
                )
                return

            # 建立 thread 並發送置物櫃頁面
            try:
                # 從環境變數讀取宿舍論壇頻道（置物櫃 thread 頻道）
                forum_channel_id = os.getenv("FORUM_CHANNEL_ID")
                if not forum_channel_id:
                    await interaction.followup.send(
                        "❌ 環境變數未設定 FORUM_CHANNEL_ID，無法建立 thread",
                        ephemeral=True,
                    )
                    return

                target_channel = interaction.guild.get_channel(int(forum_channel_id))
                if not isinstance(
                    target_channel, (discord.TextChannel, discord.ForumChannel)
                ):
                    await interaction.followup.send(
                        "❌ 頻道選擇錯誤，必須是文字頻道或論壇頻道", ephemeral=True
                    )
                    return

                # 建立 thread（根據頻道類型選擇參數）
                if isinstance(target_channel, discord.ForumChannel):
                    # 論壇頻道：建立公開 thread（論壇頻道上的 thread 無法指定為私人）
                    thread = await target_channel.create_thread(
                        name=f"📦-{user.display_name}-置物櫃"
                    )
                else:
                    # 文字頻道：建立私人 thread
                    thread = await target_channel.create_thread(
                        name=f"📦-{user.display_name}-置物櫃",
                        type=discord.ChannelType.private_thread,
                    )

                # 發送 canonical 置物櫃訊息
                from cogs.ui.utils.locker_embed_generator import update_locker_message
                from cogs.shop.merchant.cannabis_farming import (
                    get_user_plants,
                    get_inventory,
                )

                plants = await get_user_plants(user.id)
                inventory = await get_inventory(user.id)

                success = await update_locker_message(
                    thread=thread,
                    user_id=user.id,
                    bot=self.bot,
                    cog=self.bot.get_cog("UserPanel"),
                    plants=plants,
                    inventory=inventory,
                )
                if not success:
                    raise RuntimeError("無法建立 canonical 置物櫃訊息")

                await interaction.followup.send(
                    f"✅ 已為 {user.mention} 初始化置物櫃\n"
                    f"📍 thread: {thread.mention}\n"
                    f"現在可以開始種植和管理物品了！",
                    ephemeral=True,
                )
            except Exception as thread_err:
                # 即使 thread 建立失敗，置物櫃數據已初始化
                await interaction.followup.send(
                    f"✅ 已初始化置物櫃 (資料庫)\n"
                    f"⚠️ 但建立 thread 失敗: {thread_err}\n"
                    f"請手動為使用者建立 thread",
                    ephemeral=True,
                )

        except Exception as e:
            await interaction.followup.send(f"❌ 初始化失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="locker_check_all", description="檢查所有會員的置物櫃狀況（統計）"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def locker_check_all(self, interaction: discord.Interaction):
        """統計所有會員的置物櫃初始化狀況"""
        await interaction.response.defer(ephemeral=True)

        try:
            all_users = get_all_users()

            has_locker_count = 0
            no_locker_count = 0
            no_locker_users = []

            for user_data in all_users:
                user_id = user_data.get("user_id")
                plants_json = user_data.get("cannabis_plants", "[]")
                inventory_json = user_data.get("cannabis_inventory", "{}")

                try:
                    if isinstance(plants_json, str):
                        plants = json.loads(plants_json) if plants_json else []
                    else:
                        plants = plants_json if isinstance(plants_json, list) else []

                    if isinstance(inventory_json, str):
                        inventory = json.loads(inventory_json) if inventory_json else {}
                    else:
                        inventory = (
                            inventory_json if isinstance(inventory_json, dict) else {}
                        )
                except json.JSONDecodeError:
                    plants = []
                    inventory = {}

                has_locker = len(plants) > 0 or len(inventory) > 0

                if has_locker:
                    has_locker_count += 1
                else:
                    no_locker_count += 1
                    no_locker_users.append(user_id)

            # 生成報告
            embed = discord.Embed(
                title="📦 置物櫃統計報告",
                color=discord.Color.blue(),
                timestamp=datetime.now(),
            )

            embed.add_field(
                name="✅ 已初始化", value=f"{has_locker_count} 個會員", inline=True
            )

            embed.add_field(
                name="❌ 未初始化", value=f"{no_locker_count} 個會員", inline=True
            )

            if no_locker_count > 0:
                embed.add_field(
                    name="⚠️ 缺少置物櫃的會員 ID",
                    value=", ".join(map(str, no_locker_users[:20]))
                    + (
                        f"\n... 及其他 {no_locker_count - 20} 個"
                        if no_locker_count > 20
                        else ""
                    ),
                    inline=False,
                )

            embed.set_footer(text=f"總會員數: {len(all_users)}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ 統計失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="locker_fix_missing",
        description="批量初始化所有缺少置物櫃的會員並建立 thread",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def locker_fix_missing(self, interaction: discord.Interaction):
        """批量為所有沒有置物櫃的會員初始化並建立 thread"""
        await interaction.response.defer(ephemeral=True)

        try:
            all_users = get_all_users()

            fixed_count = 0
            already_have_count = 0
            failed_count = 0
            thread_created_count = 0

            # 從環境變數讀取宿舍論壇頻道（置物櫃 thread 頻道）
            forum_channel_id = os.getenv("FORUM_CHANNEL_ID")
            if not forum_channel_id:
                await interaction.followup.send(
                    "❌ 環境變數未設定 FORUM_CHANNEL_ID，無法建立 thread",
                    ephemeral=True,
                )
                return

            target_channel = interaction.guild.get_channel(int(forum_channel_id))
            if not isinstance(
                target_channel, (discord.TextChannel, discord.ForumChannel)
            ):
                await interaction.followup.send(
                    "❌ 頻道選擇錯誤，必須是文字頻道或論壇頻道", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"🔄 開始批量初始化（共 {len(all_users)} 個會員）...", ephemeral=True
            )

            for user_data in all_users:
                user_id = user_data.get("user_id")
                plants_json = user_data.get("cannabis_plants", "[]")
                inventory_json = user_data.get("cannabis_inventory", "{}")

                try:
                    if isinstance(plants_json, str):
                        plants = json.loads(plants_json) if plants_json else []
                    else:
                        plants = plants_json if isinstance(plants_json, list) else []

                    if isinstance(inventory_json, str):
                        inventory = json.loads(inventory_json) if inventory_json else {}
                    else:
                        inventory = (
                            inventory_json if isinstance(inventory_json, dict) else {}
                        )
                except json.JSONDecodeError:
                    plants = []
                    inventory = {}

                has_locker = len(plants) > 0 or len(inventory) > 0

                if has_locker:
                    already_have_count += 1
                    continue

                # 初始化這個會員
                try:
                    success = True
                    success &= set_user_field(user_id, "cannabis_plants", "[]")
                    success &= set_user_field(user_id, "cannabis_inventory", "{}")

                    if not success:
                        failed_count += 1
                        continue

                    fixed_count += 1

                    # 嘗試建立 thread 並發送置物櫃
                    try:
                        user_obj = await self.bot.fetch_user(user_id)

                        # 建立 thread（根據頻道類律選擇參數）
                        if isinstance(target_channel, discord.ForumChannel):
                            # 論壇頻道：建立公開 thread（論壇頻道上的 thread 無法指定為私人）
                            thread = await target_channel.create_thread(
                                name=f"📦-{user_obj.display_name}-置物櫃"
                            )
                        else:
                            # 文字頻道：建立私人 thread
                            thread = await target_channel.create_thread(
                                name=f"💾-{user_obj.display_name}-置物櫃",
                                type=discord.ChannelType.private_thread,
                            )

                        # 發送 canonical 置物櫃訊息
                        from cogs.ui.utils.locker_embed_generator import (
                            update_locker_message,
                        )
                        from cogs.shop.merchant.cannabis_farming import (
                            get_user_plants,
                            get_inventory,
                        )

                        plants = await get_user_plants(user_id)
                        inventory = await get_inventory(user_id)

                        success = await update_locker_message(
                            thread=thread,
                            user_id=user_id,
                            bot=self.bot,
                            cog=self.bot.get_cog("UserPanel"),
                            plants=plants,
                            inventory=inventory,
                        )
                        if not success:
                            raise RuntimeError("無法建立 canonical 置物櫃訊息")

                        thread_created_count += 1

                    except Exception:
                        # thread 建立失敗但不影響計數
                        pass

                except Exception:
                    failed_count += 1

            # 生成報告
            embed = discord.Embed(
                title="✅ 置物櫃批量初始化完成",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )

            embed.add_field(
                name="🔧 已修復", value=f"{fixed_count} 個會員", inline=True
            )

            embed.add_field(
                name="📍 已建立 thread", value=f"{thread_created_count} 個", inline=True
            )

            embed.add_field(
                name="➡️ 已有置物櫃", value=f"{already_have_count} 個會員", inline=True
            )

            if failed_count > 0:
                embed.add_field(
                    name="❌ 修復失敗", value=f"{failed_count} 個會員", inline=True
                )

            embed.set_footer(
                text=f"總處理: {fixed_count + already_have_count + failed_count} 個會員"
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ 批量初始化失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="locker_remake_thread", description="手動為使用者重製置物櫃 thread"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def locker_remake_thread(
        self, interaction: discord.Interaction, user: discord.User
    ):
        """手動為使用者重製置物櫃 thread（參照置物櫃建立邏輯）"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 從環境變數讀取論壇頻道 ID
            forum_channel_id = os.getenv("FORUM_CHANNEL_ID")
            if not forum_channel_id:
                await interaction.followup.send(
                    "❌ 環境變數未設定 FORUM_CHANNEL_ID，無法建立 thread",
                    ephemeral=True,
                )
                return

            target_channel = interaction.guild.get_channel(int(forum_channel_id))
            if not isinstance(
                target_channel, (discord.TextChannel, discord.ForumChannel)
            ):
                await interaction.followup.send(
                    "❌ 頻道選擇錯誤，必須是文字頻道或論壇頻道", ephemeral=True
                )
                return

            # 建立 thread（根據頻道類型選擇參數）
            if isinstance(target_channel, discord.ForumChannel):
                thread = await target_channel.create_thread(
                    name=f"📦-{user.display_name}-置物櫃"
                )
            else:
                thread = await target_channel.create_thread(
                    name=f"📦-{user.display_name}-置物櫃",
                    type=discord.ChannelType.private_thread,
                )

            # 發送 canonical 置物櫃訊息
            from cogs.ui.utils.locker_embed_generator import update_locker_message
            from cogs.shop.merchant.cannabis_farming import (
                get_user_plants,
                get_inventory,
            )

            plants = await get_user_plants(user.id)
            inventory = await get_inventory(user.id)

            success = await update_locker_message(
                thread=thread,
                user_id=user.id,
                bot=self.bot,
                cog=self.bot.get_cog("UserPanel"),
                plants=plants,
                inventory=inventory,
            )
            if not success:
                raise RuntimeError("無法建立 canonical 置物櫃訊息")

            await interaction.followup.send(
                f"✅ 已為 {user.mention} 重製置物櫃 thread\n"
                f"📍 thread: {thread.mention}",
                ephemeral=True,
            )

        except Exception as e:
            await interaction.followup.send(f"❌ 重製置物櫃失敗: {e}", ephemeral=True)


async def setup(bot):
    """加載 Cog"""
    await bot.add_cog(LockerAdminCog(bot))
