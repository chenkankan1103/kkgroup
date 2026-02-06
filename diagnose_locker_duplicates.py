#!/usr/bin/env python3
"""
置物櫃清理診斷工具 - 檢測重複ID和離開成員的遺留數據

功能：
1. 掃描 cannabis_plants 和 cannabis_inventory 中的重複用戶ID
2. 識別已離開伺服器的成員遺留的植物/庫存
3. 報告統計信息
4. 提供自動清理選項
"""

import sqlite3
import asyncio
import discord
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', '0'))
DB_PATH = './shop_commands/merchant/cannabis.db'

class LockerDiagnoser:
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        self.bot = discord.Client(intents=intents)
        self.guild = None
        self.valid_members = set()
        self.issues = {
            'duplicate_entries': [],
            'orphaned_plants': [],
            'orphaned_inventory': [],
            'duplicate_ids': {}
        }
    
    async def on_ready(self):
        """連接Discord後執行診斷"""
        print(f"✅ 已連接: {self.bot.user}")
        
        self.guild = self.bot.get_guild(GUILD_ID)
        if not self.guild:
            print(f"❌ 找不到伺服器: {GUILD_ID}")
            await self.bot.close()
            return
        
        print(f"📍 伺服器: {self.guild.name}\n")
        
        # 獲取現有成員
        print("🔄 獲取伺服器成員...")
        for member in self.guild.members:
            if not member.bot:
                self.valid_members.add(member.id)
        print(f"✅ 掃描了 {len(self.valid_members)} 位成員\n")
        
        # 診斷
        await self.diagnose()
        
        # 顯示報告
        self.show_report()
        
        await self.bot.close()
    
    async def diagnose(self):
        """執行診斷"""
        print("🔍 === 診斷置物櫃數據 ===\n")
        
        if not Path(DB_PATH).exists():
            print(f"⚠️ 數據庫不存在: {DB_PATH}")
            return
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 1️⃣ 檢查 cannabis_plants 表
        print("1️⃣ 掃描植物數據...")
        try:
            c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_plants'")
            if not c.fetchone()[0]:
                print("   ℹ️ cannabis_plants 表不存在\n")
            else:
                c.execute("SELECT id, user_id, seed_type, planted_at FROM cannabis_plants")
                plants = c.fetchall()
                print(f"   ✅ 發現 {len(plants)} 個植物記錄\n")
                
                # 統計重複ID
                user_counts = {}
                for plant_id, user_id, seed_type, planted_at in plants:
                    if user_id not in user_counts:
                        user_counts[user_id] = []
                    user_counts[user_id].append({
                        'plant_id': plant_id,
                        'seed_type': seed_type,
                        'planted_at': planted_at
                    })
                
                # 識別 orphaned 和重複
                for user_id, plant_list in user_counts.items():
                    if len(plant_list) > 1:
                        self.issues['duplicate_ids'][user_id] = plant_list
                        print(f"   ⚠️ 用戶 {user_id}: {len(plant_list)} 個植物")
                    
                    if user_id not in self.valid_members:
                        for plant in plant_list:
                            self.issues['orphaned_plants'].append({
                                'user_id': user_id,
                                'plant_id': plant['plant_id'],
                                'seed_type': plant['seed_type']
                            })
                
                if self.issues['orphaned_plants']:
                    print(f"   🗑️ 發現 {len(self.issues['orphaned_plants'])} 個孤立植物（用戶已離開）\n")
        
        except Exception as e:
            print(f"   ❌ 錯誤: {e}\n")
        
        # 2️⃣ 檢查 cannabis_inventory 表
        print("2️⃣ 掃描庫存數據...")
        try:
            c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_inventory'")
            if not c.fetchone()[0]:
                print("   ℹ️ cannabis_inventory 表不存在\n")
            else:
                c.execute("SELECT id, user_id, item_type, item_name, quantity FROM cannabis_inventory")
                inventory = c.fetchall()
                print(f"   ✅ 發現 {len(inventory)} 個庫存記錄\n")
                
                # 識別孤立庫存
                for inv_id, user_id, item_type, item_name, quantity in inventory:
                    if user_id not in self.valid_members:
                        self.issues['orphaned_inventory'].append({
                            'inv_id': inv_id,
                            'user_id': user_id,
                            'item_type': item_type,
                            'item_name': item_name,
                            'quantity': quantity
                        })
                
                if self.issues['orphaned_inventory']:
                    print(f"   🗑️ 發現 {len(self.issues['orphaned_inventory'])} 項孤立庫存（用戶已離開）\n")
        
        except Exception as e:
            print(f"   ❌ 錯誤: {e}\n")
        
        conn.close()
    
    def show_report(self):
        """顯示診斷報告"""
        print("\n" + "="*70)
        print("📊 === 置物櫃診斷報告 ===")
        print("="*70 + "\n")
        
        total_issues = (len(self.issues['orphaned_plants']) + 
                       len(self.issues['orphaned_inventory']) + 
                       len(self.issues['duplicate_ids']))
        
        if total_issues == 0:
            print("✅ 沒有發現任何問題！置物櫃數據完整。\n")
            return
        
        print(f"⚠️ 發現 {total_issues} 個問題\n")
        
        # 孤立植物
        if self.issues['orphaned_plants']:
            print(f"🗑️ === 孤立植物 ({len(self.issues['orphaned_plants'])}個) ===")
            for item in self.issues['orphaned_plants']:
                print(f"   - 用戶 {item['user_id']:18d} | 植物ID: {item['plant_id']} | {item['seed_type']}")
            print()
        
        # 孤立庫存
        if self.issues['orphaned_inventory']:
            print(f"🗑️ === 孤立庫存 ({len(self.issues['orphaned_inventory'])}項) ===")
            for item in self.issues['orphaned_inventory']:
                print(f"   - 用戶 {item['user_id']:18d} | {item['item_type']} | {item['item_name']} x{item['quantity']}")
            print()
        
        # 重複用戶ID
        if self.issues['duplicate_ids']:
            print(f"⚠️ === 重複成員ID ({len(self.issues['duplicate_ids'])}個用戶) ===")
            for user_id, plants in self.issues['duplicate_ids'].items():
                print(f"   - 用戶 {user_id:18d}: {len(plants)} 個植物")
            print()
        
        print("="*70)
        print("\n建議行動:")
        print("1. 刪除所有孤立數據（已離開成員）")
        print("2. 檢查重複成員ID是否合理（可能是重新加入）")
        print("3. 設置定期清理任務\n")

async def main():
    try:
        diagnoser = LockerDiagnoser()
        diagnoser.bot.event(diagnoser.on_ready)
        await diagnoser.bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
