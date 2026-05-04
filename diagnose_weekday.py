#!/usr/bin/env python3
from datetime import datetime
import pytz

TW_TZ = pytz.timezone('Asia/Taipei')

# 05-04 凌晨 03:59
dt_0359 = datetime(2026, 5, 4, 3, 59, 0, tzinfo=TW_TZ)
print(f"時間: {dt_0359}")
print(f"Python weekday: {dt_0359.weekday()} (0=Mon, 6=Sun)")

# 代碼的計算
weekday_today = (dt_0359.weekday() + 1) % 7 or 7
weekday_tomorrow = (weekday_today % 7) + 1

print(f"weekday_today 計算: ({dt_0359.weekday()} + 1) % 7 or 7 = {weekday_today}")
print(f"weekday_tomorrow 計算: ({weekday_today} % 7) + 1 = {weekday_tomorrow}")

print(f"\n對應的 API day:")
print(f"  weekday_today={weekday_today} → Day {weekday_today}")
print(f"  weekday_tomorrow={weekday_tomorrow} → Day {weekday_tomorrow}")

# 05-04 下午 13:58
dt_1358 = datetime(2026, 5, 4, 13, 58, 0, tzinfo=TW_TZ)
print(f"\n時間: {dt_1358}")
print(f"Python weekday: {dt_1358.weekday()}")

weekday_today_2 = (dt_1358.weekday() + 1) % 7 or 7
weekday_tomorrow_2 = (weekday_today_2 % 7) + 1

print(f"weekday_today 計算: ({dt_1358.weekday()} + 1) % 7 or 7 = {weekday_today_2}")
print(f"weekday_tomorrow 計算: ({weekday_today_2} % 7) + 1 = {weekday_tomorrow_2}")

print(f"\nAPI 返回 Day 1 的動畫時刻:")
print(f"  videoSn=48560: 01:00 (新番角色介紹)")
print(f"  videoSn=48727: 12:00 (MAO 吻拍)")
print(f"\nAPI 返回 Day 4 的動畫時刻:")
print(f"  videoSn=48559: 00:00 (CANDY CARIES)")
print(f"  videoSn=48694: 01:00 (某集)")
print(f"  videoSn=48872: 22:00 (Dr.STONE)")

print(f"\n問題：")
print(f"系統在 05-04 推送了 Day 1 (星期一) 的動畫")
print(f"但應該推送 Day 4 (星期四) 的動畫")
