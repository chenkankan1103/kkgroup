#!/usr/bin/env python3
"""
診斷Discord成員ID與資料庫的不一致問題

功能：
1. 從Discord獲取所有成員
2. 與SQLite資料庫對比
3. 找出ID錯誤（±500以內）的情況
4. 識別缺失和重複的昵稱
"""

import sqlite3
import os
import asyncio
import discord
from dotenv import load_dotenv
from pathlib import Path

# 載入環境變數
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', '0'))
DB_PATH = './user_data.db'

class IDDiagnoser:
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        self.guild = None
        self.db_members = {}  # 資料庫中的成員
        self.discord_members = {}  # Discord中的成員
        
    async def on_ready(self):
        """連接Discord後執行診斷"""
        print(f"✅ 已連接: {self.bot.user}")
        
        self.guild = self.bot.get_guild(GUILD_ID)
        if not self.guild:
            print(f"❌ 找不到伺服器: {GUILD_ID}")
            await self.bot.close()
            return
        
        print(f"\n📍 伺服器: {self.guild.name} ({self.guild.id})")
        
        # 1️⃣ 從Discord獲取所有成員
        await self.fetch_discord_members()
        
        # 2️⃣ 從資料庫獲取所有用戶
        self.fetch_database_members()
        
        # 3️⃣ 執行診斷
        await self.diagnose()
        
        await self.bot.close()
    
    async def fetch_discord_members(self):
        """從Discord獲取所有成員"""
        print(f"\n🔄 正在從Discord獲取成員... (共 {self.guild.member_count} 人)")
        
        for member in self.guild.members:
            if not member.bot:  # 跳過機器人
                self.discord_members[member.id] = {
                    'name': member.name,
                    'display_name': member.display_name,
                    'nick': member.nick,
                    'joined_at': member.joined_at
                }
        
        print(f"✅ 取得 {len(self.discord_members)} 位成員")
    
    def fetch_database_members(self):
        """從資料庫獲取所有用戶"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id, nickname FROM users ORDER BY user_id")
            rows = cursor.fetchall()
            
            for row in rows:
                self.db_members[row['user_id']] = row['nickname']
            
            conn.close()
            print(f"✅ 資料庫中有 {len(self.db_members)} 個用戶")
        
        except Exception as e:
            print(f"❌ 讀取資料庫失敗: {e}")
    
    async def diagnose(self):
        """執行ID診斷"""
        print("\n" + "=" * 80)
        print("🔍 Discord 成員 vs 資料庫 比對診斷")
        print("=" * 80)
        
        # 找出在Discord但不在資料庫的成員
        missing_in_db = {}
        for discord_id, member_info in self.discord_members.items():
            if discord_id not in self.db_members:
                missing_in_db[discord_id] = member_info
        
        # 找出在資料庫但不在Discord的用戶（可能是離開的成員）
        removed_from_discord = [uid for uid in self.db_members.keys() if uid not in self.discord_members]
        
        # 找出ID接近但不相同的情況（±500以內）
        suspicious_ids = self.find_suspicious_ids()
        
        # 找出沒有昵稱的成員
        missing_nicknames = self.find_missing_nicknames()
        
        # 找出測試ID
        test_ids = self.find_test_ids()
        
        # 📊 顯示診斷結果
        print(f"\n📊 診斷結果摘要：")
        print(f"  Discord成員: {len(self.discord_members)}")
        print(f"  資料庫用戶: {len(self.db_members)}")
        print(f"  缺失在資料庫: {len(missing_in_db)}")
        print(f"  已移除的成員: {len(removed_from_discord)}")
        print(f"  可疑的ID (±500): {len(suspicious_ids)}")
        print(f"  缺失昵稱: {len(missing_nicknames)}")
        print(f"  測試ID: {len(test_ids)}")
        
        # 顯示詳細信息
        if missing_in_db:
            print(f"\n❌ Discord中但不在資料庫的成員 ({len(missing_in_db)})：")
            for discord_id, member_info in sorted(missing_in_db.items())[:20]:
                print(f"  {discord_id:18d} | {member_info['display_name']:20s} | {member_info['name']}")
        
        if removed_from_discord:
            print(f"\n⚠️ 資料庫中但已離開伺服器的成員 ({len(removed_from_discord)})：")
            for uid in sorted(removed_from_discord)[:10]:
                print(f"  {uid:18d} | {self.db_members[uid]}")
        
        if suspicious_ids:
            print(f"\n🔎 可疑的ID配對 (±500差值)：")
            for discord_id, (db_id, diff) in sorted(suspicious_ids.items())[:20]:
                discord_name = self.discord_members[discord_id]['display_name']
                db_name = self.db_members.get(db_id, 'N/A')
                print(f"  Discord {discord_id} ({discord_name:20s}) ↔ DB {db_id} ({db_name}) | 差值: {diff}")
        
        if missing_nicknames:
            print(f"\n📝 資料庫中缺失昵稱的成員 ({len(missing_nicknames)})：")
            for db_id, discord_member in sorted(missing_nicknames.items())[:20]:
                print(f"  {db_id:18d} | {discord_member['display_name']}")
        
        if test_ids:
            print(f"\n🧪 測試ID ({len(test_ids)})：")
            for test_id in sorted(test_ids):
                nick = self.db_members.get(test_id, 'N/A')
                print(f"  {test_id:18d} | {nick}")
        
        # 生成修正建議
        print(f"\n💡 修正建議：")
        print(f"  1. 新增 {len(missing_in_db)} 個缺失的Discord成員到資料庫")
        if suspicious_ids:
            print(f"  2. ⚠️ 檢查並修正 {len(suspicious_ids)} 個可疑的ID配對")
        if missing_nicknames:
            print(f"  3. 補充 {len(missing_nicknames)} 個缺失的昵稱")
        if test_ids:
            print(f"  4. 刪除 {len(test_ids)} 個測試ID")
        if removed_from_discord:
            print(f"  5. 可選：清理 {len(removed_from_discord)} 個已離開的成員")
    
    def find_suspicious_ids(self):
        """找出ID相差±500以內的情況"""
        suspicious = {}
        
        for discord_id in self.discord_members.keys():
            if discord_id in self.db_members:
                continue  # 已經匹配，跳過
            
            # 在資料庫中尋找相近的ID
            for db_id in self.db_members.keys():
                if db_id in [self.db_members[uid] for uid in self.discord_members.keys()]:
                    continue  # 已經被其他Discord成員聲稱
                
                diff = abs(discord_id - db_id)
                if 0 < diff <= 500:
                    # 檢查昵稱相似性
                    discord_name = self.discord_members[discord_id]['display_name'].lower()
                    db_name = self.db_members[db_id].lower() if self.db_members[db_id] else ""
                    
                    # 如果昵稱相同或接近，則更可能是同一個人
                    if db_name and (db_name in discord_name or discord_name in db_name or db_name.split()[0] in discord_name):
                        suspicious[discord_id] = (db_id, diff)
        
        return suspicious
    
    def find_missing_nicknames(self):
        """找出資料庫中缺失昵稱的成員"""
        missing = {}
        
        for db_id in self.db_members.keys():
            if not self.db_members[db_id] and db_id in self.discord_members:
                missing[db_id] = self.discord_members[db_id]
        
        return missing
    
    def find_test_ids(self):
        """找出測試ID（短ID和特定昵稱）"""
        test_ids = []
        
        for db_id in self.db_members.keys():
            # 短ID（< 100000000000000000）
            if db_id < 100000000000000000:
                test_ids.append(db_id)
                continue
            
            # 特定昵稱模式
            nick = self.db_members[db_id] or ""
            test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB', 'Test_User']
            if any(pattern in nick for pattern in test_patterns):
                test_ids.append(db_id)
        
        return test_ids

async def main():
    try:
        diagnoser = IDDiagnoser()
        diagnoser.bot.event(diagnoser.on_ready)
        
        await diagnoser.bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
