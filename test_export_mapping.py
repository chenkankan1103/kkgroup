#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, '.')

from sheet_driven_db import SheetDrivenDB

# 連接到本地 DB（如果有備份）
# 但由於我們沒有本地 DB，就模擬導出邏輯

# 模擬 DB 行（包含 user_name 但 nickname 為空）
test_row_dict = {
    'user_id': '111111111',
    'nickname': '',
    'user_name': 'TestA',
    'level': '5',
    'xp': '0',
    'kkcoin': '1000'
}

print("=" * 60)
print("測試欄位映射邏輯")
print("=" * 60)
print(f"\n原始行數據：")
for key, val in test_row_dict.items():
    print(f"  {key}: '{val}'")

# 應用映射邏輯（與代碼中相同）
print(f"\n應用映射：如果 nickname 為空但 user_name 有值，用 user_name 填充 nickname")
if (not test_row_dict.get('nickname') or test_row_dict.get('nickname') == '') and test_row_dict.get('user_name'):
    test_row_dict['nickname'] = test_row_dict.get('user_name')

print(f"\n映射後的行數據：")
for key, val in test_row_dict.items():
    print(f"  {key}: '{val}'")

print(f"\n✅ nickname 映射結果: '{test_row_dict['nickname']}'")

if test_row_dict['nickname'] == 'TestA':
    print("✅ 映射成功！")
else:
    print("❌ 映射失敗！")
