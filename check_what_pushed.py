#!/usr/bin/env python3
import sqlite3

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=== 最近推送的動畫 ===")
    c.execute("""
        SELECT videoSn, anime_name, volume, notified_at 
        FROM anime_notified 
        ORDER BY notified_at DESC 
        LIMIT 10
    """)
    for row in c.fetchall():
        print(f"  {row[3]}: {row[1]} {row[2]}")
    
    print("\n=== 05-04 11:55 - 12:05 推送的 ===")
    c.execute("""
        SELECT videoSn, anime_name, volume, notified_at 
        FROM anime_notified 
        WHERE notified_at BETWEEN '2026-05-04 11:50' AND '2026-05-04 12:10'
        ORDER BY notified_at DESC
    """)
    results = c.fetchall()
    if results:
        for row in results:
            print(f"  {row[3]}: {row[1]} {row[2]}")
    else:
        print("  (無)")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
