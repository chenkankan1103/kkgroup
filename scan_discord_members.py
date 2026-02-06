#!/usr/bin/env python3
"""
從 Discord 伺服器掃描所有成員的真實 ID
與資料庫中的 ID 進行對比，找出不匹配的情況
"""

import asyncio
import discord
from discord.ext import commands
import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
env_path = Path('/home/e193752468/kkgroup/.env')
if env_path.exists():
    load_dotenv(env_path)

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID') or os.getenv('SHOP_DISCORD_GUILD_ID') or '1133112693356773416')
TOKEN = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('SHOP_DISCORD_BOT_TOKEN')

class DiscordScanner:
    def __init__(self):
        self.intents = discord.Intents.default()
        self.intents.members = True
        self.intents.guilds = True
        self.client = discord.Client(intents=self.intents)
        self.discord_members = {}
        self.db_users = {}
        
    async def scan_discord(self):
        """掃描 Discord 伺服器中的所有成員"""
        @self.client.event
        async def on_ready():
            print('=' * 100)
            print('🔗 Discord 機器人已連接')
            print('=' * 100)
            print()
            
            guild = self.client.get_guild(GUILD_ID)
            if not guild:
                print(f'❌ 無法找到 Guild: {GUILD_ID}')
                await self.client.close()
                return
            
            print(f'📡 Guild: {guild.name}')
            print(f'   ID: {guild.id}')
            print(f'   成員數: {guild.member_count}')
            print()
            
            # 掃描 Discord 成員
            print('⏳ 正在掃描 Discord 成員...')
            print()
            
            member_count = 0
            async for member in guild.fetch_members(limit=None):
                self.discord_members[member.id] = {
                    'id': member.id,
                    'name': member.name,
                    'display_name': member.display_name,
                    'nickname': member.nick,
                    'avatar_url': str(member.avatar.url) if member.avatar else None,
                    'bot': member.bot,
                }
                member_count += 1
            
            print(f'✅ 掃描完成: {member_count} 個成員')
            print()
            
            # 讀取資料庫
            self.load_database()
            
            # 對比
            self.compare_and_report()
            
            await self.client.close()
        
        try:
            await self.client.start(TOKEN)
        except Exception as e:
            print(f'❌ 連接失敗: {e}')
    
    def load_database(self):
        """從資料庫讀取用戶資訊"""
        print('📚 読取資料庫用戶...')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, nickname FROM users ORDER BY user_id')
        
        for user_id, nickname in cursor.fetchall():
            self.db_users[user_id] = {
                'id': user_id,
                'nickname': nickname,
            }
        
        conn.close()
        
        print(f'✅ 讀取完成: {len(self.db_users)} 個用戶')
        print()
    
    def compare_and_report(self):
        """對比 Discord 和資料庫中的用戶"""
        print('=' * 100)
        print('🔍 對比結果')
        print('=' * 100)
        print()
        
        # 在 Discord 中的真實 ID 列表
        discord_ids = set(self.discord_members.keys())
        db_ids = set(self.db_users.keys())
        
        # 在資料庫但不在 Discord 的用戶
        missing_in_discord = db_ids - discord_ids
        
        # 在 Discord 但不在資料庫的用戶
        extra_in_discord = discord_ids - db_ids
        
        # 都有的用戶
        both = db_ids & discord_ids
        
        print(f'📊 總計:')
        print(f'   Discord 成員: {len(discord_ids)}')
        print(f'   資料庫用戶: {len(db_ids)}')
        print(f'   匹配: {len(both)}')
        print()
        
        if missing_in_discord:
            print(f'❌ 在資料庫但不在 Discord 伺服器的用戶 ({len(missing_in_discord)} 個):')
            print()
            for user_id in sorted(missing_in_discord):
                nick = self.db_users[user_id]['nickname']
                print(f'   {nick}: {user_id}')
            print()
        else:
            print(f'✅ 所有資料庫用戶都在 Discord 伺服器中')
            print()
        
        if extra_in_discord:
            print(f'⚠️  在 Discord 但不在資料庫的用戶 ({len(extra_in_discord)} 個):')
            print()
            for member_id in sorted(extra_in_discord):
                member = self.discord_members[member_id]
                print(f'   {member["display_name"]:30} ({member["name"]:20}): {member_id}')
            print()
        else:
            print(f'✅ 沒有多餘的 Discord 成員')
            print()
        
        # 詳細列表
        print('=' * 100)
        print('📋 詳細成員列表')
        print('=' * 100)
        print()
        
        print(f'{"#":<3} {"昵稱":<25} {"Discord 名稱":<25} {"ID (資料庫)":<20} {"ID (Discord)":<20} {"狀態":<10}')
        print('-' * 100)
        
        all_nicknames = set()
        for uid, user in self.db_users.items():
            if user['nickname']:
                all_nicknames.add(user['nickname'])
        
        row = 1
        for nick in sorted(all_nicknames):
            # 從資料庫找出該昵稱
            db_user = None
            for uid, user in self.db_users.items():
                if user['nickname'] == nick:
                    db_user = user
                    break
            
            if db_user:
                db_id = db_user['id']
                
                # 嘗試從 Discord 找出該用戶
                discord_member = None
                if db_id in self.discord_members:
                    discord_member = self.discord_members[db_id]
                else:
                    # 嘗試通過昵稱查找
                    for member in self.discord_members.values():
                        if member['display_name'].lower() == nick.lower() or member['name'].lower() == nick.lower():
                            discord_member = member
                            break
                
                if discord_member:
                    discord_id = discord_member['id']
                    discord_name = discord_member['display_name']
                    
                    if db_id == discord_id:
                        status = '✅'
                    else:
                        status = '⚠️ 不符'
                    
                    print(f'{row:<3} {nick:<25} {discord_name:<25} {db_id:<20} {discord_id:<20} {status:<10}')
                else:
                    print(f'{row:<3} {nick:<25} {"[未找到]":<25} {db_id:<20} {"N/A":<20} {"❌ 缺失":<10}')
                
                row += 1
        
        print()
        print('=' * 100)
        print('✅ 掃描完成')

def main():
    scanner = DiscordScanner()
    asyncio.run(scanner.scan_discord())

if __name__ == '__main__':
    main()
