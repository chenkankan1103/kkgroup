#!/usr/bin/env python3
"""列出置物櫃所有線程"""

import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('UI_DISCORD_BOT_TOKEN')
FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))

async def list_locker_threads():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='/', intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"✅ 機器人已連接: {bot.user}\n")
        
        channel = bot.get_channel(FORUM_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到論壇頻道")
            await bot.close()
            return
        
        # 獲取所有線程
        threads = [t async for t in channel.archived_threads()]
        active_threads = [t for t in channel.threads]
        all_threads = threads + active_threads
        
        print(f"📊 現有線程數: {len(all_threads)}\n")
        print("線程列表:")
        print("="*60)
        
        for idx, thread in enumerate(all_threads[:30], 1):
            print(f"{idx:2d}. {thread.name}")
        
        if len(all_threads) > 30:
            print(f"... 還有 {len(all_threads) - 30} 個線程")
        
        await bot.close()
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(list_locker_threads())
