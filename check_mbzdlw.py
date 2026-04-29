# -*- coding: utf-8 -*-
"""
檢查 mbzdlw 用戶的紙娃娃配置
"""
import json
from shared.db.sheet_driven_db import get_db_instance

# 載入 fashion DB
with open('twms_fashion_db.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

# 建立 ID 到物品信息的映射
items_by_id = {item['id']: item for item in items}

# mbzdlw 的配置
user_id = 1430046213012590592
config = {
    'top': 1041002,
    'bottom': 1060096,
    'shoes': 1072410,
    'hair': 30260,
    'face': 20001,
    'skin': 12100
}

print(f'=== 檢查用戶 mbzdlw (ID: {user_id}) ===')
print()

category_map = {
    'top': 'Top',
    'bottom': 'Bottom',
    'shoes': 'Shoes',
    'hair': 'Hair',
    'face': 'Face',
    'skin': 'Skin'
}

invalid_items = {}

for part, item_id in config.items():
    cat_name = category_map[part]
    
    if item_id in items_by_id:
        item_info = items_by_id[item_id]
        print(f'✅ {part.upper()}: {item_id} - 有效')
        print(f'   分類: {item_info.get("category")}')
        print(f'   名稱: {item_info.get("name", "N/A")}')
    else:
        # Skin 是特殊情況
        if part == 'skin':
            print(f'ℹ️  {part.upper()}: {item_id} - Skin 不在 fashion DB 中（正常）')
        else:
            print(f'❌ {part.upper()}: {item_id} - 【無效】不在 fashion DB 中')
            invalid_items[part] = item_id
    print()

if invalid_items:
    print('=== 需要修復的物品 ===')
    print()
    for part, item_id in invalid_items.items():
        print(f'{part}: {item_id}')
else:
    print('✅ 所有物品都有效（除了 Skin 這是正常的）')

# 檢查用戶是否存在於數據庫
print()
print('=== 檢查用戶數據庫狀態 ===')
db = get_db_instance()
user_data = db.get_user(user_id)

if user_data:
    print(f'✅ 用戶已存在於數據庫')
else:
    print(f'❌ 用戶不存在於數據庫 - 需要新增或導入')
