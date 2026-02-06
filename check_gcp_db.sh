#!/bin/bash
cd /home/e193752468/kkgroup
source venv/bin/activate
python3 -c "
import sqlite3
conn = sqlite3.connect('user_data.db')
c = conn.cursor()
c.execute('SELECT user_id, nickname FROM users ORDER BY user_id DESC')
users = c.fetchall()
print(f'總用戶數: {len(users)}')
for uid, nick in users:
    status = '✅' if uid >= 100000000000000000 else '❌'
    print(f'{status} {uid:20d} | {nick or \"(無)\"}'[:60])
conn.close()
" > /tmp/gcp_db_status.txt 2>&1

# Ensure file is readable
chmod 644 /tmp/gcp_db_status.txt
