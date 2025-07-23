import discord
from discord.ext import commands
import sqlite3
import os

DB_PATH = "user_data.db"

class MemberSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (str(member.id),))
        if not c.fetchone():
            c.execute('''INSERT INTO users (user_id) VALUES (?)''', (str(member.id),))
            conn.commit()
        conn.close()
        print(f"✅ 已新增用戶 {member} 到資料庫")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id = ?", (str(member.id),))
        conn.commit()
        conn.close()
        print(f"❌ 已從資料庫刪除用戶 {member}")

async def setup(bot):
    await bot.add_cog(MemberSync(bot))
