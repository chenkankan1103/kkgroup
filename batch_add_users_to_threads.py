#!/usr/bin/env python3
"""批量將所有用戶添加到現有的置物櫃線程中"""

import asyncio
import discord
import os
from dotenv import load_dotenv
from db_adapter import get_all_users, get_user_field

load_dotenv()

FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

class ThreadUserAdder(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.added_count = 0
        self.error_count = 0
        self.already_added = 0

    async def on_ready(self):
        print(f"✅ 已連接為 {self.user}")
        
        try:
            forum_channel = self.bot.get_channel(FORUM_CHANNEL_ID) if hasattr(self, 'bot') else self.get_channel(FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print(f"❌ 找不到論壇頻道 {FORUM_CHANNEL_ID}")
                await self.close()
                return
            
            print(f"🔍 論壇頻道: {forum_channel.name}")
            print(f"➕ 開始批量添加用戶到線程...\n")
            
            # 從資料庫獲取所有用戶
            all_users = get_all_users()
            guild = forum_channel.guild
            
            print(f"📊 找到 {len(all_users)} 個用戶\n")
            print(f"{'='*50}\n")
            
            # 遍歷每個用戶
            for idx, user_data in enumerate(all_users, 1):
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id', 0)
                username = user_data.get('username', 'Unknown')
                
                if not thread_id or thread_id == 0:
                    print(f"{idx}. ⏭️  {username} - 沒有 thread_id（跳過）")
                    continue
                
                try:
                    # 獲取線程
                    thread = forum_channel.get_thread(thread_id)
                    if not thread:
                        # 嘗試從已存檔線程取得
                        try:
                            thread = await forum_channel.fetch_archived_thread(thread_id)
                        except discord.NotFound:
                            thread = None
                    
                    if not thread:
                        print(f"{idx}. ❌ {username} - 線程不存在或已刪除")
                        self.error_count += 1
                        continue
                    
                    # 獲取用戶對象
                    try:
                        user = await self.fetch_user(user_id)
                    except discord.NotFound:
                        print(f"{idx}. ❌ {username} - 用戶不存在")
                        self.error_count += 1
                        continue
                    
                    # 檢查用戶是否已在線程中
                    try:
                        # 嘗試獲取用戶在線程中的權限
                        perms = thread.permissions_for(user)
                        if perms is not None and perms.view_channel:
                            print(f"{idx}. ℹ️  {username} - 已在線程中")
                            self.already_added += 1
                            continue
                    except:
                        pass
                    
                    # 添加用戶到線程
                    try:
                        await thread.add_user(user)
                        self.added_count += 1
                        print(f"{idx}. ✅ {username} - 已添加\n")
                    except discord.Forbidden:
                        print(f"{idx}. ❌ {username} - 權限不足")
                        self.error_count += 1
                    except discord.HTTPException as e:
                        print(f"{idx}. ❌ {username} - API 錯誤: {e.status}")
                        self.error_count += 1
                    
                except Exception as e:
                    self.error_count += 1
                    print(f"{idx}. ❌ {username} - 未知錯誤: {str(e)[:50]}\n")
                
                await asyncio.sleep(0.3)  # 避免速率限制
            
            print(f"\n{'='*50}")
            print(f"📈 操作完成！")
            print(f"✅ 新增: {self.added_count} 個用戶")
            print(f"ℹ️ already 已有: {self.already_added} 個用戶")
            print(f"❌ 遇到錯誤: {self.error_count} 個")
            print(f"{'='*50}\n")
            
        except Exception as e:
            print(f"❌ 操作過程中出現錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.close()

async def main():
    """執行批量添加"""
    print("🚀 開始批量添加用戶到現有線程...")
    print(f"論壇頻道 ID: {FORUM_CHANNEL_ID}\n")
    
    client = ThreadUserAdder()
    async with client:
        await client.start(BOT_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
