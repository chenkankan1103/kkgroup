#!/usr/bin/env python3
"""
強制更新所有置物櫃 embed — 移除 image_source field，使用動態生成的 API URL
"""
import asyncio
import sys
import os

# 加入 kkgroup 路徑
sys.path.insert(0, '/home/e193752468/kkgroup')

async def main():
    import discord
    from discord.ext import commands
    import sqlite3
    from db_adapter import get_all_users, set_user_field
    
    # 從環境變數加載 token（或從 .env）
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass
    
    token = os.getenv('UI_DISCORD_BOT_TOKEN') or os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ bot token not found in environment variables")
        return
    
    # 初始化 bot（無 command_prefix，因為我們只想用 API）
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"✅ Bot ready as {bot.user}")
        
        try:
            # 讀取所有有 locker_message_id 的用戶
            all_users = get_all_users()
            total = len([u for u in all_users if u.get('locker_message_id')])
            print(f"📊 開始更新 {total} 個置物櫃...\n")
            
            updated = 0
            failed = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id')
                locker_message_id = user_data.get('locker_message_id')
                
                if not user_id or not thread_id or not locker_message_id:
                    continue
                
                try:
                    # 獲取 thread 和 message
                    thread = bot.get_channel(thread_id)
                    if not thread:
                        try:
                            thread = await bot.fetch_channel(thread_id)
                        except:
                            continue
                    
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    if getattr(thread, 'archived', False):
                        continue
                    
                    try:
                        message = await thread.fetch_message(locker_message_id)
                    except:
                        continue
                    
                    if not message:
                        continue
                    
                    # 直接生成新 embed（動態生成 API URL，無 image_source field）
                    from uicommands.utils.image_utils import build_maplestory_api_url
                    
                    user = bot.get_user(user_id) or await bot.fetch_user(user_id)
                    if not user:
                        continue
                    
                    # 簡單 embed（核心是圖片 URL）
                    embed = discord.Embed(
                        title=f"📊 {user.display_name or user.name} 的置物櫃",
                        color=0x00ff88,
                        timestamp=discord.utils.utcnow()
                    )
                    try:
                        embed.set_thumbnail(url=user.display_avatar.url)
                    except:
                        pass
                    
                    # 動態生成 API URL
                    api_url = build_maplestory_api_url(user_data, animated=True)
                    embed.set_image(url=api_url)
                    # ⬆️ 不添加 image_source field
                    
                    embed.add_field(name="🆔 使用者ID", value=f"`{user_data['user_id']}`", inline=True)
                    embed.add_field(name="⭐ 等級", value=f"**{user_data['level'] or 1}**", inline=True)
                    embed.add_field(name="✨ 經驗值", value=f"{user_data['xp'] or 0} XP", inline=True)
                    embed.add_field(name="💰 金錢", value=f"{user_data['kkcoin'] or 0} KKCoin", inline=True)
                    embed.add_field(name="🏆 職位", value=user_data['title'] or '新手', inline=True)
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    
                    # 簡化：只顯示核心數據（完整版參考 create_user_embed）
                    embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
                    
                    # 更新 message
                    await message.edit(embed=embed)
                    updated += 1
                    print(f"✅ {updated}. user_id={user_id}")
                    
                    await asyncio.sleep(0.5)  # 避免 rate limit
                    
                except Exception as e:
                    failed += 1
                    print(f"❌ user_id={user_id}: {e}")
                    continue
            
            print(f"\n📈 完成！更新={updated}, 失敗={failed}")
        
        except Exception as e:
            print(f"❌ 錯誤: {e}")
        finally:
            await bot.close()
    
    await bot.start(token)

if __name__ == '__main__':
    asyncio.run(main())
