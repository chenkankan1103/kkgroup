#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 測試欄位映射邏輯

test_records = [
    {'user_id': '111', 'nickname': '', 'user_name': 'TestA', 'level': '5'},
    {'user_id': '222', 'nickname': 'Player1', 'user_name': 'TestB', 'level': '5'},
    {'user_id': '333', 'nickname': '', 'user_name': '', 'level': '5'},
]

print("=== 欄位映射測試 ===\n")
print("應用規則：如果 nickname 為空但 user_name 有值，用 user_name 填充 nickname\n")

for record in test_records:
    print(f"原始: user_id={record['user_id']}, nickname='{record['nickname']}', user_name='{record['user_name']}'")
    
    # 應用映射邏輯 (與 sheet_sync_manager.py 和 sheet_driven_db.py 中的邏輯相同)
    if (not record.get('nickname') or record.get('nickname') == '') and record.get('user_name'):
        record['nickname'] = record.get('user_name')
    
    print(f"映射後: user_id={record['user_id']}, nickname='{record['nickname']}', user_name='{record['user_name']}'")
    print()

print("\n✅ 預期結果：")
print("  記錄 1: nickname 應為 'TestA' (從 user_name 映射)")
print("  記錄 2: nickname 應保留 'Player1' (已有值，不覆蓋)")
print("  記錄 3: nickname 應保留空值 (user_name 為空，無法映射)")
