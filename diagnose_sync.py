#!/usr/bin/env python3
"""
SHEET 同步診斷工具
檢查：
1. Google Sheets 連接和數據結構
2. 數據庫結構和記錄數量
3. 識別任何潛在問題
"""
import sqlite3
import json
from datetime import datetime

print("=" * 60)
print("🔍 SHEET 同步診斷工具")
print("=" * 60)

# 1. 檢查數據庫
print("\n📊 [1/3] 數據庫診斷")
print("-" * 60)

try:
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    
    # 檢查表結構
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    print(f"✅ users 表存在，共 {len(columns)} 列：")
    for col in columns:
        print(f"   - {col[1]}: {col[2]}")
    
    # 檢查記錄數量
    cursor.execute("SELECT COUNT(*) FROM users")
    total_records = cursor.fetchone()[0]
    print(f"\n✅ 總記錄數: {total_records} 筆")
    
    # 檢查是否有重複 user_id
    cursor.execute("SELECT user_id, COUNT(*) as cnt FROM users GROUP BY user_id HAVING COUNT(*) > 1")
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"🔴 警告：發現 {len(duplicates)} 個重複的 user_id:")
        for user_id, cnt in duplicates[:10]:
            print(f"   - user_id {user_id}: {cnt} 筆重複")
    else:
        print(f"✅ 沒有重複的 user_id")
    
    # 檢查 kkcoin 等關鍵欄位的統計
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            AVG(kkcoin) as avg_kkcoin,
            MAX(kkcoin) as max_kkcoin,
            MIN(level) as min_level,
            MAX(level) as max_level
        FROM users
    """)
    stats = cursor.fetchone()
    print(f"\n📈 數據統計:")
    print(f"   - 平均 KKCoin: {stats[1]:.0f}")
    print(f"   - 最高 KKCoin: {stats[2]}")
    print(f"   - 等級範圍: {stats[3]} ~ {stats[4]}")
    
    # 檢查最近修改的記錄
    cursor.execute("""
        SELECT user_id, level, xp, kkcoin, last_action_date 
        FROM users 
        WHERE last_action_date IS NOT NULL
        ORDER BY last_action_date DESC 
        LIMIT 5
    """)
    recent = cursor.fetchall()
    if recent:
        print(f"\n⏰ 最近修改的 5 條記錄:")
        for row in recent:
            print(f"   - user_id {row[0]}: level {row[1]}, kkcoin {row[3]}, 最後活動: {row[4]}")
    
    conn.close()
    print("\n✅ 數據庫診斷完成")

except Exception as e:
    print(f"❌ 數據庫診斷失敗: {e}")

# 2. 檢查 Google Sheets 連接
print("\n📋 [2/3] Google Sheets 連接診斷")
print("-" * 60)

try:
    from google.oauth2.service_account import Credentials
    import gspread
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    SHEET_ID = "1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM"
    SHEET_NAME = "玩家資料"
    
    # 連接 Google Sheets
    creds = Credentials.from_service_account_file('google_credentials.json', scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SHEET_ID)
    
    print(f"✅ Google Sheets 連接成功")
    print(f"   - 文件名: {spreadsheet.title}")
    print(f"   - 工作表: {[ws.title for ws in spreadsheet.worksheets()]}")
    
    sheet = spreadsheet.worksheet(SHEET_NAME)
    all_values = sheet.get_all_values()
    
    print(f"\n✅ {SHEET_NAME} 工作表信息:")
    print(f"   - 行數: {len(all_values)}")
    print(f"   - 列數: {len(all_values[0]) if all_values else 0}")
    
    # 檢查標題行
    if len(all_values) >= 2:
        print(f"\n📋 標題檢查:")
        print(f"   - 第 1 行（分組標題）: {all_values[0][:3]}... (共 {len(all_values[0])} 列)")
        print(f"   - 第 2 行（實際標題）: {all_values[1][:3]}... (共 {len(all_values[1])} 列)")
        if len(all_values) >= 3:
            print(f"   - 第 3 行（數據範例）: {all_values[2][:3]}...")
    
    # 檢查數據記錄（跳過空行）
    data_rows = [row for row in all_values[2:] if any(row)]
    print(f"\n📊 SHEET 數據統計:")
    print(f"   - 總行數（包括空行）: {len(all_values)}")
    print(f"   - 實際數據行: {len(data_rows)}")
    
    # 檢查是否有重複 user_id
    if len(all_values) >= 2:
        headers = all_values[1]
        user_id_col = headers.index('user_id') if 'user_id' in headers else -1
        
        if user_id_col >= 0:
            user_ids = [row[user_id_col] for row in data_rows if user_id_col < len(row)]
            print(f"   - 提取的 user_id 數量: {len(user_ids)}")
            print(f"   - 唯一 user_id 數量: {len(set(user_ids))}")
    
    print("\n✅ Google Sheets 診斷完成")

except Exception as e:
    print(f"❌ Google Sheets 診斷失敗: {e}")
    import traceback
    traceback.print_exc()

# 3. 比較 DB 和 SHEET
print("\n⚖️ [3/3] DB ↔ SHEET 比較")
print("-" * 60)

try:
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    db_count = cursor.fetchone()[0]
    conn.close()
    
    print(f"✅ 對比結果:")
    print(f"   - 數據庫記錄: {db_count}")
    print(f"   - SHEET 記錄: {len(data_rows)}")
    
    if db_count == len(data_rows):
        print(f"   ✅ 記錄數量一致！")
    else:
        diff = len(data_rows) - db_count
        if diff > 0:
            print(f"   ⚠️ SHEET 比 DB 多 {diff} 筆記錄（可能包含未同步的編輯）")
        else:
            print(f"   ⚠️ DB 比 SHEET 多 {-diff} 筆記錄（可能 SHEET 被清空或編輯過）")

except Exception as e:
    print(f"❌ 比較失敗: {e}")

print("\n" + "=" * 60)
print("✅ 診斷完成")
print("=" * 60)
print("\n💡 建議:")
print("   1. 若記錄數量不一致，執行 /sync_from_sheet 同步 SHEET 到 DB")
print("   2. 若記錄數量一致，執行 /export_to_sheet 驗證 DB→SHEET 導出")
print("   3. 檢查 bot 日誌以查看同步詳細過程")
