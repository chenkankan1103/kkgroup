import discord
from discord import app_commands
from discord.ext import commands
import re

class NicknameIDManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 為所有成員設定園編
    @app_commands.command(name="assign_nickname_id", description="為所有成員設定園編編號")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def assign_nickname_id(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        success_count = 0
        failed_count = 0
        for member in interaction.guild.members:
            if member.bot:  # 跳過 BOT
                continue
            try:
                # 使用 display_name 作為名稱來源
                base_name = member.display_name
                park_id = f"No.{int(member.id) % 100000:05d}"  # 園編格式：No.00001~99999
                new_nick = f"{park_id} {base_name}" if not base_name.startswith(park_id) else base_name

                # 設定新的暱稱
                await member.edit(nick=new_nick, reason="設定園編編號")
                print(f"✅ 成功設定暱稱: {new_nick}")
                success_count += 1
            except Exception as e:
                print(f"❌ 無法變更 {member.display_name} 的暱稱: {e}")
                failed_count += 1
        await interaction.followup.send(
            f"🎉 已為 {success_count} 位成員設定園編編號。\n"
            f"⚠️ 有 {failed_count} 位成員暱稱變更失敗（可能是權限問題）。"
        )

    # 為所有成員移除園編
    @app_commands.command(name="remove_nickname_id", description="移除園編編號，還原所有成員原始暱稱")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def remove_nickname_id(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        success_count = 0
        failed_count = 0
        pattern = re.compile(r"^No\.\d{5}\s*")  # 匹配園編開頭的部分
        for member in interaction.guild.members:
            if member.bot or member.nick is None:  # 跳過 BOT 和無暱稱成員
                continue
            try:
                original_nick = pattern.sub("", member.nick).strip()
                await member.edit(nick=original_nick, reason="移除園編編號")
                success_count += 1
            except Exception as e:
                print(f"❌ 無法變更 {member.display_name} 的暱稱: {e}")
                failed_count += 1
        await interaction.followup.send(
            f"🧼 已移除 {success_count} 位成員的園編編號。\n"
            f"⚠️ 有 {failed_count} 位成員暱稱移除失敗（可能是權限問題）。"
        )

    # 單人設定園編
    @app_commands.command(name="test_assign_nickname_id", description="為指定成員設定園編編號（單人測試）")
    @app_commands.describe(member="要設定園編的成員")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def test_assign_nickname_id(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(thinking=True)
        if member.bot:  # 跳過 BOT
            return await interaction.followup.send("⚠️ 無法處理 BOT 成員。")
        try:
            # 使用 display_name 作為名稱來源
            base_name = member.display_name
            park_id = f"No.{int(member.id) % 100000:05d}"  # 園編格式：No.00001~99999
            new_nick = f"{park_id} {base_name}" if not base_name.startswith(park_id) else base_name

            # 設定新的暱稱
            await member.edit(nick=new_nick, reason="測試設定園編編號")
            await interaction.followup.send(f"✅ 成功為 {member.mention} 設定園編編號：`{new_nick}`")
        except Exception as e:
            print(f"❌ 無法變更 {member.display_name} 的暱稱: {e}")
            await interaction.followup.send(f"❌ 無法為 {member.mention} 設定園編：{e}")

    # 單人移除園編
    @app_commands.command(name="test_remove_nickname_id", description="移除指定成員的園編編號（單人測試）")
    @app_commands.describe(member="要還原暱稱的成員")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def test_remove_nickname_id(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(thinking=True)
        if member.bot or member.nick is None:  # 跳過 BOT 和無暱稱成員
            return await interaction.followup.send("⚠️ 無法處理 BOT 或無暱稱成員。")
        pattern = re.compile(r"^No\.\d{5}\s*")  # 匹配園編開頭的部分
        if not pattern.search(member.nick):
            return await interaction.followup.send("ℹ️ 該成員的暱稱中不含園編編號。")
        try:
            original_nick = pattern.sub("", member.nick).strip()
            await member.edit(nick=original_nick, reason="測試移除園編編號")
            await interaction.followup.send(f"🧼 已成功移除 {member.mention} 的園編編號，恢復為：`{original_nick}`")
        except Exception as e:
            print(f"❌ 無法變更 {member.display_name} 的暱稱: {e}")
            await interaction.followup.send(f"❌ 無法移除 {member.mention} 的園編：{e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(NicknameIDManager(bot))