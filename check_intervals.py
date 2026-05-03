#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime
import pytz

TW_TZ = pytz.timezone('Asia/Taipei')
conn = sqlite3.connect('user_data.db')
cur = conn.cursor()

print('\n【分析】最近2小时的检查间隔：')
print('-' * 80)

# Simple analysis without LAG
cur.execute('''
  SELECT check_date, scheduled_time, checked_at
  FROM anime_check_history 
  WHERE checked_at >= datetime('now', '-2 hours')
  ORDER BY checked_at DESC
  LIMIT 20
''')

rows = cur.fetchall()
prev_checked = None
for date, time, checked_at in rows:
    interval = ''
    if prev_checked:
        prev_dt = datetime.fromisoformat(prev_checked)
        curr_dt = datetime.fromisoformat(checked_at)
        diff_sec = (prev_dt - curr_dt).total_seconds()
        interval = f' (gap: {int(diff_sec)}s)'
    
    print(f'  [{date} {time}] {checked_at}{interval}')
    prev_checked = checked_at

conn.close()
