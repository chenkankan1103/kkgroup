#!/usr/bin/env python3
import sqlite3

db_path = "/home/e193752468/kkgroup/user_data.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== 查看所有 01:00 和 22:00 的檢查記錄 ===\n")

for time_str in ['01:00', '22:00', '12:00']:
    print(f"\n=== 時刻 {time_str} ===")
    c.execute("""
        SELECT check_date, checked_at
        FROM anime_check_history
        WHERE scheduled_time = ?
        ORDER BY checked_at DESC
        LIMIT 20
    """, (time_str,))
    
    for row in c.fetchall():
        check_date, checked_at = row
        day_diff = abs(int(check_date.split('-')[2]) - int(checked_at.split()[0].split('-')[2]))
        marker = "⚠️ 提前標記" if day_diff > 0 else "✅ 同日檢查"
        print(f"  {marker} | 日期: {check_date} | 檢查時間: {checked_at}")

conn.close()
