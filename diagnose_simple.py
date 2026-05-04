#!/usr/bin/env python3
from datetime import datetime, timedelta

# 模擬時間：05-04 10:04
now_str = "2026-05-04 10:04:07"
now = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
print(f"模擬時間: {now}")
print(f"現在的日期: {now.date()}")
print(f"Python weekday: {now.weekday()} (0=Mon, 6=Sun)")
print(f"轉換為星期 1-7: {(now.weekday() + 1) % 7 or 7}")

# 04-05 是星期幾？
# 05-04 是 5 月 4 日，2026 年
# 計算：假設 05-03 是星期二（根據前面的日期邏輯）
# 那麼 05-04 就是星期三
weekday = (now.weekday() + 1) % 7 or 7
print(f"\n今天星期: {weekday}")

# 星期三在 schedule dict 中應該有什麼時刻？
# 需要查 API 返回的數據，但根據 00:00, 00:30, 01:00, 10:00, 12:00, 22:00 推測

print("\n=== 預期時刻 ===")
times = ["00:00", "00:30", "01:00", "10:00", "12:00", "22:00"]
today = now.date()

expected_times = []
for time_str in times:
    h, m = map(int, time_str.split(':'))
    dt = datetime(today.year, today.month, today.day, h, m)
    expected_times.append((dt, time_str))

print(f"今天 ({today}) 的預期時刻:")
for dt, time_str in expected_times:
    is_past = dt <= now
    diff_min = (now - dt).total_seconds() / 60 if is_past else None
    print(f"  {time_str}: 已過={is_past}, 時差={diff_min:.1f if diff_min else 'N/A'}分")

# 找最近的已過時刻
print("\n=== 找最近已過的時刻 ===")
next_scheduled = None
for dt, time_str in expected_times:
    if dt <= now:
        next_scheduled = (dt, time_str)
        print(f"  {time_str}: 符合 (更新最新)")

if next_scheduled:
    dt, time_str = next_scheduled
    time_diff_min = (now - dt).total_seconds() / 60
    print(f"\n✅ 最近已過時刻: {time_str}")
    print(f"時差: {time_diff_min:.1f} 分")
    
    if 4 <= time_diff_min <= 6:
        print(f"✓ 在窗口 [4-6 分] 內，應推送")
    else:
        print(f"✗ 不在窗口內")
