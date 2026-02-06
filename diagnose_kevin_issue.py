#!/usr/bin/env python3
"""
診斷凱文重複和虛擬人物問題
連接 GCP 資料庫和 Google Sheets
"""
import sqlite3
import json
import os
from pathlib import Path

# 讀取環境變數
from dotenv import load_dotenv
load_dotenv('/home/e193752468/kkgroup/.env')

# 導入 Sheet 同步相關模組
try:
    from sheet_sync_manager import SheetSyncManager
    from sheet_driven_db import get_db_instance
except ImportError:
    print("⚠️ 無法導入本地模組，使用 GCP 脆弱診斷")

print("=" * 80)
print("凱文重複和虛擬人物診斷")
print("=" * 80)

# 連接 GCP 資料庫
GCP_DB_PATH = '/home/e193752468/kkgroup/user_data.db'

try:
    conn = sqlite3.connect(GCP_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"\n✅ 連接到 GCP 資料庫: {GCP_DB_PATH}")
    
    # 1. 查詢凱文相關用戶
    print("\n" + "=" * 80)
    print("【檢查 1】資料庫中的凱文")
    print("=" * 80 + "\n")
    
    cursor.execute("""
        SELECT user_id, nickname, level, xp, kkcoin, title, 
               hp, stamina, equipment, _created_at, _updated_at 
        FROM users 
        WHERE nickname LIKE '%凱文%' OR user_id = 776464975551660123
        ORDER BY user_id
    """)
    
    kevin_records = cursor.fetchall()
    print(f"找到 {len(kevin_records)} 個凱文相關記錄:\n")
    
    for i, record in enumerate(kevin_records, 1):
        print(f"【記錄 {i}】")
        print(f"  user_id: {record['user_id']}")
        print(f"  nickname: {record['nickname']}")
        print(f"  level: {record['level']}")
        print(f"  xp: {record['xp']}")
        print(f"  kkcoin: {record['kkcoin']}")
        print(f"  title: {record['title']}")
        print(f"  hp: {record['hp']}")
        print(f"  stamina: {record['stamina']}")
        print(f"  equipment: {record['equipment']}")
        print(f"  created: {record['_created_at']}")
        print(f"  updated: {record['_updated_at']}")
        print()
    
    # 2. 檢查虛擬人物
    print("=" * 80)
    print("【檢查 2】虛擬人物（Unknown_* 或沒有昵稱）")
    print("=" * 80 + "\n")
    
    cursor.execute("""
        SELECT user_id, nickname, level, xp, kkcoin 
        FROM users 
        WHERE nickname LIKE 'Unknown_%' 
           OR nickname IS NULL 
           OR nickname = ''
           OR nickname LIKE '虛擬人物%'
        ORDER BY user_id
    """)
    
    virtual_users = cursor.fetchall()
    print(f"找到 {len(virtual_users)} 個虛擬人物:\n")
    
    for user in virtual_users[:20]:  # 只顯示前 20 個
        print(f"  ID: {user['user_id']:20} | 名稱: {user['nickname']:30} | 等級: {user['level']} | KK幣: {user['kkcoin']}")
    
    if len(virtual_users) > 20:
        print(f"  ... 還有 {len(virtual_users) - 20} 個虛擬人物")
    
    # 3. 檢查 user_id 重複
    print("\n" + "=" * 80)
    print("【檢查 3】user_id 重複")
    print("=" * 80 + "\n")
    
    cursor.execute("""
        SELECT user_id, COUNT(*) as count, GROUP_CONCAT(nickname) as nicknames
        FROM users
        GROUP BY user_id
        HAVING COUNT(*) > 1
        ORDER BY count DESC
    """)
    
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"⚠️ 發現 {len(duplicates)} 個重複的 user_id:\n")
        for dup in duplicates:
            print(f"  ID {dup['user_id']}: {dup['count']} 條記錄")
            print(f"    昵稱: {dup['nicknames']}")
    else:
        print("✅ 沒有重複的 user_id")
    
    # 4. 特別檢查已修復的 user_id
    print("\n" + "=" * 80)
    print("【檢查 4】已修復的凱文 ID")
    print("=" * 80 + "\n")
    
    cursor.execute("""
        SELECT user_id, nickname, level, xp, kkcoin, title, equipment
        FROM users 
        WHERE user_id = 776464975551660123
    """)
    
    kevin_fixed = cursor.fetchone()
    if kevin_fixed:
        print(f"✅ 找到已修復的凱文:")
        print(f"  user_id: {kevin_fixed['user_id']}")
        print(f"  nickname: {kevin_fixed['nickname']}")
        print(f"  level: {kevin_fixed['level']}")
        print(f"  xp: {kevin_fixed['xp']}")
        print(f"  kkcoin: {kevin_fixed['kkcoin']}")
        print(f"  title: {kevin_fixed['title']}")
        print(f"  equipment: {kevin_fixed['equipment']}")
    else:
        print("❌ 未找到 ID 776464975551660123 的用戶")
    
    conn.close()

except Exception as e:
    print(f"❌ 資料庫操作失敗: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("診斷完成")
print("=" * 80)
