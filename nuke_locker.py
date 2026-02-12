#!/usr/bin/env python3
"""
置物櫃完全清除 - 刪除所有剩餘線程和消息（徹底清潔）
"""

import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from status_dashboard import add_log

load_dotenv()

TOKEN = os.getenv('UI_DISCORD_BOT_TOKEN')
FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))

async def nuke_locker():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    
    bot = commands.Bot(command_prefix='/', intents=intents)
    
    @bot.event
    async def on_ready():
        add_log("uibot", f"✅ 機器人已連接: {bot.user}")
        
        channel = bot.get_channel(FORUM_CHANNEL_ID)
        if not channel:
            add_log("uibot", f"❌ 找不到論壇頻道")
            await bot.close()
            return
        
        add_log("uibot", f"🔍 論壇: {channel.name}")
        
        # 第 1 步：刪除所有線程
        add_log("uibot", "【步驟 1】刪除所有線程...")
        try:
            threads = [t async for t in channel.archived_threads()]
            active_threads = [t for t in channel.threads]
            all_threads = threads + active_threads
            
            add_log("uibot", f"找到 {len(all_threads)} 個線程要刪除")
            
            for idx, thread in enumerate(all_threads, 1):
                try:
                    await thread.delete()
                    add_log("uibot", f"  ✅ [{idx}/{len(all_threads)}] {thread.name}")
                except Exception as e:
                    add_log("uibot", f"  ❌ [{idx}/{len(all_threads)}] {thread.name} - {e}")
                
                # 避免 API 限流
                await asyncio.sleep(0.1)
            
            add_log("uibot", f"✅ 已刪除 {len(all_threads)} 個線程")
        
        except Exception as e:
            add_log("uibot", f"❌ 刪除線程失敗: {e}")
        
        # 第 2 步：刪除所有消息
        add_log("uibot", "【步驟 2】清理論壇消息...")
        try:
            msg_count = 0
            async for message in channel.history(limit=None):
                try:
                    await message.delete()
                    msg_count += 1
                    if msg_count % 10 == 0:
                        add_log("uibot", f"  ✅ 已清理 {msg_count} 條消息")
                except:
                    pass
                
                # 避免 API 限流
                await asyncio.sleep(0.05)
            
            add_log("uibot", f"✅ 已刪除 {msg_count} 條消息")
        
        except Exception as e:
            add_log("uibot", f"❌ 清理消息失敗: {e}")
        
        add_log("uibot", "✅ 置物櫃已完全清潔！")
        
        await bot.close()
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    add_log("uibot", "🔄 開始置物櫃完全清潔程序...")
    asyncio.run(nuke_locker())
