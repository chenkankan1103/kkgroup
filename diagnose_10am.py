#!/usr/bin/env python3
import asyncio
import aiohttp
import pytz
from datetime import datetime, timedelta

TW_TZ = pytz.timezone('Asia/Taipei')

async def fetch_schedule():
    """模擬 10:04 時系統的狀態"""
    # 模擬時間：05-04 10:04
    now = datetime(2026, 5, 4, 10, 4, 7, tzinfo=TW_TZ)
    print(f"模擬時間: {now}")
    print(f"現在的日期: {now.date()}")
    print(f"現在的時刻: {now.time()}")
    
    # 模擬 API 返回（根據星期四 05-04）
    schedule = {
        "4": [  # 星期四
            {"scheduleTime": "00:00"},
            {"scheduleTime": "00:30"},
            {"scheduleTime": "01:00"},
            {"scheduleTime": "10:00"},
            {"scheduleTime": "12:00"},
            {"scheduleTime": "22:00"},
        ]
    }
    
    # 計算預期檢查時刻（今天 + 明天）
    weekday_today = (now.weekday() + 1) % 7 or 7  # Python weekday: Mon=0, Sun=6 → 1-7
    weekday_tomorrow = (weekday_today % 7) + 1
    
    print(f"\n今天的星期: {weekday_today}, 明天的星期: {weekday_tomorrow}")
    
    check_times = []
    for day_offset, weekday in [(0, str(weekday_today)), (1, str(weekday_tomorrow))]:
        target_date = (now + timedelta(days=day_offset)).date()
        print(f"\n檢查第 {day_offset} 天 (日期={target_date}, 星期={weekday}):")
        
        for anime_info in schedule.get(weekday, []):
            schedule_time = anime_info.get("scheduleTime", "")
            if schedule_time:
                scheduled_time = datetime.strptime(schedule_time, "%H:%M").time()
                scheduled_dt = datetime.combine(target_date, scheduled_time, tzinfo=TW_TZ)
                
                # 只添加未來的時刻，不添加已過期太久的時刻
                if scheduled_dt >= now - timedelta(hours=1):
                    check_times.append(scheduled_dt)
                    print(f"  ✓ {scheduled_dt} (在 1 小時內窗口)")
                else:
                    print(f"  ✗ {scheduled_dt} (超過 1 小時，跳過)")
    
    check_times.sort()
    print(f"\n=== 預期檢查時刻 (共 {len(check_times)} 個) ===")
    for dt in check_times:
        print(f"  {dt}")
    
    # 找最近的已過時刻（只限今天）
    print(f"\n=== 尋找最近的已過時刻 ===")
    today_date = now.date()
    print(f"今天日期: {today_date}")
    
    next_scheduled = None
    for dt in check_times:
        print(f"  檢查 {dt}: dt.date()={dt.date()}, dt <= now={dt <= now}")
        if dt.date() == today_date and dt <= now:
            next_scheduled = dt
            print(f"    → 符合條件，更新為最新")
    
    if next_scheduled:
        print(f"\n✅ 找到最近的已過時刻: {next_scheduled}")
        scheduled_time_str = next_scheduled.strftime("%H:%M")
        time_diff_min = (now - next_scheduled).total_seconds() / 60
        print(f"時刻字符串: {scheduled_time_str}")
        print(f"時差 (分鐘): {time_diff_min:.1f}")
        
        if 4 <= time_diff_min <= 6:
            print(f"✓ 在時間窗口內 [4-6 分鐘]，應該推送")
        else:
            print(f"✗ 不在時間窗口內，跳過")
    else:
        print(f"\n❌ 未找到最近的已過時刻")

asyncio.run(fetch_schedule())
