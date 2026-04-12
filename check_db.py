#!/usr/bin/env python3
"""全面檢查資料庫和系統狀態"""
import sqlite3
import json

try:
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    
    # 1. 檢查 users 表
    print("=" * 60)
    print("📋 檢查 users 表結構")
    print("=" * 60)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        print("✅ users 表存在")
        cursor.execute("PRAGMA table_info(users)")
        cols = cursor.fetchall()
        print(f"📌 表有 {len(cols)} 列：")
        for col in cols:
            print(f"  - {col[1]} ({col[2]})")
    else:
        print("❌ users 表不存在！") 
    
    # 2. 檢查數據統計
    print("\n" + "=" * 60)
    print("📊 數據統計")
    print("=" * 60)
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    print(f"✅ users 表有 {count} 行數據")
    
    # 3. 檢查關鍵欄位
    print("\n" + "=" * 60)
    print("🔍 檢查關鍵欄位的數據")
    print("=" * 60)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_user_id,
            SUM(CASE WHEN thread_id IS NULL OR thread_id = 0 THEN 1 ELSE 0 END) as null_thread_id,
            SUM(CASE WHEN locker_message_id IS NULL OR locker_message_id = 0 THEN 1 ELSE 0 END) as null_locker_msg
        FROM users
    """)
    result = cursor.fetchone()
    if result:
        total, null_uid, null_tid, null_msg = result
        print(f"  總行數: {total}")
        print(f"  user_id 為空: {null_uid or 0}")
        print(f"  thread_id 為 NULL 或 0: {null_tid or 0}")
        print(f"  locker_message_id 為 NULL 或 0: {null_msg or 0}")
    
    # 4. 檢查大麻系統字段
    print("\n" + "=" * 60)
    print("🌱 檢查大麻系統字段")
    print("=" * 60)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN cannabis_plants IS NULL OR cannabis_plants = '' THEN 1 ELSE 0 END) as null_plants,
            SUM(CASE WHEN cannabis_inventory IS NULL OR cannabis_inventory = '' THEN 1 ELSE 0 END) as null_inventory
        FROM users
    """)
    result = cursor.fetchone()
    if result:
        total, null_plants, null_inv = result
        print(f"  總行數: {total}")
        print(f"  cannabis_plants 為空: {null_plants or 0}")
        print(f"  cannabis_inventory 為空: {null_inv or 0}")
    
    # 5. 檢查樣本用戶數據
    print("\n" + "=" * 60)
    print("👤 檢查樣本用戶數據 (前 3 個用戶)")
    print("=" * 60)
    cursor.execute("""
        SELECT user_id, thread_id, locker_message_id, 
               LENGTH(cannabis_plants) as plant_data_size, 
               LENGTH(cannabis_inventory) as inventory_data_size
        FROM users 
        LIMIT 3
    """)
    for row in cursor.fetchall():
        user_id, thread_id, locker_msg, plant_size, inv_size = row
        print(f"\n  用戶 {user_id}:")
        print(f"    - thread_id: {thread_id}")
        print(f"    - locker_message_id: {locker_msg}")
        print(f"    - cannabis_plants 數據大小: {plant_size} bytes")
        print(f"    - cannabis_inventory 數據大小: {inv_size} bytes")
    
    conn.close()
    print("\n✅ 數據庫檢查完成")
    
except Exception as e:
    import traceback
    print(f"❌ 錯誤：{e}")
    traceback.print_exc()
