# -*- coding: utf-8 -*-
"""
置物櫃系統中 - 用戶角色配置命令
允許用戶自己設置楓之谷角色的各個部位
"""

import discord
from discord.ext import commands
from discord import app_commands
from db_adapter import get_user, set_user_field


class CharacterSetupCog(commands.Cog):
    """角色配置命令 - 用戶可以自定義楓之谷娃娃外觀"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="set_character",
        description="設置您的楓之谷娃娃外觀 (face, hair, skin, top, bottom, shoes)",
    )
    @app_commands.describe(
        face="臉型 ID (例: 20005)",
        hair="髮型 ID (例: 30120)",
        skin="膚色 ID (例: 12000)",
        top="上衣 ID (例: 1040014)",
        bottom="下身 ID (例: 1060096)",
        shoes="鞋子 ID (例: 1072005)",
    )
    async def set_character(
        self,
        interaction: discord.Interaction,
        face: int = None,
        hair: int = None,
        skin: int = None,
        top: int = None,
        bottom: int = None,
        shoes: int = None,
    ):
        """
        設置您的楓之谷娃娃外觀

        提示：可在線上楓之谷裝備網站查詢 ID
        """
        await interaction.response.defer(ephemeral=True)

        try:
            user_id = interaction.user.id
            updates = {}

            # 收集所有非 None 的更新
            if face is not None:
                updates["face"] = face
            if hair is not None:
                updates["hair"] = hair
            if skin is not None:
                updates["skin"] = skin
            if top is not None:
                updates["top"] = top
            if bottom is not None:
                updates["bottom"] = bottom
            if shoes is not None:
                updates["shoes"] = shoes

            if not updates:
                await interaction.followup.send(
                    "❌ 請至少指定一個部位！", ephemeral=True
                )
                return

            # 更新用戶數據
            for field, value in updates.items():
                set_user_field(user_id, field, value)

            embed = discord.Embed(
                title="✅ 角色外觀已更新",
                description="您的楓之谷娃娃已更新為新的外觀",
                color=discord.Color.green(),
            )

            # 列出更新的部位
            parts = {
                "face": "臉型",
                "hair": "髮型",
                "skin": "膚色",
                "top": "上衣",
                "bottom": "下身",
                "shoes": "鞋子",
            }

            update_text = "\n".join(
                [f"• {parts.get(k, k)}: {v}" for k, v in updates.items()]
            )
            embed.add_field(name="已更新的部位", value=update_text, inline=False)
            embed.set_footer(text="可用 /view_character 查看最新外觀")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ 更新失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="view_character", description="查看您或其他用戶的楓之谷娃娃外觀"
    )
    @app_commands.describe(user="要查看的用戶（留空則查看自己）")
    async def view_character(
        self, interaction: discord.Interaction, user: discord.User = None
    ):
        """查看楓之谷娃娃外觀"""
        await interaction.response.defer(ephemeral=True)

        try:
            target_user = user or interaction.user
            user_data = get_user(target_user.id)

            if not user_data:
                await interaction.followup.send(
                    f"❌ 找不到用戶 {target_user.mention} 的數據", ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"🧑 {target_user.display_name} 的娃娃外觀",
                color=discord.Color.blue(),
            )

            # 顯示所有角色部位
            parts = {
                "face": ("臉型", 20005),
                "hair": ("髮型", 30120),
                "skin": ("膚色", 12000),
                "top": ("上衣", 1040014),
                "bottom": ("下身", 1060096),
                "shoes": ("鞋子", 1072005),
            }

            for field, (name, default) in parts.items():
                value = user_data.get(field, default)
                embed.add_field(name=name, value=f"`{value}`", inline=True)

            # 生成 API URL 並顯示圖片
            from cogs.ui.utils import paperdoll_manager

            api_url = paperdoll_manager.build_api_url(user_data)
            if api_url:
                embed.set_image(url=api_url)
                embed.set_footer(text="💫 由 MapleStory.io API 提供")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ 查詢失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="random_character", description="為您隨機生成一個楓之谷娃娃外觀"
    )
    async def random_character(self, interaction: discord.Interaction):
        """隨機生成楓之谷娃娃外觀"""
        await interaction.response.defer(ephemeral=True)

        try:
            import random

            # 楓之谷部位預設列表
            variations = {
                "face": [20000, 20001, 20005, 20100, 20400, 20402, 20405],
                "hair": [30000, 30030, 30120, 30220, 30260, 30300, 30320],
                "skin": [10000, 10001, 10002, 12000, 12100],
                "top": [1040010, 1040014, 1041002, 1040060, 1042003],
                "bottom": [1060002, 1060096, 1060127, 1061112],
                "shoes": [1072005, 1072014, 1072267, 1072410],
            }

            user_id = interaction.user.id
            char_data = {
                "face": random.choice(variations["face"]),
                "hair": random.choice(variations["hair"]),
                "skin": random.choice(variations["skin"]),
                "top": random.choice(variations["top"]),
                "bottom": random.choice(variations["bottom"]),
                "shoes": random.choice(variations["shoes"]),
                "gender": random.choice(["male", "female"]),
            }

            # 更新用戶數據
            for field, value in char_data.items():
                set_user_field(user_id, field, value)

            embed = discord.Embed(
                title="✨ 已為您隨機生成新外觀", color=discord.Color.purple()
            )

            parts = {
                "face": "臉型",
                "hair": "髮型",
                "skin": "膚色",
                "top": "上衣",
                "bottom": "下身",
                "shoes": "鞋子",
                "gender": "性別",
            }

            for field, name in parts.items():
                if field in char_data:
                    embed.add_field(
                        name=name, value=f"`{char_data[field]}`", inline=True
                    )

            # 生成 API URL 並顯示圖片
            from cogs.ui.utils import paperdoll_manager

            api_url = paperdoll_manager.build_api_url(char_data)
            if api_url:
                embed.set_image(url=api_url)
                embed.set_footer(text="💫 喜歡嗎？用 /set_character 自訂吧！")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ 生成失敗: {e}", ephemeral=True)


async def setup(bot):
    """加載 Cog"""
    await bot.add_cog(CharacterSetupCog(bot))
