#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db_path = "/home/e193752468/kkgroup/user_data.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== 檢查 05-04 的推送記錄 ===\n")

# 查看 anime_notified 表的詳細信息
c.execute("""
    SELECT videoSn, animeSn, anime_name, volume, notified_at, cover_url 
    FROM anime_notified 
    WHERE notified_at LIKE '2026-05-04%'
    ORDER BY notified_at DESC
""")

for row in c.fetchall():
    video_sn, anime_sn, name, volume, notified_at, url = row
    print(f"videoSn: {video_sn}")
    print(f"animeSn: {anime_sn}")
    print(f"名稱: {name}")
    print(f"Volume: {volume}")
    print(f"推送時間: {notified_at}")
    print()

# 查看 anime_check_history 的所有 05-04 記錄
print("=== 05-04 的檢查歷史 ===\n")
c.execute("""
    SELECT check_date, scheduled_time, checked_at 
    FROM anime_check_history 
    WHERE check_date LIKE '2026-05-04%'
    ORDER BY checked_at DESC
""")

for row in c.fetchall():
    check_date, scheduled_time, checked_at = row
    print(f"檢查日期: {check_date}")
    print(f"排定時刻: {scheduled_time}")
    print(f"檢查時間: {checked_at}")
    print()

# 查看前一天和後一天的推送
print("=== 05-03 的推送記錄 ===\n")
c.execute("""
    SELECT videoSn, anime_name, notified_at 
    FROM anime_notified 
    WHERE notified_at LIKE '2026-05-03%'
    ORDER BY notified_at DESC
    LIMIT 5
""")

for row in c.fetchall():
    video_sn, name, notified_at = row
    print(f"  {notified_at} | videoSn={video_sn} | {name}")

print("\n=== 05-05 的推送記錄 ===\n")
c.execute("""
    SELECT videoSn, anime_name, notified_at 
    FROM anime_notified 
    WHERE notified_at LIKE '2026-05-05%'
    ORDER BY notified_at DESC
    LIMIT 5
""")

for row in c.fetchall():
    video_sn, name, notified_at = row
    print(f"  {notified_at} | videoSn={video_sn} | {name}")

conn.close()
