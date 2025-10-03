import os
import subprocess
from discord import app_commands, Interaction
from discord.ext import commands
import discord

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))

SERVICES = [
    ("shopbot", "shopbot.service"),
    ("uibot", "uibot.service"),
    ("bot", "bot.service"),
]

class AdminBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def restart_service(self, service_name: str):
        """使用 systemctl 重啟服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True, f"✅ {service_name} 重啟成功"
            else:
                return False, f"❌ {service_name} 重啟失敗: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, f"⏱️ {service_name} 重啟超時"
        except Exception as e:
            return False, f"❌ {service_name} 重啟錯誤: {str(e)}"
    
    def get_service_status(self, service_name: str):
        """獲取服務狀態"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip()
        except:
            return "unknown"
    
    @app_commands.command(name="restart_all", description="全部重啟 bot 服務")
    async def restart_all(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        results = []
        
        # 重啟所有服務
        for name, service in SERVICES:
            success, message = self.restart_service(service)
            results.append(message)
        
        await interaction.followup.send("🔄 重啟結果:\n" + "\n".join(results))
    
    @app_commands.command(name="restart", description="重啟指定的 bot 服務")
    @app_commands.describe(service="選擇要重啟的服務")
    @app_commands.choices(service=[
        app_commands.Choice(name="ShopBot", value="shopbot.service"),
        app_commands.Choice(name="UIBot", value="uibot.service"),
        app_commands.Choice(name="Bot", value="bot.service"),
    ])
    async def restart(self, interaction: Interaction, service: str):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        success, message = self.restart_service(service)
        await interaction.followup.send(message)
    
    @app_commands.command(name="status", description="查看所有 bot 服務狀態")
    async def status(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        results = []
        
        for name, service in SERVICES:
            status = self.get_service_status(service)
            emoji = "🟢" if status == "active" else "🔴"
            results.append(f"{emoji} {name}: {status}")
        
        await interaction.followup.send("📊 服務狀態:\n" + "\n".join(results))

async def setup(bot):
    await bot.add_cog(AdminBot(bot))
