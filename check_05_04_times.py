#!/usr/bin/env python3
import sqlite3

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=== 05-04 所有檢查時刻記錄 ===")
    c.execute("""
        SELECT * FROM anime_check_history 
        WHERE check_date = '2026-05-04'
        ORDER BY scheduled_time
    """)
    for row in c.fetchall():
        id_val, date, time, checked_at = row
        print(f"  時刻={time:>5}, checked_at={checked_at}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
