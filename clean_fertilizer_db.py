"""
清理資料庫中的肥料數據
"""
import json
import sqlite3
from sheet_driven_db import SheetDrivenDB

def clean_fertilizer_data():
    """從所有用戶的cannabis_inventory中移除肥料數據"""
    try:
        # 連接到資料庫
        db = SheetDrivenDB('user_data.db')

        # 獲取所有用戶
        all_users = db.get_all_users()

        cleaned_count = 0
        total_users = len(all_users)

        print(f"開始清理 {total_users} 個用戶的肥料數據...")
        print(f"all_users 類型: {type(all_users)}")

        # all_users 是用戶數據對象的列表
        for user_data in all_users:
            try:
                user_id = user_data.get('user_id')
                if not user_id:
                    continue

                # 檢查是否有cannabis_inventory字段
                inventory_json = user_data.get('cannabis_inventory', '{}')

                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = inventory_json if isinstance(inventory_json, dict) else {}

                # 如果有肥料數據，移除它
                if '肥料' in inventory:
                    print(f"用戶 {user_id}: 移除肥料數據 - {inventory['肥料']}")
                    del inventory['肥料']
                    cleaned_count += 1

                    # 更新資料庫
                    updated_inventory_json = json.dumps(inventory, ensure_ascii=False)
                    db.set_user_field(user_id, 'cannabis_inventory', updated_inventory_json)

            except Exception as e:
                print(f"處理用戶數據時出錯: {e}")
                continue

        print(f"✅ 清理完成！共處理 {total_users} 個用戶，清理了 {cleaned_count} 個用戶的肥料數據")

    except Exception as e:
        print(f"❌ 清理過程出錯: {e}")

if __name__ == "__main__":
    clean_fertilizer_data()