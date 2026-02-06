#!/usr/bin/env python3
"""
驗證 Discord 成員與資料庫同步狀態
檢查資料庫中的所有用戶是否真的在 Discord guild 中
"""

import sqlite3
import asyncio
import discord
import sys
from pathlib import Path

# 讀取配置
CONFIG_PATH = Path('/home/e193752468/kkgroup/shop_config.py')
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config_content = f.read()
        exec(config_content)

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
GUILD_ID = 1133112693356773416

async def verify_members():
    """驗證所有成員"""
    
    # 建立簡單的 Discord 客戶端
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print('✅ Discord 連線成功')
        
        # 獲取 guild
        guild = client.get_guild(GUILD_ID)
        if not guild:
            print(f'❌ 無法找到 guild {GUILD_ID}')
            await client.close()
            return
        
        print(f'📡 Guild: {guild.name} ({guild.id})')
        print(f'   成員數: {guild.member_count}')
        print()
        
        # 讀取資料庫
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, nickname FROM users ORDER BY user_id')
        db_users = cursor.fetchall()
        conn.close()
        
        print(f'📊 資料庫用戶: {len(db_users)}')
        print()
        
        # 獲取 Discord 成員
        print('⏳ 正在獲取 Discord 成員列表...')
        discord_members = {}
        async for member in guild.fetch_members(limit=None):
            discord_members[member.id] = member
        
        print(f'✅ Discord 成員: {len(discord_members)}')
        print()
        
        # 檢查
        print('🔍 檢查對應關係:')
        print()
        
        missing_in_discord = []
        found_in_discord = []
        
        for user_id, nick in db_users:
            if user_id in discord_members:
                member = discord_members[user_id]
                found_in_discord.append((user_id, nick, member.name))
            else:
                missing_in_discord.append((user_id, nick))
        
        print(f'✅ 在 Discord 中找到: {len(found_in_discord)}/{len(db_users)}')
        print(f'❌ 在 Discord 中缺失: {len(missing_in_discord)}/{len(db_users)}')
        print()
        
        if missing_in_discord:
            print('👻 缺失的用戶:')
            for user_id, nick in missing_in_discord:
                print(f'   {nick}: {user_id}')
            print()
        
        # 檢查頭像問題
        print('🎨 檢查頭像狀態:')
        no_avatar = []
        has_avatar = []
        
        for user_id, nick, discord_name in found_in_discord:
            member = discord_members[user_id]
            if member.avatar:
                has_avatar.append((user_id, nick))
            else:
                no_avatar.append((user_id, nick, discord_name))
        
        print(f'✅ 有頭像: {len(has_avatar)}/{len(found_in_discord)}')
        print(f'❌ 無頭像: {len(no_avatar)}/{len(found_in_discord)}')
        
        if no_avatar:
            print()
            print('   無頭像的用戶:')
            for user_id, nick, discord_name in no_avatar:
                print(f'      {nick} ({discord_name}): {user_id}')
        
        print()
        print('=' * 80)
        print('✅ 驗證完成')
        
        await client.close()
    
    # 獲取 token
    token = None
    token_file = Path('/home/e193752468/kkgroup/.bot_token')
    if token_file.exists():
        token = token_file.read_text().strip()
    elif 'BOT_TOKEN' in locals():
        token = BOT_TOKEN
    else:
        print('❌ 無法找到 bot token')
        return
    
    try:
        await client.start(token)
    except Exception as e:
        print(f'❌ 連線失敗: {e}')

if __name__ == '__main__':
    asyncio.run(verify_members())
