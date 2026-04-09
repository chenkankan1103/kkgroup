#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

conn = sqlite3.connect('uibot_anime_latest.db')
c = conn.cursor()

# Show tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f'Tables: {tables}')

# Show anime_notified count
c.execute('SELECT COUNT(*) FROM anime_notified')
count = c.fetchone()[0]
print(f'Notified episodes: {count}')

if count > 0:
    c.execute('SELECT videoSn, anime_name, volume FROM anime_notified LIMIT 5')
    print('First 5 episodes:')
    for row in c.fetchall():
        print(f'  {row[1]} {row[2]} (videoSn={row[0]})')

# Show bootstrap status
c.execute('SELECT * FROM anime_bootstrap')
bootstrap = c.fetchall()
print(f'\nBootstrap completed: {len(bootstrap) > 0}')
if bootstrap:
    for row in bootstrap:
        print(f'  bootstrap_completed={row[1]}, completed_at={row[2]}')

conn.close()
