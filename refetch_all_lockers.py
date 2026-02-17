#!/usr/bin/env python3
"""
置物櫃重新建立 - 為所有用戶重新建立置物櫃線程

使用方式：
python refetch_all_lockers.py
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

async def refetch_all_lockers():
    from db_adapter import get_all_users, set_user_field
    
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
        add_log("uibot", "【步驟】重新建立所有用戶置物櫃線程...")
        
        try:
            users = get_all_users()
            add_log("uibot", f"📊 找到 {len(users)} 個用戶")
            
            created_count = 0
            failed_count = 0
            
            for idx, user_data in enumerate(users, 1):
                try:
                    user_id = user_data.get('user_id') if isinstance(user_data, dict) else user_data
                    
                    user = await bot.fetch_user(user_id)
                    
                    # 清理線程名稱（移除特殊字符）
                    safe_name = f"🏠 {user.name}的置物櫃"[:100]
                    
                    # 建立線程
                    thread = await channel.create_thread(
                        name=safe_name,
                        type=discord.ChannelType.public_thread
                    )
                    
                    # 設置線程所有者
                    try:
                        await thread.edit(owner_id=user_id)
                    except:
                        pass  # 忽略 owner_id 設置錯誤
                    
                    # 保存線程 ID 到資料庫
                    set_user_field(user_id, 'thread_id', thread.id)
                    
                    # 發送歡迎消息（包含紙娃娃預覽）
                    embed = discord.Embed(
                        title=f"👋 {user.name}的個人置物櫃",
                        description="這是你的個人置物櫃 🏠\n所有農耕和收集都在這裡進行。",
                        color=discord.Color.green()
                    )
                    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
                    # 嘗試從資料庫產生 MapleStory.io API 圖片 URL，若失敗則省略
                    try:
                        from db_adapter import get_user
                        from uicommands.utils.image_utils import build_maplestory_api_url
                        user_data_row = get_user(user_id)
                        if user_data_row:
                            api_url = build_maplestory_api_url(user_data_row)
                            embed.set_image(url=api_url)
                    except Exception:
                        pass

                    embed.set_footer(text=f"線程 ID: {thread.id}")
                    await thread.send(embed=embed)
                    
                    print(f"  ✅ [{idx:3d}/{len(users):3d}] {user.name}")
                    created_count += 1
                    
                except Exception as e:
                    add_log("uibot", f"  ❌ [{idx:3d}/{len(users):3d}] 用戶 {user_id} - {str(e)[:50]}")
                    failed_count += 1
                
                # 避免 API 限流（每 0.5 秒建立一個線程）
                await asyncio.sleep(0.5)
            
            add_log("uibot", f"✅ 成功建立: {created_count}")
            if failed_count > 0:
                add_log("uibot", f"❌ 失敗: {failed_count}")
        
        except Exception as e:
            add_log("uibot", f"❌ 操作失敗: {e}")
        
        await bot.close()
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    add_log("uibot", "🔄 開始重新建立所有用戶置物櫃...")
    asyncio.run(refetch_all_lockers())
