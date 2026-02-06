"""
置物櫃定期檢測 Cog - 每周自動檢查並清理孤立數據

在 bot.py 中加載：
    await bot.load_extension('locker_maintenance')
"""

import discord
from discord.ext import commands, tasks
import sqlite3
from pathlib import Path
from datetime import datetime
import traceback

DB_PATH = './shop_commands/merchant/cannabis.db'


class LockerMaintenanceCog(commands.Cog):
    """置物櫃定期維護"""
    
    def __init__(self, bot):
        self.bot = bot
        self.checks_performed = 0
        self.items_cleaned = 0
        
        # 啟動每周檢查任務
        self.weekly_locker_check.start()
    
    def cog_unload(self):
        self.weekly_locker_check.cancel()
    
    @tasks.loop(hours=168)  # 每周（168小時）
    async def weekly_locker_check(self):
        """每周檢查並清理孤立數據"""
        try:
            print("\n" + "="*70)
            print("🧹 每周置物櫃維護任務啟動")
            print("="*70 + "\n")
            
            if not Path(DB_PATH).exists():
                print(f"⚠️ 數據庫不存在: {DB_PATH}")
                return
            
            # 獲取伺服器和成員列表
            for guild in self.bot.guilds:
                valid_members = set()
                for member in guild.members:
                    if not member.bot:
                        valid_members.add(member.id)
                
                # 清理孤立數據
                cleaned = await self.cleanup_orphaned_data(valid_members)
                
                if cleaned > 0:
                    print(f"✅ 在伺服器 {guild.name} 中清理了 {cleaned} 項孤立數據")
                
                self.items_cleaned += cleaned
            
            self.checks_performed += 1
            print(f"\n✅ 檢查完成（第 {self.checks_performed} 次）")
            print(f"📊 總共清理: {self.items_cleaned} 項\n")
        
        except Exception as e:
            print(f"❌ 檢查失敗: {e}")
            traceback.print_exc()
    
    @weekly_locker_check.before_loop
    async def before_weekly_check(self):
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
                    c.execute("SELECT id, user_id FROM cannabis_plants WHERE user_id NOT IN (SELECT ? FROM (VALUES (?)) AS t(id))")
                    
                    # 改用 in-memory 檢查
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
    
    @commands.command(name="檢查置物櫃", description="🔍 手動檢查置物櫃健康狀態")
    async def check_locker_health(self, ctx):
        """手動檢查置物櫃"""
        try:
            await ctx.defer()
            
            if not Path(DB_PATH).exists():
                embed = discord.Embed(
                    title="❌ 置物櫃數據庫不存在",
                    color=discord.Color.red()
                )
                await ctx.followup.send(embed=embed)
                return
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            plants_count = 0
            inventory_count = 0
            
            # 獲取植物數量
            try:
                c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_plants'")
                if c.fetchone()[0]:
                    c.execute("SELECT COUNT(*) FROM cannabis_plants")
                    plants_count = c.fetchone()[0]
            except:
                pass
            
            # 獲取庫存數量
            try:
                c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cannabis_inventory'")
                if c.fetchone()[0]:
                    c.execute("SELECT COUNT(*) FROM cannabis_inventory")
                    inventory_count = c.fetchone()[0]
            except:
                pass
            
            conn.close()
            
            embed = discord.Embed(
                title="🔍 置物櫃健康檢查",
                description="置物櫃數據庫狀態",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📊 統計信息",
                value=f"🌱 植物記錄: {plants_count}\n📦 庫存項目: {inventory_count}\n",
                inline=False
            )
            
            embed.add_field(
                name="🔄 自動維護",
                value=f"✅ 已執行檢查: {self.checks_performed} 次\n🧹 已清理項目: {self.items_cleaned} 項",
                inline=False
            )
            
            embed.add_field(
                name="📅 下次檢查",
                value=f"<t:{int((datetime.now().timestamp() + 604800))}:F>",
                inline=False
            )
            
            await ctx.followup.send(embed=embed)
        
        except Exception as e:
            await ctx.followup.send(f"❌ 檢查失敗: {str(e)[:100]}")
            traceback.print_exc()


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(LockerMaintenanceCog(bot))
    print("✅ 置物櫃維護任務已載入")
