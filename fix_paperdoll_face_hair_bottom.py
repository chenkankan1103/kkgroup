#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import random
import json

print("=" * 100)
print("🔧 完整修復紙娃娃造型 - 重新生成 Face/Hair/Bottom 為多樣性值")
print("=" * 100)

# 載入 fashion DB
with open('twms_fashion_db.json', 'r', encoding='utf-8') as f:
    fashion_items = json.load(f)

# 分類有效 ID
valid_by_category = {}
for item in fashion_items:
    cat = item['category']
    if cat not in valid_by_category:
        valid_by_category[cat] = []
    valid_by_category[cat].append(int(item['id']))

# 準備修復
face_ids = list(set(valid_by_category.get('Face', [])))
hair_ids = list(set(valid_by_category.get('Hair', [])))
bottom_ids = list(set(valid_by_category.get('Bottom', [])))

print(f"\n準備修復:")
print(f"  有效 Face: {len(face_ids)} 個")
print(f"  有效 Hair: {len(hair_ids)} 個")
print(f"  有效 Bottom: {len(bottom_ids)} 個\n")

# 連接資料庫
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# 統計需要修復的用戶
MALE_DEFAULT_FACE = 20005
MALE_DEFAULT_HAIR = 30120
MALE_DEFAULT_BOTTOM = 1060096
FEMALE_DEFAULT_FACE = 21731
FEMALE_DEFAULT_HAIR = 34410
FEMALE_DEFAULT_BOTTOM = 1061008

cursor.execute(f"""
    SELECT COUNT(*) FROM users 
    WHERE face = {MALE_DEFAULT_FACE} 
    OR face = {FEMALE_DEFAULT_FACE}
    OR face IS NULL OR face = ''
""")
need_face_fix = cursor.fetchone()[0]

cursor.execute(f"""
    SELECT COUNT(*) FROM users 
    WHERE hair = {MALE_DEFAULT_HAIR}
    OR hair = {FEMALE_DEFAULT_HAIR}
    OR hair IS NULL OR hair = ''
""")
need_hair_fix = cursor.fetchone()[0]

cursor.execute(f"""
    SELECT COUNT(*) FROM users 
    WHERE bottom = {MALE_DEFAULT_BOTTOM}
    OR bottom = {FEMALE_DEFAULT_BOTTOM}
    OR bottom IS NULL OR bottom = ''
""")
need_bottom_fix = cursor.fetchone()[0]

print(f"需要修復的用戶:")
print(f"  Face 需要修復: {need_face_fix} 個")
print(f"  Hair 需要修復: {need_hair_fix} 個")
print(f"  Bottom 需要修復: {need_bottom_fix} 個\n")

# 執行修復
fixed_count = 0

# 修復 Face
cursor.execute(f"""
    SELECT user_id, face FROM users 
    WHERE face = {MALE_DEFAULT_FACE} 
    OR face = {FEMALE_DEFAULT_FACE}
    OR face IS NULL OR face = ''
""")

for user_id, current_face in cursor.fetchall():
    new_face = str(random.choice(face_ids))
    cursor.execute("UPDATE users SET face = ? WHERE user_id = ?", (new_face, user_id))
    fixed_count += 1
    if fixed_count % 50 == 0:
        print(f"  進度: 修復 {fixed_count} 個用戶的 Face...")

print(f"✅ Face 修復完成: {fixed_count} 個用戶")

# 修復 Hair
fixed_count = 0
cursor.execute(f"""
    SELECT user_id, hair FROM users 
    WHERE hair = {MALE_DEFAULT_HAIR}
    OR hair = {FEMALE_DEFAULT_HAIR}
    OR hair IS NULL OR hair = ''
""")

for user_id, current_hair in cursor.fetchall():
    new_hair = str(random.choice(hair_ids))
    cursor.execute("UPDATE users SET hair = ? WHERE user_id = ?", (new_hair, user_id))
    fixed_count += 1
    if fixed_count % 50 == 0:
        print(f"  進度: 修復 {fixed_count} 個用戶的 Hair...")

print(f"✅ Hair 修復完成: {fixed_count} 個用戶")

# 修復 Bottom
fixed_count = 0
cursor.execute(f"""
    SELECT user_id, bottom FROM users 
    WHERE bottom = {MALE_DEFAULT_BOTTOM}
    OR bottom = {FEMALE_DEFAULT_BOTTOM}
    OR bottom IS NULL OR bottom = ''
""")

for user_id, current_bottom in cursor.fetchall():
    new_bottom = str(random.choice(bottom_ids))
    cursor.execute("UPDATE users SET bottom = ? WHERE user_id = ?", (new_bottom, user_id))
    fixed_count += 1
    if fixed_count % 50 == 0:
        print(f"  進度: 修復 {fixed_count} 個用戶的 Bottom...")

print(f"✅ Bottom 修復完成: {fixed_count} 個用戶")

conn.commit()
conn.close()

# 驗證
print(f"\n【修復後驗證】\n")

conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

for part in ['face', 'hair', 'bottom']:
    cursor.execute(f"SELECT COUNT(DISTINCT {part}) FROM users WHERE {part} IS NOT NULL AND {part} != ''")
    unique_count = cursor.fetchone()[0]
    print(f"{part.upper()}: {unique_count} 種不同的 ID")

conn.close()

print(f"\n" + "=" * 100)
print(f"✅ 修復完成！所有紙娃娃部位現在都有多樣性")
print(f"=" * 100)
