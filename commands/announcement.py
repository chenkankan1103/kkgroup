import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Select, TextInput, Modal

class AnnouncementModal(Modal):
    def __init__(self, select: Select):
        super().__init__(title="公告內容填寫")
        self.select = select
        # 在 Modal 中創建公告內容的輸入框
        self.add_item(TextInput(label="公告內容", style=discord.TextStyle.paragraph, placeholder="在這裡輸入公告內容", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        message = self.children[0].value
        # 發送公告
        await interaction.channel.send(f"📢 【{self.select.values[0]}】公告：{message}")
        await interaction.response.send_message("✅ 公告已發送。", ephemeral=True)

class Announcement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="公告", description="發送公告訊息")
    async def announce(self, interaction: discord.Interaction):
        # 檢查是否為管理員
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 你沒有權限使用這個指令。", ephemeral=True)
            return

        # 建立下拉選單
        select = Select(
            placeholder="選擇公告類型...",
            options=[
                discord.SelectOption(label="系統公告", value="系統公告"),
                discord.SelectOption(label="活動公告", value="活動公告"),
                discord.SelectOption(label="緊急公告", value="緊急公告")
            ]
        )

        async def select_callback(interaction2: discord.Interaction):
            modal = AnnouncementModal(select)
            await interaction2.response.send_modal(modal)

        select.callback = select_callback

        view = View()
        view.add_item(select)

        await interaction.response.send_message("請選擇公告類型並填寫公告內容：", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Announcement(bot))