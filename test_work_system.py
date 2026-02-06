#!/usr/bin/env python3
"""
測試打卡系統在 ID 修復後是否能正常工作
"""
from db_adapter import get_user, set_user
import json

# 27 個已修復的用戶中的幾個進行測試
test_cases = [
    (344018672056139786, "赤月"),
    (401694438449217548, "落華"),
    (1209509919699505184, "餒餒補給站"),  # 新修復的
]

print("=" * 60)
print("測試打卡系統資料庫連接")
print("=" * 60)

for user_id, nickname in test_cases:
    print(f"\n測試: {nickname} (ID: {user_id})")
    print("-" * 40)
    
    user = get_user(user_id)
    
    if user:
        print(f"✅ 成功找到用戶")
        print(f"  暱稱: {user.get('nickname', 'N/A')}")
        print(f"  等級: {user.get('level', 0)}")
        print(f"  經驗值: {user.get('xp', 0)}")
        print(f"  連勤: {user.get('streak', 0)}")
        print(f"  上次打卡: {user.get('last_work_date', 'N/A')}")
    else:
        print(f"❌ ERROR: 找不到用戶!")
        print(f"  嘗試的 ID: {user_id}")

print("\n" + "=" * 60)
print("測試結果統計")
print("=" * 60)

found_count = 0
total_count = len(test_cases)

for user_id, nickname in test_cases:
    if get_user(user_id):
        found_count += 1

print(f"成功找到: {found_count}/{total_count} 個用戶")

if found_count == total_count:
    print("✅ 所有用戶都能正確查找！打卡系統應該可以正常工作。")
else:
    print(f"❌ {total_count - found_count} 個用戶無法查找，打卡系統可能有問題。")
