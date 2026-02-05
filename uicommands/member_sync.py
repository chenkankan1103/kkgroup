import discord
from discord.ext import commands
from db_adapter import set_user, delete_user, get_user

class MemberSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # 檢查用戶是否已存在，不存在則創建
        existing_user = get_user(member.id)
        if not existing_user:
            # user_id will be automatically set by set_user
            set_user(member.id, {})
            print(f"✅ 已新增用戶 {member} 到資料庫")
        else:
            print(f"ℹ️ 用戶 {member} 已存在於資料庫中")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        delete_user(member.id)
        print(f"❌ 已從資料庫刪除用戶 {member}")

async def setup(bot):
    await bot.add_cog(MemberSync(bot))
