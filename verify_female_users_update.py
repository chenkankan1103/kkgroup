# -*- coding: utf-8 -*-
"""
驗證本地資料庫女性用戶的更新 - 改進版
檢查生成的 ID 是否在 fashion DB 中存在且有效
"""
from shared.db.sheet_driven_db import SheetDrivenDB
from collections import defaultdict
import json

db = SheetDrivenDB('user_data.db')
all_users_list = db.get_all_users()
all_users = {str(user.get('user_id', '')): user for user in all_users_list}

female_users = [(uid, data) for uid, data in all_users.items() if data.get('gender') == 'female']

print(f"✅ 本地資料庫驗證：{len(female_users)} 個女性用戶\n")

# 載入 fashion DB
with open('twms_fashion_db.json', 'r', encoding='utf-8') as f:
    fashion_items = json.load(f)

# 建立 category 和 ID 的對應
face_ids = {str(item['id']) for item in fashion_items if item['category'] == 'Face'}
hair_ids = {str(item['id']) for item in fashion_items if item['category'] == 'Hair'}
top_ids = {str(item['id']) for item in fashion_items if item['category'] == 'Top'}
bottom_ids = {str(item['id']) for item in fashion_items if item['category'] == 'Bottom'}
shoes_ids = {str(item['id']) for item in fashion_items if item['category'] == 'Shoes'}

print("=== 檢查所有女性用戶的部件是否有效 ===\n")
all_valid = True

for uid, data in female_users:
    face_id = str(data.get('face', ''))
    hair_id = str(data.get('hair', ''))
    top_id = str(data.get('top', ''))
    bottom_id = str(data.get('bottom', ''))
    shoes_id = str(data.get('shoes', ''))
    
    face_valid = face_id in face_ids
    hair_valid = hair_id in hair_ids
    top_valid = top_id in top_ids
    bottom_valid = bottom_id in bottom_ids
    shoes_valid = shoes_id in shoes_ids
    
    all_parts_valid = all([face_valid, hair_valid, top_valid, bottom_valid, shoes_valid])
    
    status = "✅" if all_parts_valid else "❌"
    print(f"{status} 用戶 {uid[-8:]}: face={face_valid} hair={hair_valid} top={top_valid} bottom={bottom_valid} shoes={shoes_valid}")
    
    if not all_parts_valid:
        all_valid = False
        if not face_valid:
            print(f"    ⚠️ face ID {face_id} 不在 DB 中")
        if not hair_valid:
            print(f"    ⚠️ hair ID {hair_id} 不在 DB 中")
        if not top_valid:
            print(f"    ⚠️ top ID {top_id} 不在 DB 中")
        if not bottom_valid:
            print(f"    ⚠️ bottom ID {bottom_id} 不在 DB 中")
        if not shoes_valid:
            print(f"    ⚠️ shoes ID {shoes_id} 不在 DB 中")

print(f"\n{'✅ 所有女性用戶的部件都有效！' if all_valid else '❌ 發現無效的部件 ID'}")
print(f"\n📊 統計:")
print(f"  總女性用戶: {len(female_users)} 人")
print(f"  所有部件都有效: {'✅ 是' if all_valid else '❌ 否'}")
