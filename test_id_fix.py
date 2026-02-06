"""
測試 Discord ID 精度損失修復

模擬 Google Sheets 返回浮點數的情況，驗證修復是否有效
"""

import sys
sys.path.insert(0, '/tmp/test_kkgroup')

from sheet_driven_db import SheetDrivenDB
from sheet_sync_manager import SheetSyncManager

print("=" * 80)
print("Discord ID 精度損失修復測試")
print("=" * 80)

# 【測試1】驗證 _convert_value() 修復
print("\n【測試1】驗證 _convert_value() 修復\n")

db = SheetDrivenDB(':memory:')

test_ids = [
    ('776464975551660123', 'string'),     # 原始 ID（字符串）
    (776464975551660123, 'int'),          # 原始 ID（整數）
    (7.764649755516601e+17, 'float'),    # 浮點精度損失版本
    ('7.764649755516601e+17', 'sci'),    # 科學計數法字符串
]

print("測試結果：")
for val, source in test_ids:
    result = db._convert_value('user_id', val)
    expected = 776464975551660123
    status = "✓" if result == expected else "✗"
    print(f"{status} {source:8} 輸入: {str(val):30} → 結果: {result}")

# 【測試2】驗證同名去重邏輯
print("\n【測試2】驗證同名去重邏輯\n")

# 模擬 SHEET 數據（包含同名異 ID）
headers = ['user_id', 'nickname', 'level', 'kkcoin']
rows = [
    ['776464975551660123', '凱文', '4', '100006'],      # 原始
    ['776464975551660160', '凱文', '4', '111340'],      # 幽靈（精度損失版本）
    ['260266786719531008', '夜神獅獅', '4', '70004'],   # 原始
    ['260266786719531009', '夜神獅獅', '4', '70021'],   # 幽靈
]

mgr = SheetSyncManager(':memory:')
records = mgr._parse_records(headers, rows)

print(f"解析結果：{len(records)} 條有效記錄")
for rec in records:
    print(f"  - {rec['nickname']:15} (ID: {rec['user_id']})")

print("\n✅ 測試完成！")
print("\n預期結果：")
print("  - 只應該有 2 個用戶（凱文、夜神獅獅）")
print("  - 每個用戶只有 1 個 ID（最小的）")
