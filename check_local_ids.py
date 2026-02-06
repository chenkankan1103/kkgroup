import sqlite3
import json

# 連接本地資料庫
conn = sqlite3.connect('user_data.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 60)
print("檢查本地資料庫中的用戶 ID")
print("=" * 60)

# 查詢所有用戶
cursor.execute("SELECT user_id, nickname, level, xp FROM users LIMIT 30")
rows = cursor.fetchall()

print(f"\n找到 {len(rows)} 個用戶\n")

user_id_list = []
for row in rows:
    user_id = row['user_id']
    nickname = row['nickname']
    user_id_list.append(user_id)
    print(f"ID: {user_id:20} | 暱稱: {nickname}")

conn.close()

# 現在檢查已修復的 ID 是否在列表中
print("\n" + "=" * 60)
print("檢查修復後的 ID 是否在本地資料庫中")
print("=" * 60)

fixed_ids = [344018672056139786, 401694438449217548, 1209509919699505184]
for fixed_id in fixed_ids:
    if fixed_id in user_id_list:
        print(f"✅ {fixed_id} 存在於本地資料庫")
    else:
        print(f"❌ {fixed_id} 不在本地資料庫")
