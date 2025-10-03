import subprocess
from discord import app_commands, Interaction
from discord.ext import commands

SERVICES = [
    ("shopbot", "shopbot.py"),
    ("uibot", "uibot.py"),
    ("bot", "bot.py")  # 自己最後 Kill
]

class AdminBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="restart_all", description="Kill + Auto Restart 服務")
    async def restart_all(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        results = []

        for name, filename in SERVICES:
            try:
                # Kill 進程
                pids = subprocess.run(
                    ["pgrep", "-f", filename],
                    capture_output=True, text=True
                ).stdout.strip()

                if pids:
                    subprocess.run(["kill", "-9"] + pids.split())
                    results.append(f"🛑 已停止 {name} ({filename}) 進程: {pids}")
                else:
                    results.append(f"⚠️ 找不到 {name} 進程 ({filename})，可能已停止")

            except Exception as e:
                results.append(f"❌ {name} 停止失敗: {e}")

            # 如果是自己，Kill 完就不發送 followup 了
            if name == "bot":
                break

        await interaction.followup.send("🔄 全部服務 Kill 指令執行完成:\n" + "\n".join(results))
