#!/usr/bin/env python3
"""
置物櫃清理和重發 - 刪除論壇所有線程、清理消息，然後重新發送個人線程

使用方式：
python reset_locker_and_refetch.py
"""

import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('UI_DISCORD_BOT_TOKEN')
FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))

class LockerResetter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def delete_all_threads(self):
        """刪除論壇中所有線程"""
        channel = self.bot.get_channel(FORUM_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到論壇頻道: {FORUM_CHANNEL_ID}")
            return 0
        
        print(f"🔍 正在掃描論壇: {channel.name}")
        
        # 獲取所有活躍線程
        threads = [thread async for thread in channel.archived_threads()]
        active_threads = [thread for thread in channel.threads]
        all_threads = threads + active_threads
        
        print(f"📊 找到 {len(all_threads)} 個線程")
        
        deleted_count = 0
        for idx, thread in enumerate(all_threads, 1):
            try:
                await thread.delete()
                print(f"  ✅ [{idx}/{len(all_threads)}] 已刪除線程: {thread.name}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ [{idx}/{len(all_threads)}] 刪除失敗 {thread.name}: {e}")
        
        return deleted_count
    
    async def delete_all_messages(self):
        """刪除論壇中的所有消息"""
        channel = self.bot.get_channel(FORUM_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到論壇頻道: {FORUM_CHANNEL_ID}")
            return 0
        
        print(f"🗑️  正在清理論壇消息...")
        
        deleted_count = 0
        try:
            async for message in channel.history(limit=None):
                try:
                    await message.delete()
                    deleted_count += 1
                    if deleted_count % 10 == 0:
                        print(f"  ✅ 已清理 {deleted_count} 條消息")
                except Exception as e:
                    print(f"  ⚠️  無法刪除消息 {message.id}: {e}")
        except Exception as e:
            print(f"❌ 清理消息失敗: {e}")
        
        return deleted_count
    
    async def refetch_locker_threads(self):
        """重新獲取用戶的置物櫃線程（自動建立）"""
        from db_adapter import get_all_users
        
        channel = self.bot.get_channel(FORUM_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到論壇頻道: {FORUM_CHANNEL_ID}")
            return 0
        
        print(f"🔄 重新建立用戶置物櫃線程...")
        
        try:
            users = get_all_users()
            created_count = 0
            
            for idx, user_id in enumerate(users, 1):
                try:
                    user = await self.bot.fetch_user(user_id)
                    
                    # 建立線程
                    thread = await channel.create_thread(
                        name=f"🏠 {user.name}的置物櫃",
                        type=discord.ChannelType.public_thread
                    )
                    
                    # 設置線程所有者
                    await thread.edit(owner_id=user_id)
                    
                    # 發送歡迎消息
                    from db_adapter import set_user_field
                    set_user_field(user_id, 'thread_id', thread.id)
                    
                    embed = discord.Embed(
                        title=f"👋 {user.name}的個人置物櫃",
                        description="這是你的個人置物櫃，所有農耕和收集都在這裡進行。",
                        color=discord.Color.green()
                    )
                    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
                    
                    await thread.send(embed=embed)
                    
                    print(f"  ✅ [{idx}/{len(users)}] 已建立 {user.name} 的置物櫃線程")
                    created_count += 1
                    
                except Exception as e:
                    print(f"  ❌ [{idx}/{len(users)}] 建立失敗 (ID: {user_id}): {e}")
            
            return created_count
        
        except Exception as e:
            print(f"❌ 重新建立置物櫃失敗: {e}")
            return 0

async def main():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    
    bot = commands.Bot(command_prefix='/', intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"✅ 機器人已連接: {bot.user}")
        
        # 加載 Cog
        cog = LockerResetter(bot)
        await bot.add_cog(cog)
        
        print("\n" + "="*50)
        print("🧹 置物櫃重置流程開始")
        print("="*50)
        
        # 步驟 1: 刪除所有線程
        print("\n[1/3] 刪除論壇所有線程...")
        threads_deleted = await cog.delete_all_threads()
        print(f"✅ 已刪除 {threads_deleted} 個線程\n")
        
        # 步驟 2: 清理消息
        print("[2/3] 清理論壇消息...")
        messages_deleted = await cog.delete_all_messages()
        print(f"✅ 已清理 {messages_deleted} 條消息\n")
        
        # 步驟 3: 重新建立用戶線程
        print("[3/3] 重新建立用戶置物櫃線程...")
        threads_created = await cog.refetch_locker_threads()
        print(f"✅ 已建立 {threads_created} 個置物櫃線程\n")
        
        print("="*50)
        print("✅ 置物櫃重置完成！")
        print("="*50)
        
        await bot.close()
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    print("🚀 啟動置物櫃重置程序...")
    asyncio.run(main())
