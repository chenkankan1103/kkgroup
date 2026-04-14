"""
置物櫃自動診斷和清理 Cog - 每天自動檢查並清理孤立數據

在 uibot.py 中自動加載作為 uicommands 模塊
"""

import discord
from discord.ext import commands, tasks
import sqlite3
from pathlib import Path
from datetime import datetime, time
import traceback
import os

# 確定數據庫路徑
DB_PATH = './shop_commands/merchant/cannabis.db'


class LockerMaintenanceCog(commands.Cog):
    """置物櫃自動維護 - UIBot 集成（每天執行）"""
    
    def __init__(self, bot):
        self.bot = bot
        self.checks_performed = 0
        self.items_cleaned = 0
        self.last_run = None
        
        # 啟動每天檢查任務
        self.daily_locker_check.start()
    
    def cog_unload(self):
        self.daily_locker_check.cancel()
    
    @tasks.loop(hours=24)  # 每天（24小時）
    async def daily_locker_check(self):
        """每天檢查並清理孤立數據"""
        try:
            print("\n" + "="*70)
            print("🧹 每日置物櫃維護任務啟動 (UIBot)")
            print("="*70 + "\n")
            
            if not Path(DB_PATH).exists():
                print(f"⚠️ 數據庫不存在: {DB_PATH}")
                return
            
            total_cleaned = 0
            
            # 獲取伺服器和成員列表
            for guild in self.bot.guilds:
                valid_members = set()
                for member in guild.members:
                    if not member.bot:
                        valid_members.add(member.id)
                
                # 清理孤立數據
                cleaned = await self.cleanup_orphaned_data(valid_members)
                total_cleaned += cleaned
                
                if cleaned > 0:
                    print(f"✅ 在伺服器 {guild.name} 中清理了 {cleaned} 項孤立數據")
                
                self.items_cleaned += cleaned
            
            self.checks_performed += 1
            
            # 日誌記錄
            self.last_run = datetime.now()
            print(f"\n✅ 檢查完成（第 {self.checks_performed} 次）")
            print(f"📊 本次清理: {total_cleaned} 項")
            print(f"📈 總計清理: {self.items_cleaned} 項")
            print(f"⏰ 接下來重啟可能還會進行檢查\n")
        
        except Exception as e:
            print(f"❌ 檢查失敗: {e}")
            traceback.print_exc()
    
    @daily_locker_check.before_loop
    async def before_daily_check(self):
        """等待機器人準備好"""
        await self.bot.wait_until_ready()
    
    async def cleanup_orphaned_data(self, valid_members: set) -> int:
        """
        清理孤立數據
        
        返回清理的項目計數
        """
        cleaned_count = 0
        
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # 清理孤立植物
            try:
                c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_plants'")
                if c.fetchone()[0]:
                    c.execute("SELECT id, user_id FROM cannabis_plants")
                    orphaned_plants = [pid for pid, uid in c.fetchall() if uid not in valid_members]
                    
                    for plant_id in orphaned_plants:
                        c.execute("DELETE FROM cannabis_plants WHERE id = ?", (plant_id,))
                        cleaned_count += 1
                    
                    if orphaned_plants:
                        conn.commit()
            
            except Exception as e:
                print(f"   ℹ️ cannabis_plants 表檢查失敗或不存在: {e}")
            
            # 清理孤立庫存
            try:
                c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_inventory'")
                if c.fetchone()[0]:
                    c.execute("SELECT id, user_id FROM cannabis_inventory")
                    orphaned_inventory = [iid for iid, uid in c.fetchall() if uid not in valid_members]
                    
                    for inv_id in orphaned_inventory:
                        c.execute("DELETE FROM cannabis_inventory WHERE id = ?", (inv_id,))
                        cleaned_count += 1
                    
                    if orphaned_inventory:
                        conn.commit()
            
            except Exception as e:
                print(f"   ℹ️ cannabis_inventory 表檢查失敗或不存在: {e}")
            
            conn.close()
        
        except Exception as e:
            print(f"❌ 清理過程出錯: {e}")
            traceback.print_exc()
        
        return cleaned_count
    



async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(LockerMaintenanceCog(bot))
    print("✅ [UIBot] 置物櫃維護任務已載入")
