#!/usr/bin/env python3
"""
置物櫃自動清理工具

功能：
1. 刪除已離開成員的植物記錄
2. 刪除已離開成員的庫存記錄
3. 保留重複成員ID的數據（需要手動確認）
4. 記錄所有刪除操作
"""

import sqlite3
import asyncio
import discord
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', '0'))
DB_PATH = './shop_commands/merchant/cannabis.db'

class LockerCleaner:
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        self.bot = discord.Client(intents=intents)
        self.guild = None
        self.valid_members = set()
        self.cleanup_log = {
            'deleted_plants': [],
            'deleted_inventory': [],
            'timestamp': datetime.now().isoformat()
        }
    
    async def on_ready(self):
        """連接Discord後執行清理"""
        print(f"✅ 已連接: {self.bot.user}")
        
        self.guild = self.bot.get_guild(GUILD_ID)
        if not self.guild:
            print(f"❌ 找不到伺服器: {GUILD_ID}")
            await self.bot.close()
            return
        
        # 獲取現有成員
        print(f"📍 掃描伺服器成員...")
        for member in self.guild.members:
            if not member.bot:
                self.valid_members.add(member.id)
        print(f"✅ 發現 {len(self.valid_members)} 位活躍成員\n")
        
        # 清理
        await self.cleanup()
        
        # 顯示報告
        self.show_summary()
        
        await self.bot.close()
    
    async def cleanup(self):
        """執行清理"""
        print("🧹 === 清理置物櫃數據 ===\n")
        
        if not Path(DB_PATH).exists():
            print(f"⚠️ 數據庫不存在: {DB_PATH}")
            return
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 1️⃣ 清理孤立植物
        print("1️⃣ 清理孤立植物...")
        try:
            c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_plants'")
            if c.fetchone()[0]:
                # 找出所有孤立植物
                c.execute("SELECT id, user_id, seed_type FROM cannabis_plants")
                plants = c.fetchall()
                
                orphaned_count = 0
                for plant_id, user_id, seed_type in plants:
                    if user_id not in self.valid_members:
                        c.execute("DELETE FROM cannabis_plants WHERE id = ?", (plant_id,))
                        self.cleanup_log['deleted_plants'].append({
                            'plant_id': plant_id,
                            'user_id': user_id,
                            'seed_type': seed_type
                        })
                        orphaned_count += 1
                
                if orphaned_count > 0:
                    conn.commit()
                    print(f"   ✅ 刪除了 {orphaned_count} 個孤立植物\n")
                else:
                    print(f"   ✅ 沒有孤立植物\n")
        
        except Exception as e:
            print(f"   ❌ 錯誤: {e}\n")
        
        # 2️⃣ 清理孤立庫存
        print("2️⃣ 清理孤立庫存...")
        try:
            c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_inventory'")
            if c.fetchone()[0]:
                # 找出所有孤立庫存
                c.execute("SELECT id, user_id, item_type, item_name, quantity FROM cannabis_inventory")
                inventory = c.fetchall()
                
                orphaned_count = 0
                for inv_id, user_id, item_type, item_name, quantity in inventory:
                    if user_id not in self.valid_members:
                        c.execute("DELETE FROM cannabis_inventory WHERE id = ?", (inv_id,))
                        self.cleanup_log['deleted_inventory'].append({
                            'inv_id': inv_id,
                            'user_id': user_id,
                            'item_type': item_type,
                            'item_name': item_name,
                            'quantity': quantity
                        })
                        orphaned_count += 1
                
                if orphaned_count > 0:
                    conn.commit()
                    print(f"   ✅ 刪除了 {orphaned_count} 項孤立庫存\n")
                else:
                    print(f"   ✅ 沒有孤立庫存\n")
        
        except Exception as e:
            print(f"   ❌ 錯誤: {e}\n")
        
        conn.close()
    
    def show_summary(self):
        """顯示清理摘要"""
        print("="*70)
        print("📊 === 清理摘要 ===")
        print("="*70 + "\n")
        
        total_deleted = len(self.cleanup_log['deleted_plants']) + len(self.cleanup_log['deleted_inventory'])
        
        if total_deleted == 0:
            print("✅ 沒有需要清理的數據\n")
            return
        
        print(f"✅ 成功清理 {total_deleted} 項數據\n")
        
        if self.cleanup_log['deleted_plants']:
            print(f"🗑️ 已刪除植物: {len(self.cleanup_log['deleted_plants'])} 個")
            for item in self.cleanup_log['deleted_plants'][:5]:  # 顯示前5個
                print(f"   - 植物ID: {item['plant_id']} | 用戶: {item['user_id']}")
            if len(self.cleanup_log['deleted_plants']) > 5:
                print(f"   ... 還有 {len(self.cleanup_log['deleted_plants']) - 5} 個")
            print()
        
        if self.cleanup_log['deleted_inventory']:
            print(f"🗑️ 已刪除庫存: {len(self.cleanup_log['deleted_inventory'])} 項")
            for item in self.cleanup_log['deleted_inventory'][:5]:  # 顯示前5個
                print(f"   - {item['item_type']} | {item['item_name']} x{item['quantity']}")
            if len(self.cleanup_log['deleted_inventory']) > 5:
                print(f"   ... 還有 {len(self.cleanup_log['deleted_inventory']) - 5} 項")
            print()
        
        print("="*70 + "\n")

async def main():
    try:
        cleaner = LockerCleaner()
        cleaner.bot.event(cleaner.on_ready)
        await cleaner.bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
