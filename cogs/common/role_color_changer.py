import discord
from discord.ext import commands, tasks
import random
import os
import asyncio

class RainbowRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rainbow_role_id = int(os.getenv("RAINBOW_ROLE_ID", 0))
        self.monitor_members.start()

    def cog_unload(self):
        self.monitor_members.cancel()

    @tasks.loop(minutes=5)
    async def monitor_members(self):
        await self.bot.wait_until_ready()

        if self.rainbow_role_id == 0:
            return

        for guild in self.bot.guilds:
            role = guild.get_role(self.rainbow_role_id)
            if not role:
                continue

            members = [m for m in guild.members if role in m.roles]
            if members:
                print(f"[🌈] 發現成員擁有七彩角色，開始五分鐘變色循環")
                await self.run_rainbow_cycle(role)
            else:
                print(f"[⏸️] 沒有成員擁有七彩角色，暫停變色")

    async def run_rainbow_cycle(self, role: discord.Role):
        for _ in range(30):  # 每 10 秒變色，共 5 分鐘
            color = discord.Color.from_rgb(
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            )
            try:
                await role.edit(color=color, reason="自動七彩變色")
            except discord.Forbidden:
                print("[❌] 權限不足，無法變更七彩角色顏色")
                return
            except Exception as e:
                print(f"[❌] 變色錯誤：{e}")
                return
            await asyncio.sleep(30)

    @monitor_members.before_loop
    async def before_monitor_members(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RainbowRole(bot))
