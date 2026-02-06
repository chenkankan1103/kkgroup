#!/usr/bin/env python3
"""
簡化版: Discord User ID 診斷工具
直接在 GCP 上運行，自動讀取 .env 中的 token

使用方式：
  python diagnose_dc_ids.py         # 僅診斷
  python diagnose_dc_ids.py fix     # 診斷+修復
"""

import discord
import asyncio
import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict
import os
from dotenv import load_dotenv

# 配置
GUILD_ID = 1133112693356773416
DB_PATH = './user_data.db'
MAPPING_FILE = './id_mapping_results.json'


class DCIDDiagnoser:
    """Discord ID 診斷工具"""
    
    def __init__(self, token: str):
        self.token = token
        self.real_members = {}
        self.db_members = {}
        self.id_mapping = {}
        self.issues = []
        
        # 創建臨時 bot
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        
        @self.bot.event
        async def on_ready():
            print(f"\n✅ 已連接到 Discord: {self.bot.user}")
    
    async def diagnose(self) -> bool:
        """執行診斷"""
        try:
            print("\n" + "="*70)
            print("Discord User ID 診斷工具")
            print("="*70)
            
            # 登入 Discord
            print("\n[1/3] 正在連接 Discord...")
            async with self.bot:
                await self.bot.login(self.token)
                
                # 等待就緒
                await self.bot.wait_until_ready()
                
                # 拉取成員
                print("[2/3] 正在讀取 Discord 成員...")
                guild = self.bot.get_guild(GUILD_ID)
                if not guild:
                    print(f"❌ 無法找到 Guild: {GUILD_ID}")
                    return False
                
                count = 0
                async for member in guild.fetch_members(limit=None):
                    nickname = member.nick or member.name
                    self.real_members[nickname] = member.id
                    count += 1
                    if count % 50 == 0:
                        print(f"   已讀取 {count} 個成員...")
                
                print(f"✅ 已讀取 {count} 個 Discord 成員\n")
                
                await self.bot.close()
        
        except Exception as e:
            print(f"❌ Discord 連接失敗: {e}")
            return False
        
        # 讀取資料庫
        print("[3/3] 正在讀取資料庫...")
        self.db_members = self.read_db_users()
        if not self.db_members:
            print("❌ 無法讀取資料庫用戶")
            return False
        
        print(f"✅ 已讀取 {len(self.db_members)} 個資料庫用戶\n")
        
        # 對比
        self.id_mapping = self.find_mappings()
        self.issues = self.identify_issues()
        
        # 顯示報告
        print(self.generate_report())
        
        # 保存結果
        self.save_results()
        
        return True
    
    def read_db_users(self) -> Dict[str, int]:
        """從資料庫讀取用戶"""
        users = {}
        
        if not Path(DB_PATH).exists():
            return users
        
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            c.execute("SELECT user_id, nickname FROM user_data")
            rows = c.fetchall()
            
            for user_id, nickname in rows:
                if nickname and not str(nickname).startswith(('test', 'Test', 'TEST')):
                    users[nickname] = user_id
            
            conn.close()
        except Exception as e:
            print(f"❌ 讀取資料庫失敗: {e}")
        
        return users
    
    def find_mappings(self) -> Dict[int, int]:
        """找出 ID 映射"""
        mapping = {}
        
        for nickname, real_id in self.real_members.items():
            if nickname in self.db_members:
                db_id = self.db_members[nickname]
                if db_id != real_id:
                    mapping[db_id] = real_id
        
        return mapping
    
    def identify_issues(self) -> list:
        """識別問題"""
        issues = []
        
        for db_id, real_id in self.id_mapping.items():
            offset = real_id - db_id
            
            nickname = None
            for n, uid in self.db_members.items():
                if uid == db_id:
                    nickname = n
                    break
            
            issues.append({
                'type': 'offset',
                'nickname': nickname,
                'db_id': db_id,
                'real_id': real_id,
                'offset': offset
            })
        
        return issues
    
    def generate_report(self) -> str:
        """生成報告"""
        report = f"""
╔════════════════════════════════════════════════════════════════════╗
║                         診斷結果                                    ║
╠════════════════════════════════════════════════════════════════════╣
║ Discord 成員總數:        {len(self.real_members):>6}             ║
║ 資料庫用戶總數:          {len(self.db_members):>6}             ║
║ ID 偏差用戶數:           {len(self.id_mapping):>6}             ║
╚════════════════════════════════════════════════════════════════════╝
"""
        
        if self.id_mapping:
            # 統計偏差
            offsets = {}
            for db_id, real_id in self.id_mapping.items():
                offset = real_id - db_id
                if offset not in offsets:
                    offsets[offset] = 0
                offsets[offset] += 1
            
            report += "\n【 偏差分佈 】\n"
            for offset, count in sorted(offsets.items()):
                report += f"  • {offset:+5d}: {count:>3} 個用戶\n"
            
            # 詳細列表
            report += "\n【 偏差用戶列表 (前15個) 】\n"
            for idx, item in enumerate(sorted(self.issues, key=lambda x: x['offset'], reverse=True)[:15], 1):
                report += (f"  {idx:2}. {item['nickname']:20} | "
                          f"DB:{item['db_id']:>18} → {item['real_id']:>18} "
                          f"({item['offset']:+6d})\n")
        else:
            report += "\n✅ 沒有發現 ID 偏差\n"
        
        return report
    
    def save_results(self):
        """保存結果"""
        try:
            results = {
                'timestamp': datetime.now().isoformat(),
                'discord_count': len(self.real_members),
                'db_count': len(self.db_members),
                'offset_count': len(self.id_mapping),
                'mappings': {str(k): v for k, v in self.id_mapping.items()}
            }
            
            with open(MAPPING_FILE, 'w') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            print(f"✅ 結果已保存: {MAPPING_FILE}\n")
        except Exception as e:
            print(f"❌ 保存結果失敗: {e}")
    
    def apply_fixes(self) -> bool:
        """應用修復"""
        if not self.id_mapping:
            print("✅ 沒有 ID 偏差，無需修復")
            return True
        
        if not Path(DB_PATH).exists():
            print(f"❌ {DB_PATH} 不存在")
            return False
        
        try:
            print("\n" + "="*70)
            print("開始執行修復...")
            print("="*70)
            
            # 備份
            import shutil
            backup = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy(DB_PATH, backup)
            print(f"\n✅ 備份已創建: {backup}")
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            total_updates = 0
            tables = ['user_data', 'cannabis_plants', 'cannabis_inventory', 'user_roles']
            
            for table in tables:
                try:
                    c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                    if not c.fetchone():
                        continue
                    
                    print(f"\n更新 {table}:")
                    
                    for db_id, real_id in self.id_mapping.items():
                        c.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = ?", (real_id, db_id))
                        count = c.rowcount
                        if count > 0:
                            print(f"  ✅ {db_id} → {real_id}: {count} 條")
                            total_updates += count
                
                except sqlite3.OperationalError:
                    pass
            
            conn.commit()
            conn.close()
            
            print(f"\n" + "="*70)
            print(f"✅ 修復完成！共更新 {total_updates} 條記錄")
            print("="*70 + "\n")
            return True
        
        except Exception as e:
            print(f"❌ 修復失敗: {e}")
            return False


async def main():
    """主程序"""
    # 載入 .env
    load_dotenv()
    token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not token:
        print("❌ 未找到 DISCORD_BOT_TOKEN")
        print("請確保 .env 文件中有此設置")
        return False
    
    # 執行診斷
    diagnoser = DCIDDiagnoser(token)
    success = await diagnoser.diagnose()
    
    if not success:
        return False
    
    # 如果有偏差並命令行有 'fix' 參數
    if diagnoser.id_mapping and len(sys.argv) > 1 and sys.argv[1] == 'fix':
        print(f"⚠️  將修復 {len(diagnoser.id_mapping)} 個用戶的 ID")
        print("3 秒後開始... (按 Ctrl+C 取消)\n")
        try:
            await asyncio.sleep(3)
        except KeyboardInterrupt:
            print("\n已取消")
            return False
        
        return diagnoser.apply_fixes()
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
