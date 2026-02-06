"""
Discord User ID 修復工具
讀取 Discord guild 中的成員 ID + 昵稱，與 user_data.db 對比並修復偏差

步驟：
1. 拉取 Discord guild 中所有成員的真實 ID 和昵稱
2. 與 user_data.db 中的昵稱對比
3. 找出 user_id 偏差的成員
4. 創建 ID 映射表
5. 執行修復（更新所有表中的 user_id）
"""

import discord
from discord.ext import commands
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# 配置
GUILD_ID = 1133112693356773416
DB_PATH = './user_data.db'
MAPPING_FILE = './id_mapping_results.json'


class UserIDDiagnosisCog(commands.Cog):
    """用戶 ID 診斷和修復 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.real_members = {}  # {昵稱: 真實Discord ID}
        self.db_members = {}     # {昵稱: 資料庫ID}
        self.id_mapping = {}     # {資料庫ID: 真實ID}
        self.issues = []         # 發現的問題
    
    @commands.Cog.listener()
    async def on_ready(self):
        """機器人準備好時"""
        print("[UserIDDiagnosis] 用戶 ID 診斷工具已載入")
    
    @commands.command(name="診斷用戶ID", description="🔍 掃描並診斷 Discord 成員 ID 映射")
    async def diagnose_user_ids(self, ctx):
        """診斷用戶 ID 映射"""
        try:
            if not ctx.author.id in [ctx.guild.owner_id]:
                if not ctx.author.guild_permissions.administrator:
                    await ctx.send("❌ 只有管理員可以執行此命令", ephemeral=True)
                    return
            
            await ctx.defer()
            
            # 步驟 1: 從 Discord 讀取所有成員
            await ctx.followup.send("📥 正在讀取 Discord 成員列表...", ephemeral=True)
            
            self.guild = self.bot.get_guild(GUILD_ID)
            if not self.guild:
                await ctx.followup.send("❌ 無法連接到 guild", ephemeral=True)
                return
            
            # 收集 Discord 成員
            self.real_members = {}
            async for member in self.guild.fetch_members(limit=None):
                # 昵稱優先使用 nick，其次使用 name
                nickname = member.nick or member.name
                self.real_members[nickname] = member.id
            
            await ctx.followup.send(f"✅ 已讀取 {len(self.real_members)} 個 Discord 成員", ephemeral=True)
            
            # 步驟 2: 從資料庫讀取所有用戶
            await ctx.followup.send("📖 正在讀取資料庫中的用戶...", ephemeral=True)
            
            self.db_members = await self.read_db_users()
            await ctx.followup.send(f"✅ 已讀取 {len(self.db_members)} 個資料庫用戶", ephemeral=True)
            
            # 步驟 3: 對比並找出映射
            await ctx.followup.send("🔄 正在對比用戶昵稱...", ephemeral=True)
            
            self.id_mapping = await self.find_id_mappings()
            self.issues = await self.identify_issues()
            
            # 步驟 4: 生成報告
            report = await self.generate_report()
            
            # 發送報告
            embed = discord.Embed(
                title="🔍 用戶 ID 診斷報告",
                description=report,
                color=discord.Color.blue()
            )
            
            await ctx.followup.send(embed=embed, ephemeral=True)
            
            # 儲存結果
            self.save_results()
            
        except Exception as e:
            print(f"❌ 診斷失敗: {e}")
            import traceback
            traceback.print_exc()
            await ctx.followup.send(f"❌ 診斷失敗: {str(e)[:100]}", ephemeral=True)
    
    async def read_db_users(self) -> Dict[str, int]:
        """從資料庫讀取用戶昵稱和 ID"""
        users = {}
        
        if not Path(DB_PATH).exists():
            return users
        
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # 讀取所有用戶
            c.execute("SELECT user_id, nickname FROM user_data")
            rows = c.fetchall()
            
            for user_id, nickname in rows:
                if nickname and not nickname.startswith('test') and not nickname.startswith('Test'):
                    users[nickname] = user_id
            
            conn.close()
        except Exception as e:
            print(f"❌ 讀取資料庫失敗: {e}")
        
        return users
    
    async def find_id_mappings(self) -> Dict[int, int]:
        """
        找出 user_id 映射
        返回: {資料庫ID: 真實Discord ID}
        """
        mapping = {}
        
        # 完美匹配：昵稱相同
        for nickname, real_id in self.real_members.items():
            if nickname in self.db_members:
                db_id = self.db_members[nickname]
                if db_id != real_id:
                    # 找到偏差
                    mapping[db_id] = real_id
        
        return mapping
    
    async def identify_issues(self) -> List[Dict]:
        """識別所有問題"""
        issues = []
        
        # Issue 1: ID 偏差
        for db_id, real_id in self.id_mapping.items():
            offset = real_id - db_id
            
            # 找到相應的昵稱
            nickname = None
            for nick, uid in self.db_members.items():
                if uid == db_id:
                    nickname = nick
                    break
            
            issues.append({
                'type': 'id_offset',
                'nickname': nickname,
                'db_id': db_id,
                'real_id': real_id,
                'offset': offset
            })
        
        # Issue 2: 資料庫中有但 Discord 沒有的用戶
        for nickname, db_id in self.db_members.items():
            if nickname not in self.real_members:
                issues.append({
                    'type': 'missing_in_discord',
                    'nickname': nickname,
                    'db_id': db_id
                })
        
        # Issue 3: Discord 中有但資料庫沒有的用戶
        for nickname, real_id in self.real_members.items():
            if nickname not in self.db_members:
                issues.append({
                    'type': 'missing_in_db',
                    'nickname': nickname,
                    'real_id': real_id
                })
        
        return issues
    
    async def generate_report(self) -> str:
        """生成診斷報告"""
        report = f"""
