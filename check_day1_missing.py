#!/usr/bin/env python3
import sqlite3

db_path = "/home/e193752468/kkgroup/user_data.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== 搜尋 videoSn=48723、48726 的推送歷史 ===\n")

for video_sn in [48723, 48726]:
    print(f"videoSn={video_sn}:")
    c.execute("""
        SELECT anime_name, volume, notified_at
        FROM anime_notified
        WHERE videoSn = ?
        ORDER BY notified_at DESC
    """, (video_sn,))
    
    rows = c.fetchall()
    if rows:
        for name, volume, notified_at in rows:
            print(f"  推送時間: {notified_at} | {name} | {volume}")
    else:
        print(f"  (沒有推送記錄)")
    print()

print("\n=== 檢查 anime_check_history 中的 01:00 記錄 ===\n")
c.execute("""
    SELECT check_date, scheduled_time, checked_at
    FROM anime_check_history
    WHERE scheduled_time = '01:00'
    ORDER BY checked_at DESC
    LIMIT 10
""")

for row in c.fetchall():
    check_date, scheduled_time, checked_at = row
    print(f"  {checked_at} | 日期: {check_date} | 時刻: {scheduled_time}")

conn.close()
