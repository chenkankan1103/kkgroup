# -*- coding: utf-8 -*-
import json

with open('twms_fashion_db.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

# 提取所有 Face 物品並檢查名稱中是否有性別標識
faces = [item for item in items if item['category'] == 'Face']

print(f"總共 {len(faces)} 個臉型")
print("\n臉型樣本（檢查名稱）：")
for i, face in enumerate(faces[:20]):
    print(f"  {face['id']}: {face.get('name', 'N/A')}")

# 檢查是否有 "女" 或 "女性" 關鍵字
female_faces = [f for f in faces if '女' in f.get('name', '').lower() or 'female' in f.get('name', '').lower()]
male_faces = [f for f in faces if '男' in f.get('name', '').lower() or 'male' in f.get('name', '').lower()]

print(f"\n✨ 可能標記為女性的臉型: {len(female_faces)} 個")
if female_faces:
    for f in female_faces[:10]:
        print(f"  {f['id']}: {f.get('name', 'N/A')}")

print(f"\n♂️ 可能標記為男性的臉型: {len(male_faces)} 個")
if male_faces:
    for m in male_faces[:10]:
        print(f"  {m['id']}: {m.get('name', 'N/A')}")

# 檢查其他部件是否也有性別標識
print("\n\n=== 檢查其他部件 ===")
for category in ['Hair', 'Top', 'Bottom', 'Shoes']:
    items_in_cat = [item for item in items if item['category'] == category]
    female_count = sum(1 for item in items_in_cat if '女' in item.get('name', '').lower())
    male_count = sum(1 for item in items_in_cat if '男' in item.get('name', '').lower())
    
    print(f"\n{category}:")
    print(f"  總數: {len(items_in_cat)}")
    print(f"  女性標記: {female_count}")
    print(f"  男性標記: {male_count}")
