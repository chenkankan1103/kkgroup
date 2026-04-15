#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查数据库表结构"""

import sqlite3

db_path = './user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('anime_details 表列:')
cursor.execute("PRAGMA table_info(anime_details)")
for row in cursor.fetchall():
    print(f"  {row[1]}: {row[2]}")

print('\nanime_notified 表列:')
cursor.execute("PRAGMA table_info(anime_notified)")
for row in cursor.fetchall():
    print(f"  {row[1]}: {row[2]}")

conn.close()
