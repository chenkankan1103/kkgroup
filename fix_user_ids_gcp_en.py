#!/usr/bin/env python3
"""
Discord User ID Fix Script
Repair wrong IDs in database and update foreign key references
"""

import sqlite3
import json
import sys
from datetime import datetime
from pathlib import Path
import shutil

# Configuration
DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/home/e193752468/kkgroup/backups'
GUILD_ID = 1133112693356773416

# ID mappings to fix
# Format: {wrong_ID: correct_ID}
ID_FIXES = {
    260266786719531008: 260266786719531009,  # night_lion (offset +1)
}

# Tables with user_id foreign key
TABLES_WITH_USER_ID = [
    'cannabis_plants',
    'cannabis_inventory',
    'event_history',
    'merchant_transactions',
]

class UserIDFixer:
    """ID repair tool"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.backup_path = None
    
    def backup_database(self) -> bool:
        """Backup database"""
        try:
            Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.backup_path = f"{BACKUP_DIR}/user_data_backup_{timestamp}.db"
            
            print(f"Backing up database to: {self.backup_path}")
            shutil.copy2(self.db_path, self.backup_path)
            print(f"Backup complete")
            return True
        
        except Exception as e:
            print(f"Backup failed: {e}")
            return False
    
    def connect(self) -> bool:
        """Connect to database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")
            print(f"Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def get_user_info(self, user_id: int) -> dict:
        """Get user information"""
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
        """Execute ID repair"""
        try:
            c = self.conn.cursor()
            
            print("\n=== Starting ID repair ===\n")
            
            for old_id, new_id in ID_FIXES.items():
                print(f"Fixing: {old_id} -> {new_id}")
                
                # Get user info
                user_info = self.get_user_info(old_id)
                if not user_info:
                    print(f"   User not found, skipping")
                    continue
                
                print(f"   User: {user_info['nickname']}")
                
                # Begin transaction
                try:
                    self.conn.execute("BEGIN TRANSACTION")
                    
                    # Fix users table
                    print(f"   Updating users table...")
                    c.execute(
                        "UPDATE users SET user_id = ? WHERE user_id = ?",
                        (new_id, old_id)
                    )
                    rows = c.rowcount
                    print(f"      Updated {rows} rows")
                    
                    # Fix foreign key references
                    for table in TABLES_WITH_USER_ID:
                        print(f"   Updating {table} table...")
                        c.execute(
                            f"UPDATE {table} SET user_id = ? WHERE user_id = ?",
                            (new_id, old_id)
                        )
                        rows = c.rowcount
                        if rows > 0:
                            print(f"      Updated {rows} rows")
                    
                    self.conn.commit()
                    print(f"   Repair complete\n")
                
                except Exception as e:
                    self.conn.rollback()
                    print(f"   Repair failed: {e}")
                    return False
            
            return True
        
        except Exception as e:
            print(f"Repair execution failed: {e}")
            return False
    
    def verify_fixes(self) -> bool:
        """Verify repair results"""
        try:
            print("\n=== Verifying repair results ===\n")
            c = self.conn.cursor()
            
            for old_id, new_id in ID_FIXES.items():
                print(f"Checking {old_id} -> {new_id}")
                
                # Check old ID deleted
                c.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (old_id,))
                old_count = c.fetchone()[0]
                
                if old_count == 0:
                    print(f"   Old ID deleted")
                else:
                    print(f"   ERROR: Old ID still exists ({old_count} rows)")
                    return False
                
                # Check new ID exists
                c.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (new_id,))
                new_count = c.fetchone()[0]
                
                if new_count == 1:
                    print(f"   New ID exists")
                else:
                    print(f"   ERROR: New ID anomaly ({new_count} rows)")
                    return False
                
                # Check related table integrity
                for table in TABLES_WITH_USER_ID:
                    c.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (old_id,))
                    old_refs = c.fetchone()[0]
                    
                    if old_refs > 0:
                        print(f"   ERROR: Old ID still in {table} ({old_refs} rows)")
                        return False
                    
                    c.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (new_id,))
                    new_refs = c.fetchone()[0]
                    
                    if new_refs > 0:
                        print(f"   {table} updated ({new_refs} rows)")
                
                print()
            
            print("All verifications passed\n")
            return True
        
        except Exception as e:
            print(f"Verification failed: {e}")
            return False
    
    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()
    
    def run(self):
        """Execute complete repair process"""
        print("\n" + "="*70)
        print("Discord User ID Fix Tool")
        print("="*70 + "\n")
        
        # 1. Backup
        if not self.backup_database():
            return False
        
        # 2. Connect
        if not self.connect():
            return False
        
        # 3. Fix
        if not self.fix_ids():
            self.close()
            return False
        
        # 4. Verify
        if not self.verify_fixes():
            self.close()
            return False
        
        # 5. Close
        self.close()
        
        print("="*70)
        print("Repair complete!")
        print(f"Backup location: {self.backup_path}")
        print("="*70 + "\n")
        
        return True


if __name__ == '__main__':
    fixer = UserIDFixer(DB_PATH)
    success = fixer.run()
    sys.exit(0 if success else 1)
