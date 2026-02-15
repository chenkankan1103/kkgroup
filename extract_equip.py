import requests
import json

# 設定目標
VERSION = "256"
REGION = "TWMS"
API_URL = f"https://maplestory.io/api/{REGION}/{VERSION}/item?category=Equip"

print(f"正在從 {REGION} v{VERSION} 獲取數據...")

try:
    response = requests.get(API_URL)
    data = response.json()

    print(f"數據類型: {type(data)}")
    if isinstance(data, list):
        print(f"項目數: {len(data)}")
        if data:
            print(f"第一個項目鍵: {data[0].keys()}")
    else:
        print(f"數據內容: {data}")

    # 整理後的結果
    cleaned_items = []

    for item in data:
        # 只保留點裝 (isCash) 或者你感興趣的分類
        # 這樣可以讓資料庫從幾萬筆縮減到幾千筆
        if item.get('isCash') == True and 'name' in item and 'id' in item and 'typeInfo' in item:
            # 構造角色圖片API網址（假設單一item，pose=stand1）
            item_path = f'{{"itemId":{item["id"]},"region":"{REGION}","version":"{VERSION}"}}'
            image_url = f"https://maplestory.io/api/character/{item_path}/stand1/0?showears=false&resize=2"
            cleaned_items.append({
                "id": item['id'],
                "name": item['name'],
                "category": item['typeInfo'].get('subCategory', 'Unknown'),
                "region": REGION,
                "version": VERSION,
                "image_url": image_url
            })

    # 儲存整理後的檔案
    with open('twms_fashion_db.json', 'w', encoding='utf-8') as f:
        json.dump(cleaned_items, f, ensure_ascii=False, indent=4)

    print(f"整理完成！共篩選出 {len(cleaned_items)} 件點裝。")

except Exception as e:
    print(f"讀取失敗: {e}")