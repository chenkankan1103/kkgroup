#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
測試 SHEET → DB 完整流程
模擬 Google Sheet 發送的數據並測試 parse_records() 和 set_user()
"""

import sys
sys.path.insert(0, '.')

from sheet_sync_manager import SheetSyncManager

print("=" * 80)
print("測試 SHEET → DB 同步流程")
print("=" * 80)

# 創建同步管理器
sync_mgr = SheetSyncManager()

# 模擬 SHEET 發送的表頭（根據 Apps Script 中的表頭順序）
sheet_headers = [
    'user_id', 'nickname', 'level', 'xp', 'kkcoin', 'title', 'hp', 'stamina',
    'face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'streak',
    'last_work_date', 'last_action_date', 'actions_used', 'gender',
    'is_stunned', 'is_locked', 'last_recovery', 'inventory', 'character_config'
]

# 模擬 SHEET 發送的數據（3 筆玩家）
sheet_rows = [
    [111111111, 'TestA', 5, 0, 1000, '', 100, 100, 0, 0, 0, 0, 0, 0, 0, '', '', 0, '', False, False, '', '', '{}'],
    [123456789, 'Player1', 5, 0, 1000, '', 100, 100, 0, 0, 0, 0, 0, 0, 0, '', '', 0, '', False, False, '', '', '{}'],
    [222222222, 'TestB', 5, 0, 1000, '', 100, 100, 0, 0, 0, 0, 0, 0, 0, '', '', 0, '', False, False, '', '', '{}'],
]

print("\n[SHEET Header]:")
print(f"   {sheet_headers[:5]}...")
print(f"   Total {len(sheet_headers)} fields\n")

print(f"[SHEET Data Rows]: {len(sheet_rows)}\n")

# ========== Step 1: Parse records ==========
print("=" * 80)
print("Step 1: Parse records (parse_records)")
print("=" * 80)

records = sync_mgr.parse_records(sheet_headers, sheet_rows)

print(f"\nComplete: Got {len(records)} valid records\n")

for i, record in enumerate(records[:3], 1):
    print(f"Record {i}:")
    print(f"  user_id: {record.get('user_id')}")
    print(f"  nickname: {record.get('nickname')}")
    print(f"  user_name: {record.get('user_name')} (if exists)")
    print(f"  field count: {len(record)}")
    print(f"  field type sample: {[(k, type(v).__name__) for k, v in list(record.items())[:3]]}")
    print()

# ========== Step 2: Sync to DB ==========
print("=" * 80)
print("Step 2: Sync to DB (_sync_records_to_db)")
print("=" * 80)

stats = sync_mgr._sync_records_to_db(records)

print(f"\nResult Summary:")
print(f"  Inserted: {stats['inserted']} records")
print(f"  Updated: {stats['updated']} records")
print(f"  Errors: {stats['errors']} records")

if stats['errors'] > 0:
    print(f"\nError Details:")
    for err in stats['error_details']:
        print(f"  Record {err.get('record')}: {err.get('reason')}")
        if 'data_keys' in err:
            print(f"    Fields: {err['data_keys'][:5]}...")

print("\n" + "=" * 80)
print("測試完成")
print("=" * 80)
