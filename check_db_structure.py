#!/usr/bin/env python3
import sqlite3

db_path = "/home/e193752468/kkgroup/data/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 查詢所有表
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    print(f"Tables in user_data.db: {tables}")
    
    # 查詢 anime_check_history 表結構
    print("\n=== anime_check_history 表結構 ===")
    c.execute("PRAGMA table_info(anime_check_history)")
    for col in c.fetchall():
        print(f"  {col}")
    
    # 查詢最近的 5 個檢查記錄
    print("\n=== anime_check_history 最近 5 筆 ===")
    c.execute("SELECT * FROM anime_check_history ORDER BY checked_at DESC LIMIT 5")
    for row in c.fetchall():
        print(f"  {row}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
