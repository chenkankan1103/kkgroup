#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

db_path = '/home/e193752468/kkgroup/uibot_anime.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check bootstrap flag
cursor.execute('SELECT bootstrap_completed, completed_at FROM anime_bootstrap WHERE id = 1')
result = cursor.fetchone()
if result:
    print(f'✅ Bootstrap completed: {result[0]} at {result[1]}')
else:
    print('❌ Bootstrap flag not set')

# Check notified episodes count
cursor.execute('SELECT COUNT(*) FROM anime_notified')
count = cursor.fetchone()[0]
print(f'📊 Notified episodes in DB: {count}')

# Show first 3
cursor.execute('SELECT videoSn, anime_name, volume, notified_at FROM anime_notified LIMIT 3')
for row in cursor.fetchall():
    print(f'  - {row[1]} {row[2]}: videoSn={row[0]}')

conn.close()
