#!/usr/bin/env python3
"""清理置物櫃論壇線程中的所有消息並重新初始化"""

import asyncio
import discord
import os
from dotenv import load_dotenv
from db_adapter import get_all_users, get_user_field
import sqlite3

load_dotenv()

FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

class ThreadCleaner(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.cleaned_count = 0
        self.error_count = 0

    async def on_ready(self):
        print(f"✅ 已連接為 {self.user}")
        
        try:
            forum_channel = self.get_channel(FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print(f"❌ 找不到論壇頻道 {FORUM_CHANNEL_ID}")
                await self.close()
                return
            
            print(f"🔍 論壇頻道: {forum_channel.name}")
            print(f"📋 開始清理線程...\n")
            
            # 掃描論壇中的所有線程
            print(f"🔎 掃描論壇中的所有線程...\n")
            all_threads = []
            
            # 從 guild 獲取所有線程，並過濾屬於該論壇的線程
            guild = forum_channel.guild
            for thread in guild.threads:
                if thread.parent_id == FORUM_CHANNEL_ID:
                    all_threads.append(thread)
            
            print(f"📊 找到論壇中的線程：{len(all_threads)} 個\n")
            
            # 逐個清理線程
            for idx, thread in enumerate(all_threads, 1):
                try:
                    print(f"{idx}. 清理線程 '{thread.name}' (ID: {thread.id})...")
                    
                    # 刪除線程中的所有消息
                    message_count = 0
                    async for message in thread.history(limit=None, oldest_first=False):
                        try:
                            await message.delete()
                            message_count += 1
                            await asyncio.sleep(0.05)  # 避免速率限制
                        except Exception as e:
                            if "Unknown Message" not in str(e):
                                print(f"   ⚠️ 刪除消息失敗: {e}")
                    
                    self.cleaned_count += 1
                    status = "✅ 已清空" if message_count > 0 else "ℹ️ 無需清空"
                    print(f"   {status} (刪除 {message_count} 條消息)\n")
                    
                except Exception as e:
                    self.error_count += 1
                    print(f"   ❌ 清理失敗: {str(e)[:50]}\n")
                
                await asyncio.sleep(0.1)
            
            print(f"\n{'='*50}")
            print(f"📈 清理完成！")
            print(f"✅ 成功清空: {self.cleaned_count} 個線程")
            print(f"❌ 遇到錯誤: {self.error_count} 個線程")
            print(f"{'='*50}\n")
            
        except Exception as e:
            print(f"❌ 清理過程中出現錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.close()

async def main():
    """執行清理"""
    print("🚀 開始清理置物櫃論壇線程...")
    print(f"論壇頻道 ID: {FORUM_CHANNEL_ID}\n")
    
    client = ThreadCleaner()
    async with client:
        await client.start(BOT_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
