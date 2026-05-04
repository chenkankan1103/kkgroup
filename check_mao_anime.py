#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=== 05-04 所有推送過的動畫 ===")
    c.execute("""
        SELECT videoSn, anime_name, volume, notified_at 
        FROM anime_notified 
        WHERE notified_at LIKE '2026-05-04%'
        ORDER BY notified_at DESC
    """)
    
    for row in c.fetchall():
        video_sn, name, volume, notified_at = row
        print(f"  {notified_at} | videoSn={video_sn:5} | {name} {volume}")
    
    print("\n=== 檢查「MAO 吻拍」的信息 ===")
    c.execute("SELECT * FROM anime_notified WHERE anime_name LIKE '%MAO%' ORDER BY notified_at DESC LIMIT 5")
    for row in c.fetchall():
        print(f"  {row}")
    
    print("\n=== 05-04 所有檢查過的時刻 ===")
    c.execute("""
        SELECT scheduled_time, checked_at 
        FROM anime_check_history 
        WHERE check_date = '2026-05-04'
        ORDER BY scheduled_time
    """)
    
    for row in c.fetchall():
        time, checked_at = row
        print(f"  {time:>5} | checked_at={checked_at}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
