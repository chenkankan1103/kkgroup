#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=== 05-04 10:00 時間窗口檢查記錄 ===")
    c.execute("""
        SELECT * FROM anime_check_history 
        WHERE check_date = '2026-05-04' 
        AND scheduled_time IN ('10:00', '09:55', '10:05')
        ORDER BY checked_at DESC
    """)
    for row in c.fetchall():
        print(f"  {row}")
    
    print("\n=== 最近推送的 5 集 ===")
    c.execute("""
        SELECT videoSn, anime_name, volume, notified_at 
        FROM anime_notified 
        ORDER BY notified_at DESC 
        LIMIT 5
    """)
    for row in c.fetchall():
        print(f"  videoSn={row[0]}, 名稱={row[1]}, 集數={row[2]}, 推送時間={row[3]}")
    
    print("\n=== 05-04 10:00 前後推送的 ===")
    c.execute("""
        SELECT videoSn, anime_name, volume, notified_at 
        FROM anime_notified 
        WHERE notified_at LIKE '2026-05-04 10:%'
        ORDER BY notified_at DESC
    """)
    results = c.fetchall()
    if results:
        for row in results:
            print(f"  videoSn={row[0]}, 名稱={row[1]}, 集數={row[2]}, 推送時間={row[3]}")
    else:
        print("  未在 10:00 推送任何動畫")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
