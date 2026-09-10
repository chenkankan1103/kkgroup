import discord
from status_dashboard import add_log
import sys
from pathlib import Path

# Add kkgroup directory to sys.path for absolute imports
kkgroup_dir = Path(__file__).resolve().parent.parent.parent
if str(kkgroup_dir) not in sys.path:
    sys.path.insert(0, str(kkgroup_dir))

from cogs.ui.uibody import LockerPanelView


class PersonalItemsView(discord.ui.View):
    def __init__(self, cog, user_id, thread):
        super().__init__(timeout=None)  # Permanent View
        self.cog = cog
        self.user_id = user_id
        self.thread = thread

    @discord.ui.button(label="View Items", style=discord.ButtonStyle.primary)
    async def view_items_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        add_log("ui", f"[PersonalItems] View Items button clicked by {interaction.user.id}")
        embed = discord.Embed(
            title="🛍️ Personal Items", description="Displaying user items...", color=0x00FF00
        )
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.danger)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        add_log("ui", f"[PersonalItems] Return button clicked by {interaction.user.id}")
        embed = discord.Embed(
            title="🌿 Personal Locker", description="Select an option:", color=0x00FF00
        )

        view = LockerPanelView(self.cog, self.user_id, self.thread)
        await interaction.message.edit(embed=embed, view=view)