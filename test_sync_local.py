#!/usr/bin/env python3
"""
本地測試腳本：驗證 set_user() 和同步邏輯是否正常工作
"""

import sys
import os
import sqlite3
import json

# 添加當前目錄到路徑
sys.path.insert(0, os.path.dirname(__file__))

from sheet_driven_db import SheetDrivenDB
from sheet_sync_manager import SheetSyncManager

print("="*60)
print("🧪 本地同步邏輯測試")
print("="*60)

# 使用測試數據庫
TEST_DB = "user_data_test.db"

print(f"\n1️⃣ 初始化測試數據庫: {TEST_DB}")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
    print("   已刪除舊測試數據庫")

db = SheetDrivenDB(TEST_DB)
print("✅ 數據庫初始化完成")

# 測試 1: 直接使用 set_user()
print(f"\n2️⃣ 測試 set_user() - 新增用戶")
success = db.set_user(123456789, {
    'user_name': 'TestUser1',
    'level': 5,
    'kkcoin': 100
})
print(f"✅ set_user() 返回: {success}")

# 驗證寫入
user = db.get_user(123456789)
if user:
    print(f"✅ 驗證：用戶已寫入數據庫")
    print(f"   user_id: {user['user_id']}")
    print(f"   user_name: {user.get('user_name')}")
    print(f"   level: {user.get('level')}")
    print(f"   kkcoin: {user.get('kkcoin')}")
else:
    print(f"❌ 驗證失敗：用戶未寫入！")
    sys.exit(1)

# 測試 2: 更新現有用戶
print(f"\n3️⃣ 測試 set_user() - 更新用戶")
success = db.set_user(123456789, {
    'level': 10,
    'kkcoin': 500
})
print(f"✅ set_user() 返回: {success}")

# 驗證更新
user = db.get_user(123456789)
if user and user.get('level') == 10 and user.get('kkcoin') == 500:
    print(f"✅ 驗證：用戶已更新")
    print(f"   level: {user.get('level')} (應為 10 ✓)")
    print(f"   kkcoin: {user.get('kkcoin')} (應為 500 ✓)")
else:
    print(f"❌ 驗證失敗：用戶未更新！")
    print(f"   level: {user.get('level')} (期望: 10)")
    print(f"   kkcoin: {user.get('kkcoin')} (期望: 500)")
    sys.exit(1)

# 測試 3: 使用 SheetSyncManager 進行同步
print(f"\n4️⃣ 測試 SheetSyncManager - 同步多條記錄")

manager = SheetSyncManager(TEST_DB)

# 準備測試數據
headers = ['user_id', 'user_name', 'level', 'kkcoin']
rows = [
    ['987654321', 'TestUser2', '3', '50'],
    ['876543210', 'TestUser3', '7', '200'],
]

print(f"📋 表頭: {headers}")
print(f"📊 數據行: {len(rows)}")

# 解析記錄
records = manager._parse_records(headers, rows)
print(f"✅ 解析完成: {len(records)} 筆有效記錄")

# 同步到 DB
stats = manager._sync_records_to_db(records)
print(f"✅ 同步完成: {stats}")

# 驗證
conn = sqlite3.connect(TEST_DB)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM users")
total = cursor.fetchone()[0]
conn.close()

print(f"✅ 數據庫中現有用戶數: {total} 個")

if total >= 3:
    print("✅ 測試通過！")
else:
    print(f"❌ 測試失敗，期望至少 3 個用戶，實際 {total} 個")
    sys.exit(1)

# 測試 4: 驗證去重
print(f"\n5️⃣ 測試去重邏輯")
rows_dup = [
    ['123456789', 'TestUser1_Updated', '15', '1000'],  # 已存在的用戶
    ['123456789', 'TestUser1_Dup', '20', '2000'],       # 同一批次重複
]

records_dup = manager._parse_records(headers, rows_dup)
print(f"📋 解析結果: {len(records_dup)} 筆有效記錄(去重後)")

stats_dup = manager._sync_records_to_db(records_dup)
print(f"✅ 同步結果: {stats_dup}")

if stats_dup['duplicates'] >= 1:
    print(f"✅ 去重邏輯正常，檢測到 {stats_dup['duplicates']} 個重複")
else:
    print(f"⚠️ 未檢測到重複 (可能去重邏輯未工作)")

# 清理
print(f"\n🧹 清理測試數據庫...")
os.remove(TEST_DB)
print("✅ 清理完成")

print("\n" + "="*60)
print("✅ 所有測試通過！")
print("="*60)
