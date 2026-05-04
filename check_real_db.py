#!/usr/bin/env python3
import sqlite3

# 檢查根目錄的 user_data.db
db_path = '/home/e193752468/kkgroup/user_data.db'

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 查詢所有表
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in c.fetchall()]
print(f'Tables: {tables}')

if 'anime_check_history' in tables:
    print('\n=== anime_check_history 最近 5 筆 ===')
    c.execute('SELECT * FROM anime_check_history ORDER BY checked_at DESC LIMIT 5')
    for row in c.fetchall():
        print(row)
    
    print('\n=== 05-03 的檢查記錄 ===')
    c.execute('SELECT * FROM anime_check_history WHERE check_date = "2026-05-03"')
    for row in c.fetchall():
        print(row)

conn.close()
