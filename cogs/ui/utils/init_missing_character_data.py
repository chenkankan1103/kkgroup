# -*- coding: utf-8 -*-
"""
為缺失楓之谷角色數據的用戶填充預設值

此工具用於：
1. 檢測哪些用戶缺失角色配置
2. 為他們填充預設的楓之谷角色數據
3. 確保所有用戶都有有效的 API 圖片
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from db_adapter import get_all_users, set_user_field
import random


# 預設楓之谷角色配置（分性別，與 image_utils.py 中的預設值保持一致）
# 注意：數據庫中所有值都是字符串存儲！
# 男性預設
MALE_DEFAULT_CHARACTER_DATA = {
    'face': '20005',
    'hair': '30120',
    'skin': '12000',
    'top': '1040014',
    'bottom': '1060096',
    'shoes': '1072005',
    'is_stunned': 0,
    'gender': 'male'
}

# 女性預設
FEMALE_DEFAULT_CHARACTER_DATA = {
    'face': '21731',
    'hair': '34410',
    'skin': '12000',
    'top': '1041004',
    'bottom': '1061008',
    'shoes': '1072005',
    'is_stunned': 0,
    'gender': 'female'
}

# 向後相容性
DEFAULT_CHARACTER_DATA = MALE_DEFAULT_CHARACTER_DATA

# 楓之谷部位 ID 預設值列表（用於多樣性）
CHARACTER_VARIATIONS = {
    'face': [20000, 20001, 20005, 20100, 20400, 20402, 20405],
    'hair': [30000, 30030, 30120, 30220, 30260, 30300, 30320],
    'skin': [10000, 10001, 10002, 12000, 12100],
    'top': [1040010, 1040014, 1041002, 1040060, 1042003],
    'bottom': [1060002, 1060096, 1060127, 1061112],
    'shoes': [1072005, 1072014, 1072267, 1072410],
}


def get_random_character_data(preserve_gender: str = None) -> dict:
    """
    生成隨機但合理的楓之谷角色配置
    
    Args:
        preserve_gender: 如果提供，則保持此性別而不是隨機選擇
        
    Returns:
        包含角色配置的字典（所有值都是字符串格式，與數據庫一致）
    """
    return {
        'face': str(random.choice(CHARACTER_VARIATIONS['face'])),
        'hair': str(random.choice(CHARACTER_VARIATIONS['hair'])),
        'skin': str(random.choice(CHARACTER_VARIATIONS['skin'])),
        'top': str(random.choice(CHARACTER_VARIATIONS['top'])),
        'bottom': str(random.choice(CHARACTER_VARIATIONS['bottom'])),
        'shoes': str(random.choice(CHARACTER_VARIATIONS['shoes'])),
        'is_stunned': 0,
        'gender': preserve_gender if preserve_gender else random.choice(['male', 'female'])
    }


def find_users_with_missing_character_data() -> list:
    """
    查找所有缺失楓之谷角色數據的用戶
    
    Returns:
        缺失角色數據的用戶 ID 列表
    """
    users = get_all_users()
    missing_users = []
    
    for user in users:
        user_id = user.get('user_id')
        
        # 檢查是否缺失任何必要的角色欄位
        required_fields = ['face', 'hair', 'skin', 'top', 'bottom', 'shoes']
        has_all_fields = all(field in user and user.get(field) is not None for field in required_fields)
        
        if not has_all_fields:
            missing_users.append(user_id)
    
    return missing_users


def initialize_missing_users_with_defaults() -> dict:
    """
    為所有缺失角色數據的用戶設置預設配置
    
    Returns:
        修復結果統計 {
            'total_missing': 缺失用戶數,
            'fixed_with_defaults': 用預設值修復的用戶數,
            'fixed_with_random': 用隨機變體修復的用戶數,
            'failed': 修復失敗的用戶數,
            'error': 錯誤信息（如有）
        }
    """
    missing_users = find_users_with_missing_character_data()
    
    result = {
        'total_missing': len(missing_users),
        'fixed_with_defaults': 0,
        'fixed_with_random': 0,
        'failed': 0,
        'error': None
    }
    
    if not missing_users:
        result['error'] = '✅ 所有用戶都已有楓之谷角色數據！'
        return result
    
    print(f"🔧 發現 {len(missing_users)} 個缺失角色數據的用戶")
    print(f"正在為他們填充預設數據...\n")
    
    for i, user_id in enumerate(missing_users, 1):
        try:
            # 80% 用預設值，20% 用隨機變體
            use_random = i % 5 == 0  # 每 5 個用 1 個隨機
            
            if use_random:
                char_data = get_random_character_data()
                result['fixed_with_random'] += 1
                variant_str = "✨ 隨機變體"
            else:
                char_data = DEFAULT_CHARACTER_DATA.copy()
                result['fixed_with_defaults'] += 1
                variant_str = "預設值"
            
            # 為用戶設置所有角色欄位
            for field, value in char_data.items():
                set_user_field(user_id, field, value)
            
            print(f"  {i}. 用戶 {user_id}: {variant_str}")
        
        except Exception as e:
            result['failed'] += 1
            print(f"  ❌ 用戶 {user_id}: 修復失敗 - {e}")
    
    print(f"\n✅ 修復完成！")
    print(f"  - 總計: {result['total_missing']} 用戶")
    print(f"  - 已修復 (預設): {result['fixed_with_defaults']} 用戶")
    print(f"  - 已修復 (隨機): {result['fixed_with_random']} 用戶")
    print(f"  - 失敗: {result['failed']} 用戶")
    
    return result


def convert_default_to_random_characters() -> dict:
    """
    將所有使用預設頭髮的用戶改為隨機配置
    
    邏輯：
    1. 預設值用戶（頭髮為預設值）→ 改為隨機
    2. 非預設值用戶（頭髮不是預設值）→ 不動
    3. 空白用戶（任何欄位為 None）→ 隨機填充
    4. 性別 → 始終保持不變
    
    Returns:
        修復結果統計 {
            'total_users': 總用戶數,
            'using_defaults': 使用預設值的用戶數,
            'converted_to_random': 已轉換為隨機的用戶數,
            'filled_blanks': 填充空白欄位的用戶數,
            'unchanged': 保持不變的用戶數,
            'failed': 修復失敗的用戶數,
            'details': 詳細訊息列表
        }
    """
    users = get_all_users()
    
    result = {
        'total_users': len(users),
        'using_defaults': 0,
        'converted_to_random': 0,
        'filled_blanks': 0,
        'unchanged': 0,
        'failed': 0,
        'details': []
    }
    
    required_fields = ['face', 'hair', 'skin', 'top', 'bottom', 'shoes']
    
    for i, user in enumerate(users, 1):
        try:
            user_id = user.get('user_id')
            current_gender = user.get('gender', 'male')
            current_hair = user.get('hair')
            
            # 檢查是否有空白欄位（包括 None 和空字符串）
            user_values = {field: user.get(field) for field in required_fields}
            has_blanks = any(v in (None, '') for v in user_values.values())
            
            # 檢查頭髮是否為預設值（只檢查 hair 欄位）
            if current_gender == 'female':
                is_default_hair = current_hair == FEMALE_DEFAULT_CHARACTER_DATA['hair']
            else:
                is_default_hair = current_hair == MALE_DEFAULT_CHARACTER_DATA['hair']
            
            if has_blanks:
                # 填充空白欄位
                random_data = get_random_character_data(preserve_gender=current_gender)
                for field in required_fields:
                    if user.get(field) in (None, ''):
                        set_user_field(user_id, field, random_data[field])
                result['filled_blanks'] += 1
                result['details'].append(f"  {i}. 用戶 {user_id}: 填充空白欄位")
            
            elif is_default_hair:
                # 預設頭髮用戶 → 轉換所有欄位為隨機
                random_data = get_random_character_data(preserve_gender=current_gender)
                for field in required_fields:
                    set_user_field(user_id, field, random_data[field])
                result['using_defaults'] += 1
                result['converted_to_random'] += 1
                result['details'].append(f"  {i}. 用戶 {user_id}: 預設頭髮 → 隨機值")
            
            else:
                # 非預設頭髮用戶 → 保持不變
                result['unchanged'] += 1
        
        except Exception as e:
            result['failed'] += 1
            result['details'].append(f"  {i}. 用戶 {user_id}: 修復失敗 - {e}")
    
    return result


def batch_fill_missing_fields(field_name: str, default_value) -> dict:
    """
    為所有用戶填充特定缺失欄位
    
    Args:
        field_name: 欄位名（如 'face'）
        default_value: 預設值
        
    Returns:
        修復結果統計
    """
    users = get_all_users()
    updated = 0
    failed = 0
    
    for user in users:
        user_id = user.get('user_id')
        
        # 如果欄位缺失或為 None，則填充
        if field_name not in user or user.get(field_name) is None:
            try:
                set_user_field(user_id, field_name, default_value)
                updated += 1
            except Exception as e:
                print(f"用戶 {user_id} 的 {field_name} 更新失敗: {e}")
                failed += 1
    
    return {
        'field': field_name,
        'updated': updated,
        'failed': failed
    }


if __name__ == '__main__':
    """
    使用方式：
    python -m cogs.ui.utils.init_missing_character_data
    """
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--check':
            # 只檢查，不修復
            missing = find_users_with_missing_character_data()
            print(f"缺失楓之谷角色數據的用戶: {len(missing)}")
            if missing:
                print("用戶 ID:", missing[:20], "..." if len(missing) > 20 else "")
        
        elif sys.argv[1] == '--fix':
            # 執行修復
            initialize_missing_users_with_defaults()
        
        elif sys.argv[1] == '--randomize':
            # 將預設值轉為隨機，空白的也隨機填充，非預設值保持不變，性別不動
            print("開始轉換預設角色為隨機配置...")
            print("   (預設值→隨機, 空白→隨機, 非預設值→不動, 性別→保持)\n")
            
            result = convert_default_to_random_characters()
            
            # 列印詳細訊息
            for detail in result['details']:
                print(detail)
            
            print(f"\n轉換完成！")
            print(f"  - 總用戶: {result['total_users']}")
            print(f"  - 預設值用戶: {result['using_defaults']}")
            print(f"  - 已轉換為隨機: {result['converted_to_random']}")
            print(f"  - 填充空白欄位: {result['filled_blanks']}")
            print(f"  - 保持不變: {result['unchanged']}")
            print(f"  - 失敗: {result['failed']}")
        
        elif sys.argv[1] == '--fix-field' and len(sys.argv) > 3:
            # 修復特定欄位: python ... --fix-field face 20005
            field = sys.argv[2]
            value = int(sys.argv[3]) if sys.argv[3].isdigit() else sys.argv[3]
            result = batch_fill_missing_fields(field, value)
            print(f"已為 {result['updated']} 個用戶填充 {field}={value}")
            if result['failed']:
                print(f"{result['failed']} 個用戶修復失敗")
    else:
        # 默認執行修復
        initialize_missing_users_with_defaults()
