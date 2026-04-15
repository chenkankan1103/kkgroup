#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查20分钟前遗漏的动画推送"""

import sqlite3
from datetime import datetime, timedelta
import pytz

TW_TZ = pytz.timezone('Asia/Taipei')
db_path = './user_data.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 60)
print('🔍 检查遗漏的动画推送')
print('=' * 60)
print()

# 查看 bootstrap 状态
cursor.execute('SELECT * FROM anime_bootstrap')
bootstrap = cursor.fetchone()
print('📌 Bootstrap 状态:')
if bootstrap and bootstrap[1]:
    print(f'   ✅ 已完成初始化')
else:
    print(f'   ⚠️  未完成初始化（需要首次运行来记录当前所有动画）')
print()

# 查看最后 10 个已推送的动画
print('📺 最近推送的 10 部动画:')
cursor.execute('SELECT videoSn, anime_name, notified_at FROM anime_notified ORDER BY notified_at DESC LIMIT 10')
notified = cursor.fetchall()
if notified:
    for idx, (sn, name, time) in enumerate(notified, 1):
        print(f'   {idx}. [{sn}] {name}')
        print(f'      推送时间: {time}')
else:
    print('   (未找到已推送的记录)')
print()

# 查看缓存统计
cursor.execute('SELECT COUNT(*) FROM anime_details')
count = cursor.fetchone()[0]
print(f'💾 动画详情缓存: {count} 条记录')
print()

# 查看最新缓存的前 5 个动画
print('🎬 最新缓存的 5 部动画:')
cursor.execute('SELECT anime_sn, title, popular FROM anime_details ORDER BY ROWID DESC LIMIT 5')
for idx, (asn, title, views) in enumerate(cursor.fetchall(), 1):
    print(f'   {idx}. [{asn}] {title}')
    print(f'      观看数: {views if views else "N/A"}')

conn.close()

print()
print('=' * 60)
print('💡 建议: 如果 bootstrap 未完成，运行 /anime_start 命令启动任务')
print('=' * 60)
