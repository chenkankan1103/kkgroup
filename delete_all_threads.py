#!/usr/bin/env python3
"""完全刪除置物櫃論壇中的所有線程"""

import asyncio
import discord
import os
from dotenv import load_dotenv

load_dotenv()

FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

class ThreadDeleter(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.deleted_count = 0
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
            print(f"🗑️ 開始刪除所有線程...\n")
            
            # 掃描論壇中的所有線程
            all_threads = []
            guild = forum_channel.guild
            for thread in guild.threads:
                if thread.parent_id == FORUM_CHANNEL_ID:
                    all_threads.append(thread)
            
            print(f"📊 找到論壇中的線程：{len(all_threads)} 個\n")
            print(f"{'='*50}\n")
            
            # 逐個刪除線程
            for idx, thread in enumerate(all_threads, 1):
                try:
                    thread_name = thread.name
                    thread_id = thread.id
                    print(f"{idx}. 刪除線程 '{thread_name}'...", end=" ")
                    
                    await thread.delete()
                    self.deleted_count += 1
                    print("✅ 已刪除\n")
                    
                except Exception as e:
                    self.error_count += 1
                    print(f"❌ 刪除失敗: {str(e)[:50]}\n")
                
                await asyncio.sleep(0.5)  # 避免速率限制
            
            print(f"{'='*50}")
            print(f"\n📈 刪除完成！")
            print(f"✅ 成功刪除: {self.deleted_count} 個線程")
            print(f"❌ 遇到錯誤: {self.error_count} 個線程")
            print(f"{'='*50}\n")
            print(f"⚠️ 等待 UI BOT 重新初始化...\n")
            
        except Exception as e:
            print(f"❌ 刪除過程中出現錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.close()

async def main():
    """執行刪除"""
    print("🚀 開始刪除置物櫃論壇線程...")
    print(f"論壇頻道 ID: {FORUM_CHANNEL_ID}\n")
    print("⚠️ 警告：此操作將刪除所有線程，無法撤銷！\n")
    
    # 確認
    response = input("輸入 'DELETE' 確認刪除所有線程: ")
    if response.upper() != "DELETE":
        print("❌ 已取消操作")
        return
    
    print()
    client = ThreadDeleter()
    async with client:
        await client.start(BOT_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
