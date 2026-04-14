"""
Locker Event Test Command
測試事件系統的指令
"""
import discord
from discord.ext import commands
from discord import app_commands

from uicommands.events import (
    EquipmentChangedEvent,
    CurrencyChangedEvent,
    HealthChangedEvent,
    FullRefreshEvent,
)


class LockerEventTestCog(commands.Cog):
    """置物櫃事件系統測試"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="test_locker_equipment", description="[測試] 觸發裝備變更事件")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_equipment_event(self, interaction: discord.Interaction):
        """測試 EquipmentChangedEvent"""
        await interaction.response.defer()
        
        user_id = interaction.user.id
        event = EquipmentChangedEvent(
            user_id=user_id,
            changed_fields={"equip_0", "equip_1"}
        )
        
        print(f"🧪 [TEST] 觸發 EquipmentChangedEvent: {event}")
        self.bot.dispatch("equipment_changed", event)
        
        await interaction.followup.send("✅ EquipmentChangedEvent 已觸發", ephemeral=True)
    
    @app_commands.command(name="test_locker_currency", description="[測試] 觸發 KK幣變更事件")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_currency_event(self, interaction: discord.Interaction):
        """測試 CurrencyChangedEvent"""
        await interaction.response.defer()
        
        user_id = interaction.user.id
        event = CurrencyChangedEvent(
            user_id=user_id,
            changed_fields={"kkcoin", "xp"}
        )
        
        print(f"🧪 [TEST] 觸發 CurrencyChangedEvent: {event}")
        self.bot.dispatch("currency_changed", event)
        
        await interaction.followup.send("✅ CurrencyChangedEvent 已觸發", ephemeral=True)
    
    @app_commands.command(name="test_locker_health", description="[測試] 觸發血量變更事件")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_health_event(self, interaction: discord.Interaction):
        """測試 HealthChangedEvent"""
        await interaction.response.defer()
        
        user_id = interaction.user.id
        event = HealthChangedEvent(
            user_id=user_id,
            changed_fields={"hp", "stamina"}
        )
        
        print(f"🧪 [TEST] 觸發 HealthChangedEvent: {event}")
        self.bot.dispatch("health_changed", event)
        
        await interaction.followup.send("✅ HealthChangedEvent 已觸發", ephemeral=True)
    
    @app_commands.command(name="test_locker_full_refresh", description="[測試] 觸發完整刷新事件")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_full_refresh_event(self, interaction: discord.Interaction):
        """測試 FullRefreshEvent"""
        await interaction.response.defer()
        
        user_id = interaction.user.id
        event = FullRefreshEvent(
            user_id=user_id,
            changed_fields={"*"}
        )
        
        print(f"🧪 [TEST] 觸發 FullRefreshEvent: {event}")
        self.bot.dispatch("full_refresh", event)
        
        await interaction.followup.send("✅ FullRefreshEvent 已觸發", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LockerEventTestCog(bot))
