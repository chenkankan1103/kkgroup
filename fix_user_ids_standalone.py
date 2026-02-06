#!/usr/bin/env python3
"""
獨立式 Discord User ID 修復工具
不需要機器人交互，直接診斷和修復 user_data.db 中的 ID 偏差

使用方式：
  python fix_user_ids_standalone.py diagnose          # 只診斷，不修復
  python fix_user_ids_standalone.py                   # 完整診斷和修復流程
"""

import discord
from discord.ext import commands
import sqlite3
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import os

# 配置
GUILD_ID = 1133112693356773416
DB_PATH = './user_data.db'
MAPPING_FILE = './id_mapping_results.json'


class UserIDFixer:
    """獨立的 User ID 修復工具"""
    
    def __init__(self, token: str):
        self.token = token
        self.real_members = {}  # {昵稱: 真實Discord ID}
        self.db_members = {}     # {昵稱: 資料庫ID}
        self.id_mapping = {}     # {資料庫ID: 真實ID}
        self.issues = []
        
        # 創建臨時 bot 用於 Discord 連接
        intents = discord.Intents.default()
        intents.members = True
        self.bot = commands.Bot(command_prefix='!', intents=intents)
    
    async def run_diagnosis(self) -> bool:
        """執行完整診斷"""
        try:
            async with self.bot:
                # 步驟 1: 拉取 Discord 成員
                print("\n" + "="*60)
                print("步驟 1: 正在讀取 Discord 成員...")
                print("="*60)
                
                try:
                    await self.bot.login(self.token)
                except Exception as e:
                    print(f"❌ 無法登入 Discord: {e}")
                    return False
                
                async def fetch_members():
                    guild = self.bot.get_guild(GUILD_ID)
                    if not guild:
                        print(f"❌ 無法找到 Guild {GUILD_ID}")
                        await self.bot.close()
                        return False
                    
                    print(f"✅ 已連接到 Guild: {guild.name}")
                    
                    count = 0
                    async for member in guild.fetch_members(limit=None):
                        nickname = member.nick or member.name
                        self.real_members[nickname] = member.id
                        count += 1
                    
                    print(f"✅ 已讀取 {count} 個 Discord 成員")
                    await self.bot.close()
                    return True
                
                await fetch_members()
        
        except Exception as e:
            print(f"❌ Discord 連接失敗: {e}")
            return False
        
        # 步驟 2: 讀取資料庫
        print("\n" + "="*60)
        print("步驟 2: 正在讀取資料庫用戶...")
        print("="*60)
        
        self.db_members = self.read_db_users()
        print(f"✅ 已讀取 {len(self.db_members)} 個資料庫用戶")
        
        # 步驟 3: 對比並找出映射
        print("\n" + "="*60)
        print("步驟 3: 對比用戶昵稱...")
        print("="*60)
        
        self.id_mapping = self.find_id_mappings()
        self.issues = self.identify_issues()
        
        # 步驟 4: 生成報告
        print("\n" + "="*60)
        print("診斷報告")
        print("="*60)
        
        report = self.generate_report()
        print(report)
        
        # 儲存結果
        self.save_results()
        
        return True
    
    def read_db_users(self) -> Dict[str, int]:
        """從資料庫讀取用戶"""
        users = {}
        
        if not Path(DB_PATH).exists():
            print(f"❌ {DB_PATH} 不存在")
            return users
        
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # 讀取所有用戶
            c.execute("SELECT user_id, nickname FROM user_data")
            rows = c.fetchall()
            
            for user_id, nickname in rows:
                if nickname and not str(nickname).startswith(('test', 'Test', 'TEST')):
                    users[nickname] = user_id
            
            conn.close()
        except Exception as e:
            print(f"❌ 讀取資料庫失敗: {e}")
        
        return users
    
    def find_id_mappings(self) -> Dict[int, int]:
        """找出 user_id 映射"""
        mapping = {}
        
        # 完美匹配：昵稱相同
        matched = 0
        for nickname, real_id in self.real_members.items():
            if nickname in self.db_members:
                db_id = self.db_members[nickname]
                if db_id != real_id:
                    mapping[db_id] = real_id
                    matched += 1
        
        print(f"✅ 找到 {matched} 個昵稱匹配的用戶")
        
        return mapping
    
    def identify_issues(self) -> List[Dict]:
        """識別問題"""
        issues = []
        
        # Issue 1: ID 偏差
        for db_id, real_id in self.id_mapping.items():
            offset = real_id - db_id
            
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
        
        # Issue 2: 資料庫有但 Discord 沒有
        for nickname, db_id in self.db_members.items():
            if nickname not in self.real_members:
                issues.append({
                    'type': 'missing_in_discord',
                    'nickname': nickname,
                    'db_id': db_id
                })
        
        # Issue 3: Discord 有但資料庫沒有
        for nickname, real_id in self.real_members.items():
            if nickname not in self.db_members:
                issues.append({
                    'type': 'missing_in_db',
                    'nickname': nickname,
                    'real_id': real_id
                })
        
        return issues
    
    def generate_report(self) -> str:
        """生成詳細報告"""
        report = f"""
成員掃描結果
═════════════════════════════════════════════════════════
• Discord 成員總數:     {len(self.real_members):>6}
• 資料庫用戶總數:       {len(self.db_members):>6}
• ID 偏差用戶數:        {len(self.id_mapping):>6}

ID 偏差詳情
═════════════════════════════════════════════════════════
"""
        
        if self.id_mapping:
            offsets = {}
            for db_id, real_id in self.id_mapping.items():
                offset = real_id - db_id
                if offset not in offsets:
                    offsets[offset] = 0
                offsets[offset] += 1
            
            report += "偏差分佈:\n"
            for offset, count in sorted(offsets.items()):
                report += f"  • {offset:+6d} 偏差: {count:>3} 個用戶\n"
            
            report += "\n偏差用戶列表 (前20個):\n"
            for idx, (db_id, real_id) in enumerate(sorted(self.id_mapping.items())[:20]):
                nick = None
                for n, uid in self.db_members.items():
                    if uid == db_id:
                        nick = n
                        break
                offset = real_id - db_id
                report += f"  {idx+1:2}. {nick:20} | DB:{db_id:>18} → {real_id:>18} ({offset:+d})\n"
        else:
            report += "✅ 沒有發現 ID 偏差！\n"
        
        missing_discord = [i for i in self.issues if i['type'] == 'missing_in_discord']
        missing_db = [i for i in self.issues if i['type'] == 'missing_in_db']
        
        if missing_discord:
            report += f"\n⚠️  只在資料庫中 (Discord 找不到): {len(missing_discord)} 個\n"
        
        if missing_db:
            report += f"⚠️  只在 Discord 中 (資料庫找不到): {len(missing_db)} 個\n"
        
        return report
    
    def save_results(self):
        """保存診斷結果"""
        try:
            results = {
                'timestamp': datetime.now().isoformat(),
                'discord_members_count': len(self.real_members),
                'db_members_count': len(self.db_members),
                'offset_count': len(self.id_mapping),
                'id_mapping': {str(k): v for k, v in self.id_mapping.items()},
                'member_mapping': {
                    self.db_members.get(nick, ''): real_id
                    for nick, real_id in self.real_members.items()
                    if nick in self.db_members
                }
            }
            
            with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            print(f"\n✅ 診斷結果已保存到: {MAPPING_FILE}")
        except Exception as e:
            print(f"❌ 保存結果失敗: {e}")
    
    def apply_fixes(self) -> bool:
        """應用修復"""
        if not Path(DB_PATH).exists():
            print(f"❌ {DB_PATH} 不存在")
            return False
        
        if not self.id_mapping:
            print("✅ 沒有 ID 偏差，無需修復")
            return True
        
        try:
            print("\n" + "="*60)
            print("步驟 4: 執行修復...")
            print("="*60)
            
            # 創建備份
            import shutil
            backup_path = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy(DB_PATH, backup_path)
            print(f"✅ 備份已創建: {backup_path}")
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            total_updates = 0
            
            # 更新 user_data 表
            print("\n更新 user_data 表:")
            for db_id, real_id in self.id_mapping.items():
                c.execute("UPDATE user_data SET user_id = ? WHERE user_id = ?", (real_id, db_id))
                count = c.rowcount
                if count > 0:
                    nick = None
                    for n, uid in self.db_members.items():
                        if uid == db_id:
                            nick = n
                            break
                    print(f"  ✅ {nick}: {db_id} → {real_id} ({count} 條記錄)")
                    total_updates += count
            
            # 更新其他表
            tables_to_update = ['cannabis_plants', 'cannabis_inventory', 'user_roles', 'user_equipment']
            
            for table in tables_to_update:
                try:
                    c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                    if c.fetchone():
                        print(f"\n更新 {table} 表:")
                        
                        for db_id, real_id in self.id_mapping.items():
                            c.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = ?", (real_id, db_id))
                            count = c.rowcount
                            if count > 0:
                                print(f"  ✅ {db_id} → {real_id}: {count} 條記錄")
                                total_updates += count
                except sqlite3.OperationalError:
                    pass  # 表不存在，跳過
                except Exception as e:
                    print(f"  ⚠️  更新失敗: {e}")
            
            conn.commit()
            conn.close()
            
            print(f"\n" + "="*60)
            print(f"✅ 修復完成！")
            print(f"   • 總修復次數: {total_updates} 條記錄")
            print(f"   • 備份位置: {backup_path}")
            print("="*60)
            return True
        
        except Exception as e:
            print(f"❌ 修復失敗: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """主程序"""
    # 從環境變數讀取 Discord Token
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ 未設置 DISCORD_TOKEN 環境變數")
        print("   請執行: export DISCORD_TOKEN='your_token_here'")
        return False
    
    fixer = UserIDFixer(token)
    
    # 執行診斷
    success = await fixer.run_diagnosis()
    
    if not success:
        return False
    
    # 檢查是否需要修復
    if fixer.id_mapping:
        print(f"\n❓ 找到 {len(fixer.id_mapping)} 個 ID 偏差用戶")
        
        if len(sys.argv) > 1 and sys.argv[1] == 'fix':
            print("\n即將執行修復，按 Ctrl+C 取消...")
            try:
                import time
                time.sleep(3)
            except KeyboardInterrupt:
                print("\n已取消")
                return False
            
            return fixer.apply_fixes()
        else:
            print("\n💡 執行修復: python fix_user_ids_standalone.py fix")
            return True
    else:
        print("\n✅ 沒有發現 ID 偏差")
        return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
