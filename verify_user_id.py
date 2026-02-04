#!/usr/bin/env python3
"""
驗證 user_id 導出和導入的一致性
診斷 user_id 科學記號問題
"""
import sqlite3
from datetime import datetime

print("=" * 70)
print("🔍 user_id 導出/導入一致性驗證")
print("=" * 70)

# 1. 檢查 DB 中的 user_id
print("\n📊 [1/3] 檢查 DB 中的 user_id")
print("-" * 70)

try:
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, level, kkcoin FROM users LIMIT 5")
    db_records = cursor.fetchall()
    conn.close()
    
    print(f"✅ DB 中的前 5 筆記錄:")
    for idx, (user_id, level, kkcoin) in enumerate(db_records, 1):
        print(f"   {idx}. user_id={user_id} (type: {type(user_id).__name__}), level={level}, kkcoin={kkcoin}")
except Exception as e:
    print(f"❌ DB 讀取失敗: {e}")
    db_records = []

# 2. 檢查 SHEET 中的 user_id
print("\n📋 [2/3] 檢查 SHEET 中的 user_id")
print("-" * 70)

try:
    from google.oauth2.service_account import Credentials
    import gspread
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    SHEET_ID = "1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM"
    SHEET_NAME = "玩家資料"
    
    creds = Credentials.from_service_account_file('google_credentials.json', scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SHEET_ID)
    sheet = spreadsheet.worksheet(SHEET_NAME)
    
    all_values = sheet.get_all_values()
    
    # 獲取 user_id 列的索引
    headers = all_values[1]
    user_id_col = headers.index('user_id') if 'user_id' in headers else -1
    
    if user_id_col >= 0:
        print(f"✅ SHEET 中的前 5 筆記錄 (user_id 在第 {user_id_col + 1} 列):")
        
        sheet_records = []
        for row_idx, row in enumerate(all_values[2:7], start=3):
            if not any(row):
                continue
            user_id_str = row[user_id_col] if user_id_col < len(row) else ''
            sheet_records.append(user_id_str)
            print(f"   {row_idx}. user_id='{user_id_str}' (raw)")
            
            # 嘗試轉換
            try:
                user_id_int = int(float(user_id_str))
                print(f"        → 轉換後: {user_id_int} (type: int)")
            except:
                print(f"        → ❌ 轉換失敗")
    else:
        print(f"❌ SHEET 中找不到 user_id 列")
        sheet_records = []
        
except ImportError:
    print("⚠️ 缺少 google 模塊，跳過 SHEET 檢查")
    sheet_records = []
except Exception as e:
    print(f"❌ SHEET 讀取失敗: {e}")
    sheet_records = []

# 3. 驗證一致性
print("\n🔗 [3/3] 驗證一致性")
print("-" * 70)

if db_records and sheet_records:
    print(f"DB 記錄數: {len(db_records)}, SHEET 記錄數: {len(sheet_records)}")
    
    # 比對前幾筆
    for idx in range(min(len(db_records), len(sheet_records))):
        db_uid = db_records[idx][0]
        sheet_uid_str = sheet_records[idx]
        
        try:
            sheet_uid = int(float(sheet_uid_str))
        except:
            sheet_uid = None
        
        if sheet_uid is not None:
            match = "✅" if db_uid == sheet_uid else "❌"
            print(f"{match} 記錄 {idx+1}: DB={db_uid}, SHEET={sheet_uid_str} → {sheet_uid}")
        else:
            print(f"❌ 記錄 {idx+1}: DB={db_uid}, SHEET={sheet_uid_str} (無法轉換)")

# 4. 檢查科學記號問題
print("\n🔬 [4/4] 科學記號檢查")
print("-" * 70)

print("Discord ID 特性:")
print("   - 大小: 18-20 位數字")
print("   - 範圍: ~1.0E+17 ~ 9.2E+17")
print("   - 易於被 Google Sheets 轉成科學記號")

if sheet_records:
    scientific_count = sum(1 for uid_str in sheet_records if 'e' in uid_str.lower())
    if scientific_count > 0:
        print(f"\n🔴 警告：檢測到 {scientific_count} 個科學記號格式的 user_id")
        print("   解決方案: 導出時將 user_id 轉成字符串（已在最新代碼中修復）")
    else:
        print(f"\n✅ 沒有檢測到科學記號格式")

print("\n" + "=" * 70)
print("🎯 建議")
print("=" * 70)
print("""
如果 DB 和 SHEET 的 user_id 不一致:

1. ❌ 問題：user_id 在 SHEET 中是科學記號 (1.23E+17)
   ✅ 解決：已修復 - 導出時將 user_id 轉成字符串

2. ❌ 問題：導出後 user_id 仍然是數字格式
   ✅ 解決：執行 /export_to_sheet 重新導出

3. ❌ 問題：同步後 DB 中的 user_id 變成 0
   ✅ 解決：檢查 SHEET 中的 user_id 是否被正確識別

部署修復:
1. git pull
2. sudo systemctl restart discord-bot.service
3. /export_to_sheet (重新導出以應用修復)
4. 再次運行本診斷工具驗證
""")
