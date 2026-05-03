#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详细分析最后的检查时刻和时间差"""

import sqlite3
from datetime import datetime, timedelta
import pytz
import aiohttp
import asyncio

TW_TZ = pytz.timezone('Asia/Taipei')
db_path = '/home/e193752468/kkgroup/user_data.db'

print('\n【详细分析】')
print('=' * 80)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 获取最后 20 条检查记录，包括具体的日期和时间
cur.execute('''
  SELECT check_date, scheduled_time, checked_at
  FROM anime_check_history 
  ORDER BY checked_at DESC
  LIMIT 20
''')

records = cur.fetchall()
print(f'\n最后 {len(records)} 条检查记录：')
print('-' * 80)

for i, (check_date, scheduled_time, checked_at) in enumerate(records, 1):
    # 解析 checked_at 时间
    checked_dt = datetime.fromisoformat(checked_at.replace('Z', '+00:00')).astimezone(TW_TZ)
    print(f'{i:2d}. [{check_date} {scheduled_time}]')
    print(f'      checked_at: {checked_dt.strftime("%Y-%m-%d %H:%M:%S")}')

# 分析时间模式
print('\n【时间模式分析】')
print('-' * 80)

scheduled_times = [record[1] for record in records]
unique_times = set(scheduled_times)
print(f'唯一的检查时刻: {sorted(unique_times)}')
print(f'共 {len(records)} 条记录，{len(unique_times)} 个唯一时刻')

# 计算间隔
if len(records) > 1:
    print('\n【检查之间的时间间隔】')
    print('-' * 80)
    for i in range(min(5, len(records)-1)):
        current = datetime.fromisoformat(records[i][2].replace('Z', '+00:00')).astimezone(TW_TZ)
        previous = datetime.fromisoformat(records[i+1][2].replace('Z', '+00:00')).astimezone(TW_TZ)
        diff = (previous - current).total_seconds() / 3600
        print(f'  {i+1}->{ i+2}: {diff:.1f} 小时前')

# 现在分析当前时间与最后检查的关系
now = datetime.now(TW_TZ)
last_checked_dt = datetime.fromisoformat(records[0][2].replace('Z', '+00:00')).astimezone(TW_TZ)
mins_ago = (now - last_checked_dt).total_seconds() / 60

print(f'\n【现在时间与最后检查的关系】')
print('-' * 80)
print(f'现在(台湾): {now.strftime("%Y-%m-%d %H:%M:%S")}')
print(f'最后检查: {last_checked_dt.strftime("%Y-%m-%d %H:%M:%S")}')
print(f'距离: {mins_ago:.0f} 分钟前')

# 分析API可达性和日程表
async def check_schedule():
    print(f'\n【API 日程表分析】')
    print('-' * 80)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'https://api.gamer.com.tw/mobile_app/anime/v3/index.php',
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    schedule = data.get('data', {}).get('newAnimeSchedule', {})
                    print(f'API 可达，返回日期数: {len(schedule)}')
                    
                    # 显示今天和明天的时刻
                    weekday_today = (now.weekday() + 1) % 7
                    if weekday_today == 0:
                        weekday_today = 7
                    weekday_tomorrow = (weekday_today % 7) + 1
                    
                    print(f'\n今天 (星期 {weekday_today}):')
                    today_schedule = schedule.get(str(weekday_today), [])
                    if today_schedule:
                        times = [item.get('scheduleTime', '?') for item in today_schedule]
                        print(f'  时刻数: {len(times)}')
                        print(f'  具体时刻: {times[:10]}...')
                    else:
                        print(f'  没有安排')
                    
                    print(f'\n明天 (星期 {weekday_tomorrow}):')
                    tomorrow_schedule = schedule.get(str(weekday_tomorrow), [])
                    if tomorrow_schedule:
                        times = [item.get('scheduleTime', '?') for item in tomorrow_schedule]
                        print(f'  时刻数: {len(times)}')
                        print(f'  具体时刻: {times[:10]}...')
                    else:
                        print(f'  没有安排')
                else:
                    print(f'API 返回状态: {resp.status}')
    except Exception as e:
        print(f'API 查询失败: {e}')

asyncio.run(check_schedule())

conn.close()
print('\n' + '=' * 80)
