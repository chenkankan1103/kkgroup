#!/usr/bin/env python3
"""
快速資料庫診斷 - 直接查詢資料庫內容，無需Discord連接
只進行簡單的資料庫檢查
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = './user_data.db'

def diagnose():
    print(f"\n📋 資料庫診斷 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ 資料庫不存在: {DB_PATH}")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. 統計
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        print(f"\n📊 用戶總數: {total}")
        
        # 2. 所有用戶
        print(f"\n👥 所有用戶列表:")
        print(f"{'ID':>20} | {'昵稱':<30} | {'執行序號':<10}")
        print("-" * 65)
        
        cursor.execute("""
            SELECT user_id, nickname, rowid
            FROM users
            ORDER BY user_id DESC
        """)
        
        rows = cursor.fetchall()
        short_id_count = 0
        test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB']
        
        for user_id, nickname, rowid in rows:
            nick_str = (nickname or "(無昵稱)")[:30]
            print(f"{user_id:>20} | {nick_str:<30} | {rowid:<10}")
            
            # 檢查測試ID
            if user_id < 100000000000000000:
                short_id_count += 1
                print(f"  ⚠️ 短ID (應該是18位數字)")
            if any(p in str(nickname or "").lower() for p in test_patterns):
                print(f"  🧪 測試昵稱")
        
        print("\n📈 分類統計:")
        # 短ID
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id < 100000000000000000")
        short_ids = cursor.fetchone()[0]
        print(f"  • 短ID (< 18位): {short_ids}")
        
        # 無昵稱
        cursor.execute("SELECT COUNT(*) FROM users WHERE nickname IS NULL OR nickname = ''")
        no_nick = cursor.fetchone()[0]
        print(f"  • 無昵稱: {no_nick}")
        
        # 測試昵稱
        test_count = sum(1 for _, nick, _ in rows 
                        if nick and any(p in nick.lower() for p in test_patterns))
        print(f"  • 測試昵稱: {test_count}")
        
        print("\n✅ 診斷完成")
        print("=" * 80)
        
        conn.close()
    
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose()
