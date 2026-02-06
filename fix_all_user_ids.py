#!/usr/bin/env python3
"""
Complete Discord User ID Fix Tool
Fix all 27 users with wrong IDs
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
import shutil

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/home/e193752468/kkgroup/backups'

# All ID corrections (discovered in full diagnosis)
ID_FIXES = {
    344018672056139776: 344018672056139786,      # 赤月 (+10)
    401694438449217536: 401694438449217548,      # 落華 (+12)
    447377925885657088: 447377925885657090,      # Dorameow (+2)
    476983085536116800: 476983085536116773,      # 葉祤[語] (-27)
    515887019432476672: 515887019432476687,      # 白滅 (+15)
    529281705144614912: 529281705144614922,      # 老鼠 (+10)
    535810695011368960: 535810695011368972,      # 綠小哀 (+12)
    536158541661339648: 536158541661339659,      # Cakie (+11)
    564156950913351680: 564156950913351685,      # 自在天外天 (+5)
    584598692468883456: 584598692468883485,      # 𓀐𓂺伊藤閣下𓀐𓂺 (+29)
    598451343174139904: 598451343174139924,      # 小乃 (+20)
    611139696537501696: 611139696537501706,      # SeanLinKing (+10)
    716266196571390080: 716266196571390024,      # Yvette122 (-56)
    740803743821594624: 740803743821594654,      # 長不胖的panzer (+30)
    776464975551660160: 776464975551660123,      # 凱文 (-37)
    831927868258779136: 831927868258779196,      # huihui (+60)
    838409160054931584: 838409160054931536,      # 尬林北跪瑞 (-48)
    839294960251305984: 839294960251306018,      # 鹹魚 (+34)
    908321615111147520: 908321615111147540,      # 加藤雀 (+20)
    989477549962838144: 989477549962838096,      # 流星雨 (-48)
    1018549741920989312: 1018549741920989355,    # 小筑 (+43)
    1148893517901463552: 1148893517901463602,   # 白鱼 (+50)
    1248646973943185408: 1248646973943185518,   # lin_jack204473740 (+110)
    1296436778021945344: 1296436778021945396,   # 梅川イブ (+52)
    1373284011472060416: 1373284011472060517,   # 蘇門達臘 (+101)
    1375651445231058944: 1375651445231059034,   # 江彥🏀 (+90)
    1393778424535056384: 1393778424535056405,   # lix (+21)
}

TABLES_WITH_USER_ID = [
    'cannabis_plants',
    'cannabis_inventory',
    'event_history',
    'merchant_transactions',
]

class BulkUserIDFixer:
    """Bulk ID repair tool"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.backup_path = None
        self.results = {
            'success': [],
            'failed': [],
            'skipped': [],
        }
    
    def backup_database(self) -> bool:
        """Backup database"""
        try:
            Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.backup_path = f"{BACKUP_DIR}/user_data_backup_bulk_{timestamp}.db"
            
            print(f"Backing up to: {self.backup_path}")
            shutil.copy2(self.db_path, self.backup_path)
            print(f"Backup complete\n")
            return True
        except Exception as e:
            print(f"Backup failed: {e}")
            return False
    
    def connect(self) -> bool:
        """Connect to database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")
            print(f"Connected to database\n")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def get_user_info(self, user_id: int) -> dict:
        """Get user info"""
        try:
            c = self.conn.cursor()
            c.execute("SELECT user_id, nickname FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            if result:
                return {'user_id': result[0], 'nickname': result[1]}
            return None
        except Exception as e:
            print(f"Query failed: {e}")
            return None
    
    def fix_ids(self) -> bool:
        """Fix all IDs"""
        try:
            c = self.conn.cursor()
            total = len(ID_FIXES)
            
            print(f"Fixing {total} users...\n")
            
            for idx, (old_id, new_id) in enumerate(ID_FIXES.items(), 1):
                print(f"[{idx}/{total}] Fixing {old_id} -> {new_id}")
                
                user_info = self.get_user_info(old_id)
                if not user_info:
                    print(f"  User not found, skipping")
                    self.results['skipped'].append((old_id, new_id))
                    continue
                
                nickname = user_info['nickname']
                print(f"  User: {nickname}")
                
                try:
                    self.conn.execute("BEGIN TRANSACTION")
                    
                    # Fix users table
                    c.execute(
                        "UPDATE users SET user_id = ? WHERE user_id = ?",
                        (new_id, old_id)
                    )
                    
                    # Fix foreign keys
                    for table in TABLES_WITH_USER_ID:
                        c.execute(
                            f"UPDATE {table} SET user_id = ? WHERE user_id = ?",
                            (new_id, old_id)
                        )
                    
                    self.conn.commit()
                    print(f"  Done")
                    self.results['success'].append((old_id, new_id, nickname))
                
                except Exception as e:
                    self.conn.rollback()
                    print(f"  Failed: {e}")
                    self.results['failed'].append((old_id, new_id, str(e)))
            
            print()
            return len(self.results['failed']) == 0
        
        except Exception as e:
            print(f"Execution failed: {e}")
            return False
    
    def verify_fixes(self) -> bool:
        """Verify all fixes"""
        try:
            print("\nVerifying fixes...\n")
            c = self.conn.cursor()
            all_pass = True
            
            for old_id, new_id in ID_FIXES.items():
                # Check old ID deleted
                c.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (old_id,))
                old_count = c.fetchone()[0]
                
                # Check new ID exists
                c.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (new_id,))
                new_count = c.fetchone()[0]
                
                if old_count == 0 and new_count == 1:
                    print(f"✓ {old_id} -> {new_id}")
                else:
                    print(f"✗ {old_id} -> {new_id} (old_count={old_count}, new_count={new_count})")
                    all_pass = False
            
            print()
            return all_pass
        
        except Exception as e:
            print(f"Verification failed: {e}")
            return False
    
    def generate_report(self):
        """Generate report"""
        print("\n" + "="*70)
        print("FINAL REPORT")
        print("="*70 + "\n")
        
        print(f"Success: {len(self.results['success'])}/27")
        print(f"Failed: {len(self.results['failed'])}")
        print(f"Skipped: {len(self.results['skipped'])}")
        
        if self.results['failed']:
            print("\nFailed fixes:")
            for old_id, new_id, error in self.results['failed']:
                print(f"  {old_id} -> {new_id}: {error}")
        
        print(f"\nBackup: {self.backup_path}")
        print("="*70 + "\n")
    
    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()
    
    def run(self):
        """Run complete fix process"""
        print("\n" + "="*70)
        print("BULK Discord User ID Fix Tool")
        print("="*70 + "\n")
        
        if not self.backup_database():
            return False
        
        if not self.connect():
            return False
        
        if not self.fix_ids():
            self.close()
            return False
        
        if not self.verify_fixes():
            self.close()
            return False
        
        self.generate_report()
        self.close()
        return True


if __name__ == '__main__':
    fixer = BulkUserIDFixer(DB_PATH)
    success = fixer.run()
    exit(0 if success else 1)
