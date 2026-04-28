# -*- coding: utf-8 -*-
"""
檢查用戶置物櫃狀態
"""
import sqlite3
import sys
from pathlib import Path

def check_locker_status(user_id: str):
    db_path = Path(__file__).parent / "user_data.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            'SELECT user_id, locker_message_id, thread_id, is_stunned FROM users WHERE user_id = ?', 
            (user_id,)
        )
        row = cursor.fetchone()
        
        if row:
            print('用戶 ID: ' + str(row['user_id']))
            print('置物櫃訊息 ID: ' + str(row['locker_message_id']))
            print('置物櫃線程 ID: ' + str(row['thread_id']))
            print('暈倒狀態: ' + str(row['is_stunned']))
            
            if row['locker_message_id'] and row['thread_id']:
                print('\n✅ 置物櫃已建立！')
                return True
            else:
                print('\n❌ 置物櫃尚未建立')
                return False
        else:
            print('❌ 用戶未找到')
            return False
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python3 check_locker_status.py <user_id>')
        sys.exit(1)
    
    user_id = sys.argv[1]
    success = check_locker_status(user_id)
    sys.exit(0 if success else 1)
