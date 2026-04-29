#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

print("===== 紙娃娃多樣性驗證 =====\n")

conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

for part in ['face', 'hair', 'top', 'bottom', 'shoes']:
    cursor.execute(f"SELECT COUNT(DISTINCT {part}) FROM users WHERE {part} IS NOT NULL AND {part} != ''")
    unique = cursor.fetchone()[0]
    
    cursor.execute(f"SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    print(f"{part.upper():10} 多樣性: {unique:4} 種不同的 ID (共 {total} 個用戶)")

# 檢查預設值使用情況
MALE_FACE = 20005
FEMALE_FACE = 21731
cursor.execute(f"SELECT COUNT(*) FROM users WHERE face = {MALE_FACE} OR face = {FEMALE_FACE}")
default_faces = cursor.fetchone()[0]

print(f"\n預設 Face 使用: {default_faces} 個 ({default_faces/252*100:.1f}%)")

conn.close()

print("\n✅ 驗證完成")
