#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import json

print("=" * 100)
print("🔍 紙娃娃造型邏輯完整檢查")
print("=" * 100)

db = sqlite3.connect('user_data.db')
cursor = db.cursor()

# 1. 檢查預設值
print("\n【1️⃣ 預設值分析】\n")

import sys
sys.path.insert(0, '.')
from cogs.ui.utils import paperdoll_manager

print("MALE_DEFAULT:")
for k, v in paperdoll_manager.MALE_DEFAULT.items():
    if k not in ['is_stunned', 'gender']:
        print(f"  {k}: {v}")

print("\nFEMALE_DEFAULT:")
for k, v in paperdoll_manager.FEMALE_DEFAULT.items():
    if k not in ['is_stunned', 'gender']:
        print(f"  {k}: {v}")

# 2. 檢查資料庫中的實際分布
print("\n【2️⃣ 資料庫中實際分布】\n")

for part in ['face', 'hair', 'top', 'bottom', 'shoes']:
    cursor.execute(f"SELECT {part}, COUNT(*) as count FROM users WHERE {part} IS NOT NULL GROUP BY {part} ORDER BY count DESC LIMIT 5")
    results = cursor.fetchall()
    
    print(f"{part.upper()}:")
    total = sum(r[1] for r in results)
    for id_val, count in results:
        pct = count / 252 * 100
        match_default_m = id_val == paperdoll_manager.MALE_DEFAULT.get(part)
        match_default_f = id_val == paperdoll_manager.FEMALE_DEFAULT.get(part)
        marker = " (男預設)" if match_default_m else " (女預設)" if match_default_f else ""
        print(f"  ID {id_val}: {count} 個用戶 ({pct:.1f}%){marker}")
    
    # 計算多樣性
    cursor.execute(f"SELECT COUNT(DISTINCT {part}) FROM users WHERE {part} IS NOT NULL")
    unique_count = cursor.fetchone()[0]
    print(f"  → 不同值種類: {unique_count} 種")
    print()

# 3. 檢查是否所有用戶都是預設配置
print("【3️⃣ 預設配置檢查】\n")

male_default_exact = 0
female_default_exact = 0
custom = 0

cursor.execute("""
    SELECT user_id, face, hair, top, bottom, shoes FROM users 
    WHERE face IS NOT NULL AND hair IS NOT NULL AND top IS NOT NULL 
    AND bottom IS NOT NULL AND shoes IS NOT NULL
""")

for row in cursor.fetchall():
    user_id, face, hair, top, bottom, shoes = row
    
    # 轉換為字符串比較
    face_s = str(face)
    hair_s = str(hair)
    top_s = str(top)
    bottom_s = str(bottom)
    shoes_s = str(shoes)
    
    if (face_s == paperdoll_manager.MALE_DEFAULT['face'] and
        hair_s == paperdoll_manager.MALE_DEFAULT['hair'] and
        top_s == paperdoll_manager.MALE_DEFAULT['top'] and
        bottom_s == paperdoll_manager.MALE_DEFAULT['bottom'] and
        shoes_s == paperdoll_manager.MALE_DEFAULT['shoes']):
        male_default_exact += 1
    elif (face_s == paperdoll_manager.FEMALE_DEFAULT['face'] and
          hair_s == paperdoll_manager.FEMALE_DEFAULT['hair'] and
          top_s == paperdoll_manager.FEMALE_DEFAULT['top'] and
          bottom_s == paperdoll_manager.FEMALE_DEFAULT['bottom'] and
          shoes_s == paperdoll_manager.FEMALE_DEFAULT['shoes']):
        female_default_exact += 1
    else:
        custom += 1

total_users = 252
print(f"完全相同男性預設: {male_default_exact} 個用戶 ({male_default_exact/total_users*100:.1f}%)")
print(f"完全相同女性預設: {female_default_exact} 個用戶 ({female_default_exact/total_users*100:.1f}%)")
print(f"自訂造型: {custom} 個用戶 ({custom/total_users*100:.1f}%)")

total_defaults = male_default_exact + female_default_exact
if total_defaults > 200:
    print(f"\n⚠️ 警告: {total_defaults} 個用戶({total_defaults/total_users*100:.0f}%)使用預設造型！")
    print(f"   這表示紙娃娃多樣性嚴重不足")
else:
    print(f"\n✅ 紙娃娃多樣性正常 ({total_defaults/total_users*100:.1f}% 使用預設)")

# 4. 檢查 CHARACTER_VARIATIONS 是否正確載入
print("\n【4️⃣ CHARACTER_VARIATIONS 載入檢查】\n")

print(f"Fashion DB 載入狀態: {paperdoll_manager._FASHION_DB_CACHE is not None}")
print(f"CHARACTER_VARIATIONS 內容:")
for key in ['face', 'face_male', 'face_female', 'top', 'top_male', 'top_female']:
    val = paperdoll_manager.CHARACTER_VARIATIONS.get(key, [])
    if val:
        print(f"  {key}: {len(val)} 個 ID (前 5 個: {val[:5]})")
    else:
        print(f"  {key}: 空！")

# 5. 測試 get_random() 函數
print("\n【5️⃣ get_random() 函數測試】\n")

print("生成 5 個隨機男性造型:")
for i in range(5):
    random_male = paperdoll_manager.get_random(preserve_gender='male')
    print(f"  #{i+1}: face={random_male['face']}, hair={random_male['hair']}, top={random_male['top']}, shoes={random_male['shoes']}")

print("\n生成 5 個隨機女性造型:")
for i in range(5):
    random_female = paperdoll_manager.get_random(preserve_gender='female')
    print(f"  #{i+1}: face={random_female['face']}, hair={random_female['hair']}, top={random_female['top']}, shoes={random_female['shoes']}")

db.close()

print("\n" + "=" * 100)
print("✅ 檢查完成")
print("=" * 100)
