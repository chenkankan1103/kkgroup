#!/usr/bin/env python3
"""
Discord ID 修復腳本
修復資料庫中的異常 ID 並更新相關表的外鍵參考
"""

import sqlite3
import json
import sys
from datetime import datetime
from pathlib import Path
import shutil

# ===== 設定 =====
DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/home/e193752468/kkgroup/backups'
GUILD_ID = 1133112693356773416

# 需要修復的用戶ID映射
# 格式: {錯誤_ID: 正確_ID}
ID_FIXES = {
    260266786719531008: 260266786719531009,  # 夜神獅獅
}

# 包含 user_id 外鍵的表
TABLES_WITH_USER_ID = [
    'cannabis_plants',
    'cannabis_inventory',
    'event_history',
    'merchant_transactions',
]

class UserIDFixer:
    """ID 修復工具"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.backup_path = None
    
    def backup_database(self) -> bool:
        """備份資料庫"""
        try:
            Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.backup_path = f"{BACKUP_DIR}/user_data_backup_{timestamp}.db"
            
            print(f"📦 正在備份資料庫到: {self.backup_path}")
            shutil.copy2(self.db_path, self.backup_path)
            print(f"✅ 備份完成")
            return True
        
        except Exception as e:
            print(f"❌ 備份失敗: {e}")
            return False
    
    def connect(self) -> bool:
        """連接資料庫"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")
            print(f"✅ 已連接到資料庫: {self.db_path}")
            return True
        except Exception as e:
            print(f"❌ 連接失敗: {e}")
            return False
    
    def get_user_info(self, user_id: int) -> dict:
        """獲取用戶信息"""
        try:
            c = self.conn.cursor()
            c.execute("SELECT user_id, nickname FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            
            if result:
                return {'user_id': result[0], 'nickname': result[1]}
            return None
        except Exception as e:
            print(f"❌ 查詢用戶失敗: {e}")
            return None
    
    def fix_ids(self) -> bool:
        """執行 ID 修復"""
        try:
            c = self.conn.cursor()
            
            print("\n=== 開始修復 ID ===\n")
            
            for old_id, new_id in ID_FIXES.items():
                print(f"📝 修復: {old_id} -> {new_id}")
                
                # 獲取用戶信息
                user_info = self.get_user_info(old_id)
                if not user_info:
                    print(f"   ⚠️  使用者不存在，跳過")
                    continue
                
                print(f"   用戶: {user_info['nickname']}")
                
                # 開始事務
                try:
                    self.conn.execute("BEGIN TRANSACTION")
                    
                    # 修復 users 表
                    print(f"   🔄 更新 users 表...")
                    c.execute(
                        "UPDATE users SET user_id = ? WHERE user_id = ?",
                        (new_id, old_id)
                    )
                    rows = c.rowcount
                    print(f"      ✓ 更新 {rows} 列")
                    
                    # 修復其他表中的外鍵
                    for table in TABLES_WITH_USER_ID:
                        print(f"   🔄 更新 {table} 表...")
                        c.execute(
                            f"UPDATE {table} SET user_id = ? WHERE user_id = ?",
                            (new_id, old_id)
                        )
                        rows = c.rowcount
                        if rows > 0:
                            print(f"      ✓ 更新 {rows} 列")
                    
                    self.conn.commit()
                    print(f"   ✅ 修復完成\n")
                
                except Exception as e:
                    self.conn.rollback()
                    print(f"   ❌ 修復失敗: {e}")
                    return False
            
            return True
        
        except Exception as e:
            print(f"❌ 執行修復失敗: {e}")
            return False
    
    def verify_fixes(self) -> bool:
        """驗證修復結果"""
        try:
            print("\n=== 驗證修復結果 ===\n")
            c = self.conn.cursor()
            
            for old_id, new_id in ID_FIXES.items():
                print(f"🔍 檢查 {old_id} -> {new_id}")
                
                # 檢查舊 ID 是否已刪除
                c.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (old_id,))
                old_count = c.fetchone()[0]
                
                if old_count == 0:
                    print(f"   ✓ 舊 ID 已刪除")
                else:
                    print(f"   ❌ 舊 ID 仍存在 ({old_count} 列)")
                    return False
                
                # 檢查新 ID 是否存在
                c.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (new_id,))
                new_count = c.fetchone()[0]
                
                if new_count == 1:
                    print(f"   ✓ 新 ID 已存在")
                else:
                    print(f"   ❌ 新 ID 異常 ({new_count} 列)")
                    return False
                
                # 檢查相關表的完整性
                for table in TABLES_WITH_USER_ID:
                    c.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (old_id,))
                    old_refs = c.fetchone()[0]
                    
                    if old_refs > 0:
                        print(f"   ❌ {table} 中仍存在舊 ID ({old_refs} 列)")
                        return False
                    
                    c.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (new_id,))
                    new_refs = c.fetchone()[0]
                    
                    if new_refs > 0:
                        print(f"   ✓ {table} 已更新 ({new_refs} 列)")
                
                print()
            
            print("✅ 所有驗證通過\n")
            return True
        
        except Exception as e:
            print(f"❌ 驗證失敗: {e}")
            return False
    
    def close(self):
        """關閉連接"""
        if self.conn:
            self.conn.close()
    
    def run(self):
        """執行完整修復流程"""
        print("\n" + "="*70)
        print("Discord User ID 修復工具")
        print("="*70 + "\n")
        
        # 1. 備份
        if not self.backup_database():
            return False
        
        # 2. 連接
        if not self.connect():
            return False
        
        # 3. 修復
        if not self.fix_ids():
            self.close()
            return False
        
        # 4. 驗證
        if not self.verify_fixes():
            self.close()
            return False
        
        # 5. 關閉
        self.close()
        
        print("="*70)
        print("✅ 修復完成！")
        print(f"備份位置: {self.backup_path}")
        print("="*70 + "\n")
        
        return True


if __name__ == '__main__':
    fixer = UserIDFixer(DB_PATH)
    success = fixer.run()
    sys.exit(0 if success else 1)
