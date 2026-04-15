#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补偿遗漏的动画推送"""

import sqlite3
from datetime import datetime, timedelta
import pytz

TW_TZ = pytz.timezone('Asia/Taipei')
db_path = './user_data.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 60)
print('🎬 检查遗漏的动画推送')
print('=' * 60)
print()

# 查看 anime_details 中有多少条记录
cursor.execute('SELECT COUNT(*) FROM anime_details')
total_anime = cursor.fetchone()[0]
print(f'📚 动画详情缓存: {total_anime} 条')

# 查看 anime_notified 中有多少条已推送记录
cursor.execute('SELECT COUNT(*) FROM anime_notified')
notified_count = cursor.fetchone()[0]
print(f'✅ 已推送记录: {notified_count} 条')

# 找出在 anime_details 中但不在 anime_notified 中的动画
print()
print('🔍 查找未推送的动画...')
cursor.execute('''
    SELECT ad.animeSn, ad.title, ad.popular 
    FROM anime_details ad
    WHERE ad.animeSn NOT IN (SELECT animeSn FROM anime_notified)
    ORDER BY ad.rowid DESC
    LIMIT 10
''')

unnotified = cursor.fetchall()
if unnotified:
    print(f'\n⏭️  发现 {len(unnotified)} 部未推送的动画（最多显示 10 部）:\n')
    for idx, (asn, title, views) in enumerate(unnotified, 1):
        print(f'  {idx}. [AnimeSn: {asn}] {title}')
        print(f'     浏览量: {views if views else "N/A"}')
else:
    print('\n✨ 所有动画都已推送过了')

# 查看最近的推送记录
print()
print('=' * 60)
print('📺 最近的推送记录（最后 5 条）:')
print('=' * 60)
cursor.execute('''
    SELECT animeSn, anime_name, notified_at 
    FROM anime_notified 
    ORDER BY notified_at DESC 
    LIMIT 5
''')

for idx, (asn, name, time) in enumerate(cursor.fetchall(), 1):
    print(f'{idx}. [AnimeSn: {asn}] {name}')
    print(f'   推送时间: {time}')

conn.close()

print()
print('=' * 60)
print('💡 建议:')
print('  - 如果需要推送遗漏的动画，使用 /anime_test 命令测试推送')
print('  - 或者运行 /anime_start 命令重新初始化系统')
print('=' * 60)
