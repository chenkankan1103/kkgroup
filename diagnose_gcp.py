#!/usr/bin/env python3
"""
GCP 用戶ID診斷工具 - 簡化版，只讀取數據庫
直接在GCP上執行，確保無需依賴
"""

import sqlite3
import os

DB_PATH = './user_data.db'

try:
    if not os.path.exists(DB_PATH):
        print(f"❌ 數據庫不存在: {DB_PATH}")
        print(f"   當前目錄: {os.getcwd()}")
        exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 基礎統計
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT user_id, nickname FROM users ORDER BY user_id DESC")
    users = cursor.fetchall()
    
    print("=" * 70)
    print("📊 GCP 資料庫診斷結果")
    print("=" * 70)
    print(f"總用戶數: {total}")
    print("\n用戶清單:")
    print(f"{'UserID':>20} | {'Nickname':<30}")
    print("-" * 55)
    
    short_ids = 0
    valid_ids = 0
    test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB']
    
    for user_id, nick in users:
        nick_str = (nick or "(無昵稱)")[:30]
        print(f"{user_id:>20} | {nick_str:<30}")
        
        if user_id < 100000000000000000:
            short_ids += 1
        else:
            valid_ids += 1
    
    print()
    print(f"短ID (無效): {short_ids}")
    print(f"有效ID: {valid_ids}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ 錯誤: {e}")
    import traceback
    traceback.print_exc()
