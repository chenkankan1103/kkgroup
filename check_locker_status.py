#!/usr/bin/env python3
"""檢查置物櫃狀態"""

import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('UI_DISCORD_BOT_TOKEN')
FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))

async def check_locker_status():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='/', intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"✅ 機器人已連接: {bot.user}")
        
        channel = bot.get_channel(FORUM_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到論壇頻道")
            await bot.close()
            return
        
        print(f"\n📍 論壇頻道: {channel.name}")
        
        # 統計線程
        threads = [t async for t in channel.archived_threads()]
        active_threads = [t for t in channel.threads]
        all_threads = threads + active_threads
        
        print(f"📊 現有線程數: {len(all_threads)}")
        
        # 統計消息
        msg_count = 0
        try:
            async for msg in channel.history(limit=None):
                msg_count += 1
        except:
            pass
        
        print(f"💬 現有消息數: {msg_count}")
        print(f"\n✅ 置物櫃狀態檢查完成")
        
        await bot.close()
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    print("🔍 檢查置物櫃狀態...\n")
    asyncio.run(check_locker_status())
