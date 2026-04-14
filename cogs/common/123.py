import discord
from discord import app_commands
from discord.ext import commands

class NicknameReset(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="restore_global_nicknames", description="還原所有人的 Discord 全域暱稱（移除伺服器暱稱）")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def restore_global_nicknames(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        success = 0
        failed = 0

        for member in interaction.guild.members:
            if member.bot or member.nick is None:
                continue
            try:
                await member.edit(nick=None, reason="還原全域暱稱")
                success += 1
            except Exception as e:
                print(f"❌ 無法重設 {member.display_name} 的暱稱: {e}")
                failed += 1

        await interaction.followup.send(
            f"🧼 已還原 {success} 位成員的暱稱為全域暱稱。\n"
            f"⚠️ 有 {failed} 位成員處理失敗（可能因為權限不足或已無暱稱）。"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(NicknameReset(bot))
