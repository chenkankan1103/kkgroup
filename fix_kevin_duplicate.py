#!/usr/bin/env python3
"""
修復凱文重複和虛擬人物問題
1. 備份當前資料庫
2. 識別虛擬人物凱文
3. 保留原始 No.60123 凱文
4. 刪除或覆蓋虛擬人物版本
"""

import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/home/e193752468/kkgroup/backups'

# 原始凱文的資料（已知正確的）
ORIGINAL_KEVIN = {
    'user_id': 776464975551660123,
    'nickname': '凱文',  # No.60123 凱文
    'level': 1,  # 原始等級
    'xp': 0,
    'kkcoin': 10000,
    'title': None,
    'hp': 100,
    'stamina': 100,
    'equipment': None,  # 或 JSON
}

def backup_db():
    """備份資料庫"""
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{BACKUP_DIR}/user_data_backup_kevin_fix_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ 備份完成: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ 備份失敗: {e}")
        return None

def diagnose_kevin_issue():
    """診斷凱文的問題"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("\n" + "=" * 80)
        print("診斷凱文重複問題")
        print("=" * 80 + "\n")
        
        # 1. 查詢所有凱文相關記錄
        cursor.execute("""
            SELECT user_id, nickname, level, xp, kkcoin, title, hp, stamina, equipment
            FROM users 
            WHERE user_id = 776464975551660123 OR nickname LIKE '%凱文%'
            ORDER BY user_id, _updated_at DESC
        """)
        
        kevin_records = cursor.fetchall()
        print(f"找到 {len(kevin_records)} 個凱文相關記錄:\n")
        
        virtual_kevins = []
        original_kevin = None
        
        for i, record in enumerate(kevin_records, 1):
            print(f"【記錄 {i}】")
            print(f"  user_id: {record['user_id']}")
            print(f"  nickname: {record['nickname']}")
            print(f"  level: {record['level']}")
            print(f"  xp: {record['xp']}")
            print(f"  kkcoin: {record['kkcoin']}")
            print(f"  title: {record['title']}")
            print(f"  equipment: {record['equipment']}")
            
            # 判斷是虛擬人物還是原始凱文
            if record['user_id'] != 776464975551660123:
                print(f"  👤 虛擬人物 (ID 不匹配)")
                virtual_kevins.append(record['user_id'])
            elif record['nickname'] != '凱文' or record['kkcoin'] == 10000:
                print(f"  📌 原始凱文 (ID 匹配，KK幣為 10000)")
                original_kevin = record
            else:
                print(f"  ⚠️ 同步後覆蓋的凱文 (ID 匹配但數據不同)")
                virtual_kevins.append(record['user_id'])
            
            print()
        
        conn.close()
        
        return {
            'kevin_records': len(kevin_records),
            'virtual_kevins': virtual_kevins,
            'original_kevin': original_kevin
        }
    
    except Exception as e:
        print(f"❌ 診斷失敗: {e}")
        import traceback
        traceback.print_exc()
        return None

def fix_kevin_issue(diagnosis):
    """修復凱文重複問題"""
    if not diagnosis or diagnosis['kevin_records'] <= 1:
        print("✅ 沒有發現凱文重複問題")
        return True
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("\n" + "=" * 80)
        print("修復凱文重複問題")
        print("=" * 80 + "\n")
        
        # 1. 刪除不正確的凱文記錄
        if diagnosis['virtual_kevins']:
            print(f"刪除 {len(diagnosis['virtual_kevins'])} 個虛擬人物凱文...\n")
            
            for user_id in diagnosis['virtual_kevins']:
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                print(f"  ✓ 刪除 user_id {user_id}")
        
        # 2. 確保原始凱文的正確資料被保存
        print(f"\n恢復原始凱文的正確資料...\n")
        
        # 使用 INSERT OR REPLACE
        cursor.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, nickname, level, xp, kkcoin, title, hp, stamina, equipment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            776464975551660123,
            '凱文',
            1,
            0,
            10000,
            None,
            100,
            100,
            None
        ))
        
        print(f"  ✓ 恢復 user_id 776464975551660123")
        
        conn.commit()
        conn.close()
        
        print("\n✅ 修復完成")
        return True
    
    except Exception as e:
        print(f"❌ 修復失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 80)
    print("凱文重複和虛擬人物修復工具")
    print("=" * 80)
    
    # 1. 備份
    backup = backup_db()
    if not backup:
        exit(1)
    
    # 2. 診斷
    diagnosis = diagnose_kevin_issue()
    if not diagnosis:
        exit(1)
    
    # 3. 修復
    if fix_kevin_issue(diagnosis):
        print("\n✅ 所有操作完成")
    else:
        print("\n❌ 修復過程中出現錯誤，請檢查備份文件")
        exit(1)
