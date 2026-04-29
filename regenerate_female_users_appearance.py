# -*- coding: utf-8 -*-
"""
為所有 gender='female' 的用戶重新生成女性造型
使用新的性別感知隨機生成邏輯
"""
import json
import shutil
from datetime import datetime
from collections import defaultdict

from shared.db.sheet_driven_db import SheetDrivenDB
from cogs.ui.utils.paperdoll_manager import get_random

print("=== 為女性用戶重新生成女性造型 ===\n")

# 1. 備份資料庫
db_path = 'user_data.db'
backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"user_data.db.backup_female_restyle_{backup_timestamp}"

print(f"📦 備份資料庫...")
shutil.copy(db_path, backup_path)
print(f"✓ 備份完成: {backup_path}\n")

# 2. 讀取所有用戶
db = SheetDrivenDB(db_path)
all_users_list = db.get_all_users()
all_users = {str(user.get('user_id', '')): user for user in all_users_list}

# 3. 找出所有女性用戶
female_users = [(uid, data) for uid, data in all_users.items() if data.get('gender') == 'female']
print(f"找到 {len(female_users)} 個女性用戶\n")

# 4. 為每個女性用戶重新生成女性造型
print("=== 重新生成女性造型 ===")
updated_count = 0
changes_log = []

for user_id, old_data in female_users:
    # 生成新的女性造型
    new_config = get_random(preserve_gender='female')
    
    # 準備更新數據（保留其他欄位）
    update_data = {
        'face': new_config['face'],
        'hair': new_config['hair'],
        'skin': new_config['skin'],
        'top': new_config['top'],
        'bottom': new_config['bottom'],
        'shoes': new_config['shoes'],
        'gender': 'female',
        'is_stunned': new_config['is_stunned'],
    }
    
    # 更新資料庫
    db.set_user(user_id, update_data)
    updated_count += 1
    
    # 記錄變更
    change_info = {
        'user_id': user_id,
        'old': {
            'face': old_data.get('face'),
            'hair': old_data.get('hair'),
            'top': old_data.get('top'),
        },
        'new': {
            'face': new_config['face'],
            'hair': new_config['hair'],
            'top': new_config['top'],
        }
    }
    changes_log.append(change_info)
    
    print(f"✓ 用戶 {user_id[-8:]}: face {old_data.get('face')} → {new_config['face']}, "
          f"hair {old_data.get('hair')} → {new_config['hair']}, "
          f"top {old_data.get('top')} → {new_config['top']}")

print(f"\n=== 更新完成 ===")
print(f"✓ 更新 {updated_count} 個用戶")

# 5. 驗證更新後的數據
print(f"\n=== 驗證更新 ===")
db_refreshed = SheetDrivenDB(db_path)
all_users_after = db_refreshed.get_all_users()
all_users_dict_after = {str(u.get('user_id', '')): u for u in all_users_after}

female_users_after = [(uid, data) for uid, data in all_users_dict_after.items() if data.get('gender') == 'female']
print(f"驗證：現在有 {len(female_users_after)} 個女性用戶\n")

# 6. 分析新生成的女性造型分布
print("=== 新的女性造型分布 ===")
face_dist = defaultdict(int)
hair_dist = defaultdict(int)
top_dist = defaultdict(int)

for uid, data in female_users_after:
    face_dist[str(data.get('face', ''))] += 1
    hair_dist[str(data.get('hair', ''))] += 1
    top_dist[str(data.get('top', ''))] += 1

print("女性臉型分布 (top 5):")
for face, count in sorted(face_dist.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  Face {face}: {count} 人")

print("\n女性髮型分布 (top 5):")
for hair, count in sorted(hair_dist.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  Hair {hair}: {count} 人")

print("\n女性上衣分布 (top 5):")
for top, count in sorted(top_dist.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  Top {top}: {count} 人")

print(f"\n=== 完成 ===")
print(f"✅ 已為 {updated_count} 個女性用戶重新生成女性造型")
print(f"📂 備份位置: {backup_path}")
print(f"\n💡 提示：下次生成新隨機用戶時，如果是女性，會自動使用女性造型")
