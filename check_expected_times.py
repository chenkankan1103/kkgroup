#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=== 05-04 前後推送的所有集 ===")
    c.execute("""
        SELECT DISTINCT strftime('%H:%M', notified_at), COUNT(*) as cnt
        FROM anime_notified 
        WHERE notified_at LIKE '2026-05-04%'
        GROUP BY strftime('%H:%M', notified_at)
        ORDER BY notified_at DESC
    """)
    
    times_pushed = {}
    for row in c.fetchall():
        time_pushed, count = row
        times_pushed[time_pushed] = count
        print(f"  {time_pushed}: {count} 集被推送")
    
    print("\n=== 預期應該推送的時刻 ===")
    expected_times = ["00:00", "00:30", "01:00", "10:00", "12:00", "16:30", "17:00", "22:00", "23:00"]
    for t in expected_times:
        status = "✓ 已推送" if t in times_pushed else "✗ 未推送"
        print(f"  {t}: {status}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
