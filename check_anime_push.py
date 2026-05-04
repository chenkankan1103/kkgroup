#!/usr/bin/env python3
import sqlite3
from datetime import datetime

# 連接 VM 上的數據庫
db_path = "/home/e193752468/kkgroup/data/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("=== 最近推通知的 10 集 ===")
    c.execute("""
        SELECT videoSn, anime_name, notified_at 
        FROM anime_notified 
        ORDER BY notified_at DESC 
        LIMIT 10
    """)
    
    for row in c.fetchall():
        print(f"videoSn={row['videoSn']}, 名稱={row['anime_name']}, 推通知時間={row['notified_at']}")
    
    print("\n=== 搜尋「茉莉」相關 ===")
    c.execute("SELECT * FROM anime_notified WHERE anime_name LIKE '%茉莉%'")
    results = c.fetchall()
    if results:
        for row in results:
            print(f"找到: {row['anime_name']} (videoSn={row['videoSn']}, 推通知時間={row['notified_at']})")
    else:
        print("找不到「茉莉」相關的通知記錄")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
