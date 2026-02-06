#!/usr/bin/env python3
"""
檢查凱文用戶的重複和同步問題
"""
import sqlite3
import json

# 連接本地資料庫
conn = sqlite3.connect('user_data.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 80)
print("檢查凱文用戶 (ID: 776464975551660123)")
print("=" * 80)

# 查詢所有凱文
cursor.execute("SELECT * FROM users WHERE nickname LIKE '%凱文%' OR user_id = 776464975551660123")
rows = cursor.fetchall()

print(f"\n找到 {len(rows)} 個凱文相關記錄\n")

for i, row in enumerate(rows, 1):
    print(f"【記錄 {i}】")
    print(f"  user_id: {row['user_id']}")
    print(f"  nickname: {row['nickname']}")
    print(f"  level: {row.get('level', 'N/A')}")
    print(f"  xp: {row.get('xp', 'N/A')}")
    print(f"  kkcoin: {row.get('kkcoin', 'N/A')}")
    print(f"  title: {row.get('title', 'N/A')}")
    print(f"  hp: {row.get('hp', 'N/A')}")
    print(f"  stamina: {row.get('stamina', 'N/A')}")
    print(f"  equipment: {row.get('equipment', 'N/A')}")
    print(f"  _created_at: {row.get('_created_at', 'N/A')}")
    print(f"  _updated_at: {row.get('_updated_at', 'N/A')}")
    print()

# 特別檢查是否有多個相同的 user_id
cursor.execute("""
    SELECT user_id, COUNT(*) as count 
    FROM users 
    WHERE user_id = 776464975551660123 
    GROUP BY user_id
""")
duplicate = cursor.fetchone()

if duplicate and duplicate['count'] > 1:
    print(f"⚠️ 警告: 發現 {duplicate['count']} 個相同的 user_id!")
else:
    print("✅ 沒有重複的 user_id 記錄")

# 檢查是否有虛擬人物（沒有頭像的用戶）
print("\n" + "=" * 80)
print("檢查虛擬人物（沒有頭像的用戶）")
print("=" * 80 + "\n")

cursor.execute("""
    SELECT user_id, nickname FROM users 
    WHERE (nickname LIKE '虛擬人物%' OR nickname IS NULL OR nickname = '')
    ORDER BY user_id
""")

virtual_users = cursor.fetchall()

if virtual_users:
    print(f"找到 {len(virtual_users)} 個虛擬人物:\n")
    for user in virtual_users:
        print(f"  ID: {user['user_id']} | 名稱: {user['nickname']}")
else:
    print("✅ 沒有檢測到虛擬人物")

conn.close()

print("\n" + "=" * 80)
print("診斷完成")
print("=" * 80)
