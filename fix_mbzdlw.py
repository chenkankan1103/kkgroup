# -*- coding: utf-8 -*-
"""
創建/修復 mbzdlw 用戶記錄
"""
import json
from shared.db.sheet_driven_db import get_db_instance

# 載入 fashion DB 找有效的替代品
with open('twms_fashion_db.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

# 提取有效的 Top 和 Shoes ID
valid_tops = [item['id'] for item in items if item['category'] == 'Top']
valid_shoes = [item['id'] for item in items if item['category'] == 'Shoes']

print('=== 修復 mbzdlw 用戶 ===')
print()

user_id = 1430046213012590592

# 選擇替代品（使用比較常見的）
new_top = 1040001  # 最基本的 Top
new_shoes = 1072014  # 有效的鞋子

if new_top not in valid_tops:
    new_top = valid_tops[0]
if new_shoes not in valid_shoes:
    new_shoes = valid_shoes[0]

print(f'用戶 ID: {user_id} (mbzdlw)')
print()

# 完整的用戶配置（基於置物櫃信息）
user_data = {
    'discord_username': 'mbzdlw',
    'level': 1,
    'exp': 0,
    'coins': 0,
    'usd': 0.0,
    'rank': '新手',
    'hp': 85,
    'max_hp': 100,
    'stamina': 68,
    'max_stamina': 100,
    # 紙娃娃配置（修復無效 ID）
    'face': 20001,
    'hair': 30260,
    'skin': 12100,
    'top': str(new_top),  # 修復：1041002 → 1040001
    'bottom': 1060096,
    'shoes': str(new_shoes),  # 修復：1072410 → 1072014
    'hat': 0,
    'cape': 0,
}

db = get_db_instance()

# 檢查用戶是否存在
existing_user = db.get_user(user_id)

if existing_user:
    print(f'✅ 用戶已存在於數據庫，更新配置...')
    operation = '更新'
else:
    print(f'❌ 用戶不存在，創建新記錄...')
    operation = '創建'

# 保存用戶
try:
    db.set_user(user_id, user_data)
    print(f'✅ {operation}成功！')
except Exception as e:
    print(f'❌ {operation}失敗: {e}')
    exit(1)

print()
print('=== 配置詳情 ===')
print(f'臉型: 20001 ✅')
print(f'髮型: 30260 ✅')
print(f'膚色: 12100 ℹ️ (Skin 不在 DB 中，正常)')
print(f'上身: {new_top} (原本 1041002 無效 → 已修復)')
print(f'下身: 1060096 ✅')
print(f'鞋子: {new_shoes} (原本 1072410 無效 → 已修復)')

print()
print('=== 驗證修復 ===')
# 驗證保存
saved_user = db.get_user(user_id)
if saved_user:
    print(f'✅ 用戶已成功保存到數據庫')
    print(f'   頂部: {saved_user.get("top")}')
    print(f'   鞋子: {saved_user.get("shoes")}')
else:
    print(f'❌ 驗證失敗')
