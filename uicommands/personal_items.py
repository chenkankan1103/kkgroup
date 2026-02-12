import discord
from discord.ext import commands
from status_dashboard import add_log

class PersonalItemsView(discord.ui.View):
    def __init__(self, cog, user_id, thread):
        super().__init__(timeout=60)  # 設置60秒超時
        self.cog = cog
        self.user_id = user_id
        self.thread = thread

    @discord.ui.button(label="查看物品", style=discord.ButtonStyle.primary)
    async def view_items_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        add_log("ui", f"[PersonalItems] 查看物品按鈕點擊 by {interaction.user.id}")
        embed = discord.Embed(title="🛍️ 個人物品", description="這裡顯示用戶物品...", color=0x00FF00)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)

    @discord.ui.button(label="返回", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        add_log("ui", f"[PersonalItems] 返回按鈕點擊 by {interaction.user.id}")
        embed = discord.Embed(title="🌿 個人置物櫃", description="選擇一個選項：", color=0x00FF00)
        from .uibody import LockerPanelView  # 匯入
        view = LockerPanelView(self.cog, self.user_id, self.thread)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)