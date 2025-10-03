import os
import subprocess
import asyncio
from datetime import datetime
from discord import app_commands, Interaction
from discord.ext import commands
from dotenv import load_dotenv
import discord

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
DISCORD_SYS_CHANNEL_ID = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))
GIT_DIR = "/home/e193752468/kkgroup"

SERVICES = ["bot.service", "shopbot.service", "uibot.service"]

class AdminBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --------------------------
    # 檢查 Git 更新
    # --------------------------
    async def check_git_updates(self):
        try:
            subprocess.run(["git", "fetch"], cwd=GIT_DIR, check=True)
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                cwd=GIT_DIR,
                capture_output=True,
                text=True,
                check=True
            )
            commits_behind = int(result.stdout.strip())
            return commits_behind > 0, commits_behind
        except Exception as e:
            return False, 0

    async def pull_git_updates(self):
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=GIT_DIR,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except Exception as e:
            return False, str(e)

    # --------------------------
    # Discord 指令
    # --------------------------
    @app_commands.command(name="notify", description="發送 Git 更新通知 (不重啟)")
    async def notify(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        has_update, commits_count = await self.check_git_updates()
        if not has_update:
            await interaction.followup.send("ℹ️ 沒有新更新")
            return

        success, pull_result = await self.pull_git_updates()
        if not success:
            await interaction.followup.send(f"❌ Git 拉取失敗:\n```\n{pull_result}\n```")
            return

        embed_text = f"🔄 發現 {commits_count} 個更新，已拉取最新程式碼\n\n```{pull_result[:1000]}```"
        await interaction.followup.send(embed=discord.Embed(title="更新通知", description=embed_text, color=0xFFA500))

    @app_commands.command(name="restart_all", description="全部重啟 bot 服務")
    async def restart_all(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        results = []
        for svc in SERVICES:
            try:
                # 直接用 systemctl，不用 sudo
                subprocess.run(["systemctl", "restart", svc], check=True)
                results.append(f"✅ {svc} 重啟成功")
            except Exception as e:
                results.append(f"❌ {svc} 重啟失敗: {e}")

        await interaction.followup.send("\n".join(results))

    @app_commands.command(name="restart", description="重啟指定服務")
    @app_commands.choices(service=[app_commands.Choice(name=s, value=s) for s in SERVICES])
    async def restart(self, interaction: Interaction, service: app_commands.Choice[str]):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        svc_name = service.value
        try:
            subprocess.run(["systemctl", "restart", svc_name], check=True)
            await interaction.followup.send(f"✅ {svc_name} 重啟成功")
        except Exception as e:
            await interaction.followup.send(f"❌ {svc_name} 重啟失敗: {e}")

async def setup(bot):
    await bot.add_cog(AdminBot(bot))
