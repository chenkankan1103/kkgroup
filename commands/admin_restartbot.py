import os
import subprocess
from discord import app_commands, Interaction
from discord.ext import commands
import discord

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
SERVICES = [
    ("shopbot", "/home/e193752468/kkgroup/shopbot.py"),
    ("uibot", "/home/e193752468/kkgroup/uibot.py"),
    ("bot", "/home/e193752468/kkgroup/bot.py"),
]

class AdminBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def kill_process_by_path(self, path: str):
        """用 ps + grep 找到對應 Python 進程並 kill"""
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            lines = result.stdout.splitlines()
            killed = []
            for line in lines:
                if path in line and "grep" not in line:
                    pid = int(line.split()[1])
                    subprocess.run(["kill", "-9", str(pid)])
                    killed.append(pid)
            return killed
        except Exception as e:
            print(f"Kill error for {path}: {e}")
            return []

    @app_commands.command(name="restart_all", description="全部重啟 bot 服務")
    async def restart_all(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        results = []

        # 依序 kill 其他服務，最後 kill 自己
        for name, path in SERVICES:
            killed = self.kill_process_by_path(path)
            if killed:
                results.append(f"✅ {name} 已被殺掉 (PID: {', '.join(map(str, killed))})")
            else:
                results.append(f"⚠️ {name} 沒有找到進程，可能已經停止")
        
        results.append("ℹ️ Systemd 若設定了 Restart=always，應會自動重啟服務")
        await interaction.followup.send("🔄 全部服務重啟完成:\n" + "\n".join(results))

async def setup(bot):
    await bot.add_cog(AdminBot(bot))
