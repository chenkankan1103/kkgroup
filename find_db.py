import sqlite3
import os

# Check multiple possible DB paths
paths = [
    'user_data.db',
    '/home/e193752468/kkgroup/user_data.db',
    '/home/e193752468/user_data.db',
]

for p in paths:
    if os.path.exists(p):
        print(f'Found: {p}')
        conn = sqlite3.connect(p)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%anime%'")
        tables = cursor.fetchall()
        print(f'  Tables: {tables}')
        if tables:
            cursor.execute(
                'SELECT DISTINCT weekStartDate FROM anime_weekly_schedule ORDER BY weekStartDate DESC LIMIT 5'
            )
            weeks = cursor.fetchall()
            print(f'  Weeks: {weeks}')
        conn.close()
    else:
        print(f'Not found: {p}')
