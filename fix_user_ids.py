#!/usr/bin/env python3
"""
Discord ID 修正工具

功能：
1. 修正可疑的ID配對
2. 補充缺失的昵稱
3. 刪除測試ID
4. 新增缺失的Discord成員
"""

import sqlite3
import os
import asyncio
import discord
import json
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', '0'))
DB_PATH = './user_data.db'

class IDFixer:
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        self.guild = None
        self.db_members = {}
        self.discord_members = {}
        self.operations = {
            'fixed_ids': [],
            'added_nicknames': [],
            'removed_test_ids': [],
            'added_members': []
        }
    
    async def on_ready(self):
        """連接Discord後執行修正"""
        print(f"✅ 已連接: {self.bot.user}")
        
        self.guild = self.bot.get_guild(GUILD_ID)
        if not self.guild:
            print(f"❌ 找不到伺服器: {GUILD_ID}")
            await self.bot.close()
            return
        
        print(f"📍 伺服器: {self.guild.name}")
        
        # 獲取成員信息
        await self.fetch_discord_members()
        self.fetch_database_members()
        
        # 執行修正
        await self.fix_issues()
        
        # 應用變更
        self.apply_changes()
        
        # 顯示結果
        self.show_summary()
        
        await self.bot.close()
    
    async def fetch_discord_members(self):
        """從Discord獲取所有成員"""
        print(f"\n🔄 獲取Discord成員...")
        
        for member in self.guild.members:
            if not member.bot:
                self.discord_members[member.id] = {
                    'name': member.name,
                    'display_name': member.display_name,
                    'nick': member.nick,
                    'avatar_url': member.avatar.url if member.avatar else None
                }
        
        print(f"✅ 取得 {len(self.discord_members)} 位成員")
    
    def fetch_database_members(self):
        """從資料庫獲取所有用戶"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id, nickname FROM users")
            for row in cursor.fetchall():
                self.db_members[row['user_id']] = row['nickname']
            
            conn.close()
            print(f"✅ 資料庫中有 {len(self.db_members)} 個用戶")
        
        except Exception as e:
            print(f"❌ 讀取資料庫失敗: {e}")
    
    async def fix_issues(self):
        """執行修正"""
        print("\n" + "=" * 80)
        print("🔧 開始修正")
        print("=" * 80)
        
        # 1️⃣ 修正可疑的ID
        await self.fix_suspicious_ids()
        
        # 2️⃣ 補充缺失的昵稱
        await self.add_missing_nicknames()
        
        # 3️⃣ 刪除測試ID
        await self.remove_test_ids()
        
        # 4️⃣ 新增缺失的成員
        await self.add_missing_members()
    
    async def fix_suspicious_ids(self):
        """修正可疑的ID配對"""
        print("\n1️⃣ 檢查可疑的ID配對...")
        
        suspicious_pairs = self.find_suspicious_ids()
        
        if not suspicious_pairs:
            print("  ✅ 沒有可疑的ID配對")
            return
        
        print(f"  🔎 找到 {len(suspicious_pairs)} 個可疑配對:")
        
        for i, (discord_id, (db_id, diff, discord_name, db_name)) in enumerate(suspicious_pairs.items(), 1):
            print(f"\n  [{i}] Discord {discord_id} ({discord_name}) 可能是 DB {db_id} ({db_name})?")
            print(f"      ID差值: {diff}")
            
            # 將Discord ID複製到可疑的DB記錄
            self.operations['fixed_ids'].append({
                'old_id': db_id,
                'new_id': discord_id,
                'nickname': db_name,
                'reason': f'可疑配對 (昵稱: {db_name})'
            })
    
    async def add_missing_nicknames(self):
        """補充缺失的昵稱"""
        print("\n2️⃣ 補充缺失的昵稱...")
        
        missing = {}
        for db_id in self.db_members.keys():
            if (not self.db_members[db_id] or self.db_members[db_id].strip() == '') and db_id in self.discord_members:
                missing[db_id] = self.discord_members[db_id]
        
        if not missing:
            print("  ✅ 沒有缺失的昵稱")
            return
        
        print(f"  📝 補充 {len(missing)} 個缺失的昵稱:")
        
        for db_id, member_info in missing.items():
            new_nick = member_info['display_name']
            print(f"    ✅ {db_id:18d} -> {new_nick}")
            
            self.operations['added_nicknames'].append({
                'user_id': db_id,
                'nickname': new_nick
            })
    
    async def remove_test_ids(self):
        """刪除測試ID"""
        print("\n3️⃣ 識別並刪除測試ID...")
        
        test_ids = self.find_test_ids()
        
        if not test_ids:
            print("  ✅ 沒有測試ID")
            return
        
        print(f"  🧪 找到 {len(test_ids)} 個測試ID:")
        
        for test_id in sorted(test_ids):
            nick = self.db_members.get(test_id, 'N/A')
            print(f"    🗑️ {test_id:18d} | {nick}")
            self.operations['removed_test_ids'].append(test_id)
    
    async def add_missing_members(self):
        """新增缺失的Discord成員到資料庫"""
        print("\n4️⃣ 新增缺失的Discord成員...")
        
        missing_in_db = {}
        for discord_id, member_info in self.discord_members.items():
            if discord_id not in self.db_members:
                missing_in_db[discord_id] = member_info
        
        if not missing_in_db:
            print("  ✅ 沒有缺失的成員")
            return
        
        print(f"  ➕ 新增 {len(missing_in_db)} 個成員到資料庫:")
        
        for discord_id, member_info in missing_in_db.items():
            nick = member_info['display_name']
            print(f"    ✅ {discord_id:18d} | {nick}")
            
            self.operations['added_members'].append({
                'user_id': discord_id,
                'nickname': nick,
                'avatar_url': member_info['avatar_url']
            })
    
    def apply_changes(self):
        """應用所有變更到資料庫"""
        print("\n" + "=" * 80)
        print("💾 應用變更到資料庫")
        print("=" * 80)
        
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 修正ID
            for op in self.operations['fixed_ids']:
                print(f"\n🔧 修正ID: {op['old_id']} -> {op['new_id']}")
                try:
                    # 獲取舊ID的所有數據
                    cursor.execute("SELECT * FROM users WHERE user_id = ?", (op['old_id'],))
                    old_data = cursor.fetchone()
                    
                    if old_data:
                        # 刪除新ID（如果存在）
                        cursor.execute("DELETE FROM users WHERE user_id = ?", (op['new_id'],))
                        
                        # 更新舊記錄的user_id
                        cursor.execute("UPDATE users SET user_id = ? WHERE user_id = ?", 
                                     (op['new_id'], op['old_id']))
                        print(f"  ✅ {op['old_id']} 已改為 {op['new_id']}")
                except Exception as e:
                    print(f"  ❌ 錯誤: {e}")
            
            # 補充昵稱
            for op in self.operations['added_nicknames']:
                print(f"\n📝 補充昵稱: {op['user_id']} -> {op['nickname']}")
                try:
                    cursor.execute("UPDATE users SET nickname = ? WHERE user_id = ?",
                                 (op['nickname'], op['user_id']))
                    print(f"  ✅ 已補充")
                except Exception as e:
                    print(f"  ❌ 錯誤: {e}")
            
            # 刪除測試ID
            for test_id in self.operations['removed_test_ids']:
                print(f"\n🗑️ 刪除測試ID: {test_id}")
                try:
                    cursor.execute("DELETE FROM users WHERE user_id = ?", (test_id,))
                    print(f"  ✅ 已刪除")
                except Exception as e:
                    print(f"  ❌ 錯誤: {e}")
            
            # 新增成員
            for op in self.operations['added_members']:
                print(f"\n➕ 新增成員: {op['user_id']} | {op['nickname']}")
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO users (user_id, nickname, _created_at, _updated_at)
                        VALUES (?, ?, datetime('now'), datetime('now'))
                    """, (op['user_id'], op['nickname']))
                    print(f"  ✅ 已新增")
                except Exception as e:
                    print(f"  ❌ 錯誤: {e}")
            
            # 提交變更
            conn.commit()
            conn.close()
            
            print("\n✅ 所有變更已提交到資料庫")
        
        except Exception as e:
            print(f"❌ 應用變更失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def find_suspicious_ids(self):
        """找出可疑的ID配對"""
        suspicious = {}
        
        for discord_id in self.discord_members.keys():
            if discord_id in self.db_members:
                continue
            
            for db_id in self.db_members.keys():
                diff = abs(discord_id - db_id)
                if 0 < diff <= 500:
                    discord_name = self.discord_members[discord_id]['display_name'].lower()
                    db_name = (self.db_members[db_id] or "").lower()
                    
                    if db_name and (db_name in discord_name or discord_name in db_name):
                        if discord_id not in suspicious:
                            suspicious[discord_id] = (db_id, diff, 
                                                    self.discord_members[discord_id]['display_name'],
                                                    db_name)
        
        return suspicious
    
    def find_test_ids(self):
        """找出測試ID"""
        test_ids = []
        
        for db_id in self.db_members.keys():
            # 短ID
            if db_id < 100000000000000000:
                test_ids.append(db_id)
                continue
            
            # 測試昵稱
            nick = self.db_members[db_id] or ""
            test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB', 'Test_User']
            if any(pattern in nick for pattern in test_patterns):
                test_ids.append(db_id)
        
        return test_ids
    
    def show_summary(self):
        """顯示修正摘要"""
        print("\n" + "=" * 80)
        print("📊 修正摘要")
        print("=" * 80)
        
        print(f"\n✅ 已完成的修正：")
        print(f"  修正ID: {len(self.operations['fixed_ids'])}")
        print(f"  補充昵稱: {len(self.operations['added_nicknames'])}")
        print(f"  刪除測試ID: {len(self.operations['removed_test_ids'])}")
        print(f"  新增成員: {len(self.operations['added_members'])}")

async def main():
    try:
        fixer = IDFixer()
        fixer.bot.event(fixer.on_ready)
        
        await fixer.bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
