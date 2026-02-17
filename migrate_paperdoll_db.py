"""
資料庫升級腳本：新增缺少的衣帽部件欄位
從 6 個基本欄位擴展到完整的 25 個部件種類
"""
import sqlite3
from datetime import datetime

# 新增的部件欄位（映射 JSON 類別）
NEW_FIELDS = {
    'belt': 'TEXT',           # Belt
    'cape': 'TEXT',           # Cape
    'earrings': 'TEXT',       # Earrings
    'eye_decoration': 'TEXT', # Eye Decoration
    'face_accessory': 'TEXT', # Face Accessory
    'glove': 'TEXT',          # Glove
    'hat': 'TEXT',            # Hat
    'katara': 'TEXT',         # Katara
    'mount': 'TEXT',          # Mount
    'one_handed_sword': 'TEXT',  # One-Handed Sword
    'overall': 'TEXT',        # Overall
    'pendant': 'TEXT',        # Pendant
    'pet_equipment': 'TEXT',  # Pet Equipment
    'pet_use': 'TEXT',        # Pet Use
    'pole_arm': 'TEXT',       # Pole Arm
    'ring': 'TEXT',           # Ring
    'shield': 'TEXT',         # Shield
    'shoulder_accessory': 'TEXT',  # Shoulder Accessory
    'skill_effect': 'TEXT',   # Skill Effect
}

def migrate_database():
    """執行資料庫遷移"""
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    
    try:
        # 檢查已存在的欄位
        cursor.execute("PRAGMA table_info(users)")
        existing_fields = {col[1] for col in cursor.fetchall()}
        
        print(f"現有欄位數: {len(existing_fields)}")
        print(f"將新增 {len(NEW_FIELDS)} 個部件欄位...\n")
        
        # 新增缺少的欄位
        added_count = 0
        for field_name, field_type in NEW_FIELDS.items():
            if field_name not in existing_fields:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {field_name} {field_type}")
                    added_count += 1
                    print(f"✓ 新增欄位: {field_name} ({field_type})")
                except sqlite3.OperationalError as e:
                    print(f"✗ 無法新增 {field_name}: {e}")
            else:
                print(f"- 欄位已存在: {field_name}")
        
        conn.commit()
        print(f"\n升級完成! 共新增 {added_count} 個欄位")
        
        # 驗證
        cursor.execute("PRAGMA table_info(users)")
        final_fields = cursor.fetchall()
        print(f"最終欄位數: {len(final_fields)}")
        
    except Exception as e:
        print(f"升級失敗: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("紙娃娃部件資料庫升級")
    print("=" * 60)
    print()
    migrate_database()
