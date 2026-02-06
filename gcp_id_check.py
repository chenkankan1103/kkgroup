#!/usr/bin/env python3
"""
進階 Discord ID 檢查
直接按 ID 匹配用戶
"""

import discord
import asyncio
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv('/home/e193752468/kkgroup/.env')
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = 1133112693356773416

async def advanced_check():
    intents = discord.Intents.default()
    intents.members = True
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        guild = client.get_guild(GUILD_ID)
        
        # 讀資料庫
        conn = sqlite3.connect('/home/e193752468/kkgroup/user_data.db')
        c = conn.cursor()
        c.execute('SELECT user_id, nickname FROM users ORDER BY user_id')
        db_users = c.fetchall()
        conn.close()
        
        # 讀 Discord 成員
        discord_members = {}
        async for member in guild.fetch_members(limit=None):
            discord_members[member.id] = {
                'nick': member.nick,
                'name': member.name,
                'display': member.nick or member.name
            }
        
        print('=== 高級比對結果 ===')
        print(f'資料庫用戶: {len(db_users)}')
        print(f'Discord 成員: {len(discord_members)}')
        print()
        
        # 按 ID 找到的直接匹配
        print('【方法1】按 ID 直接匹配:')
        matches_by_id = 0
        mismatches = []
        missing_ids = []
        
        for db_id, db_nick in db_users:
            if db_id in discord_members:
                matches_by_id += 1
                dc_display = discord_members[db_id]['display']
                # 檢查昵稱是否在 DC 昵稱中
                if db_nick not in dc_display and db_nick != dc_display:
                    mismatches.append((db_id, db_nick, dc_display))
            else:
                missing_ids.append((db_id, db_nick))
        
        print(f'  ✅ 成功: {matches_by_id} / {len(db_users)}')
        
        if missing_ids:
            print()
            print(f'❌ 找不到的ID ({len(missing_ids)} 個):')
            for db_id, db_nick in missing_ids[:5]:
                print(f'  {db_nick:25} (ID: {db_id})')
        
        if mismatches:
            print()
            print(f'⚠️  昵稱不匹配的ID ({len(mismatches)} 個):')
            for db_id, db_nick, dc_nick in mismatches[:10]:
                print(f'  DB: "{db_nick:25}" -> DC: "{dc_nick[:45]}"')
        
        await client.close()
    
    async with client:
        await client.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(advanced_check())