**成員掃描結果**
• Discord 成員總數: {len(self.real_members)}
• 資料庫用戶總數: {len(self.db_members)}

**ID 偏差情況**
• 找到偏差: {len(self.id_mapping)} 個

"""
        
        # 列出偏差
        if self.id_mapping:
            offsets = {}
            for db_id, real_id in self.id_mapping.items():
                offset = real_id - db_id
                if offset not in offsets:
                    offsets[offset] = 0
                offsets[offset] += 1
            
            report += "**偏差分佈**\n"
            for offset, count in sorted(offsets.items()):
                report += f"• {offset:+d} 的用戶: {count} 個\n"
            
            report += "\n**偏差詳情 (前10個)**\n"
            for idx, (db_id, real_id) in enumerate(list(self.id_mapping.items())[:10]):
                nick = None
                for n, uid in self.db_members.items():
                    if uid == db_id:
                        nick = n
                        break
                offset = real_id - db_id
                report += f"• {nick}: {db_id} → {real_id} ({offset:+d})\n"
        
        # 缺失的用戶
        missing_discord = [i for i in self.issues if i['type'] == 'missing_in_discord']
        missing_db = [i for i in self.issues if i['type'] == 'missing_in_db']
        
        if missing_discord:
            report += f"\n**只在資料庫中 (無法在 Discord 匹配)**: {len(missing_discord)} 個\n"
        
        if missing_db:
            report += f"**只在 Discord 中 (未在資料庫)**: {len(missing_db)} 個\n"
        
        return report
    
    def save_results(self):
        """保存診斷結果"""
        try:
            results = {
                'timestamp': datetime.now().isoformat(),
                'discord_members': self.real_members,
                'db_members': self.db_members,
                'id_mapping': self.id_mapping,
                'issues_summary': {
                    'total_offsets': len(self.id_mapping),
                    'missing_in_discord': len([i for i in self.issues if i['type'] == 'missing_in_discord']),
                    'missing_in_db': len([i for i in self.issues if i['type'] == 'missing_in_db'])
                }
            }
            
            with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 結果已保存到 {MAPPING_FILE}")
        except Exception as e:
            print(f"❌ 保存結果失敗: {e}")
    
    @commands.command(name="修復用戶ID", description="🔧 執行用戶 ID 修復 (需管理員)")
    async def fix_user_ids(self, ctx):
        """修復用戶 ID"""
        try:
            if not ctx.guild.owner_id == ctx.author.id:
                if not ctx.author.guild_permissions.administrator:
                    await ctx.send("❌ 只有管理員可以執行此命令", ephemeral=True)
                    return
            
            # 檢查是否有映射結果
            if not Path(MAPPING_FILE).exists():
                await ctx.send("❌ 請先執行 `/診斷用戶ID` 命令", ephemeral=True)
                return
            
            if not self.id_mapping:
                await ctx.send("✅ 沒有發現 ID 偏差，無需修復", ephemeral=True)
                return
            
            await ctx.defer()
            
            # 確認
            await ctx.send(f"⚠️ 將修復 {len(self.id_mapping)} 個用戶的 ID\n請確認操作...", ephemeral=True)
            
            # 執行修復
            success = await self.apply_fixes()
            
            if success:
                await ctx.followup.send(
                    f"✅ 修復完成！\n"
                    f"• 修復用戶數: {len(self.id_mapping)}\n"
                    f"• 備份已保存",
                    ephemeral=True
                )
            else:
                await ctx.followup.send("❌ 修復失敗", ephemeral=True)
        
        except Exception as e:
            print(f"❌ 執行修復失敗: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ 執行修復失敗: {str(e)[:100]}", ephemeral=True)
    
    async def apply_fixes(self) -> bool:
        """應用所有修復"""
        if not Path(DB_PATH).exists():
            print("❌ user_data.db 不存在")
            return False
        
        try:
            # 創建備份
            import shutil
            backup_path = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy(DB_PATH, backup_path)
            print(f"✅ 備份已創建: {backup_path}")
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # 更新 user_data 表
            for db_id, real_id in self.id_mapping.items():
                c.execute("UPDATE user_data SET user_id = ? WHERE user_id = ?", (real_id, db_id))
                count = c.rowcount
                if count > 0:
                    print(f"✅ user_data: {db_id} → {real_id} ({count} 條記錄)")
            
            # 更新其他表（如果存在）
            tables_to_update = ['cannabis_plants', 'cannabis_inventory', 'user_roles']
            
            for table in tables_to_update:
                try:
                    # 檢查表是否存在
                    c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                    if c.fetchone():
                        for db_id, real_id in self.id_mapping.items():
                            c.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = ?", (real_id, db_id))
                            count = c.rowcount
                            if count > 0:
                                print(f"✅ {table}: {db_id} → {real_id} ({count} 條記錄)")
                except Exception as e:
                    print(f"⚠️  無法更新表 {table}: {e}")
            
            conn.commit()
            conn.close()
            
            print(f"✅ 所有 {len(self.id_mapping)} 個用戶已修復")
            return True
        
        except Exception as e:
            print(f"❌ 應用修復失敗: {e}")
            return False


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(UserIDDiagnosisCog(bot))
    print("✅ [Bot] 用戶 ID 診斷工具已載入")
