"""
DB 適配層 - 統一的數據庫操作接口

這個模塊提供統一的函數接口，讓所有命令和工具都能使用新的 Sheet-Driven DB 引擎，
同時保持向後相容性。

使用示例：
    from db_adapter import get_user_field, set_user_field, add_user_field
    
    # 獲取玩家 kkcoin
    kkcoin = get_user_field(user_id, 'kkcoin', default=0)
    
    # 更新玩家 kkcoin
    set_user_field(user_id, 'kkcoin', 5000)
    
    # 增加玩家 kkcoin
    add_user_field(user_id, 'kkcoin', 100)
"""

from sheet_driven_db import SheetDrivenDB, get_db_instance
from typing import Any, Optional, Union, Dict, List

# 獲取全局 DB 實例
def get_db() -> SheetDrivenDB:
    """獲取全局數據庫實例"""
    return get_db_instance()


# ============================================================
# 用戶操作
# ============================================================

def get_user(user_id: Union[int, str]) -> Optional[Dict[str, Any]]:
    """
    獲取用戶完整資料
    
    Args:
        user_id: 用戶 ID
        
    Returns:
        用戶資料字典，或 None 如果不存在
    """
    return get_db().get_user(user_id)


def set_user(user_id: Union[int, str], data: Dict[str, Any]) -> bool:
    """
    設置用戶資料 (INSERT OR REPLACE)
    
    Args:
        user_id: 用戶 ID
        data: 更新的資料
        
    Returns:
        是否成功
    """
    return get_db().set_user(user_id, data)


def delete_user(user_id: Union[int, str]) -> bool:
    """刪除用戶"""
    return get_db().delete_user(user_id)


# ============================================================
# 欄位操作 (最常用的方法)
# ============================================================

def get_user_field(
    user_id: Union[int, str], 
    field: str, 
    default: Any = None
) -> Any:
    """
    獲取用戶特定欄位的值
    
    Args:
        user_id: 用戶 ID
        field: 欄位名
        default: 預設值 (用戶不存在或欄位無值時返回)
        
    Returns:
        欄位值或預設值
    """
    return get_db().get_user_field(user_id, field, default)


def set_user_field(
    user_id: Union[int, str], 
    field: str, 
    value: Any
) -> bool:
    """
    設置用戶特定欄位的值
    
    Args:
        user_id: 用戶 ID
        field: 欄位名
        value: 新值
        
    Returns:
        是否成功
    """
    return get_db().set_user_field(user_id, field, value)


def add_user_field(
    user_id: Union[int, str], 
    field: str, 
    amount: Union[int, float]
) -> bool:
    """
    增加用戶特定欄位的值 (僅限數字類型)
    
    常用示例：
        add_user_field(user_id, 'kkcoin', 100)   # 增加 100 個 kkcoin
        add_user_field(user_id, 'xp', 50)        # 增加 50 個 xp
        add_user_field(user_id, 'kkcoin', -50)   # 減少 50 個 kkcoin
    
    Args:
        user_id: 用戶 ID
        field: 欄位名 (必須是數字類型)
        amount: 增量 (可為負)
        
    Returns:
        是否成功
    """
    return get_db().update_user_field(user_id, field, amount)


# ============================================================
# 批量操作
# ============================================================

def get_all_users(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """獲取所有用戶資料"""
    return get_db().get_all_users(limit)


def batch_set_users(updates: Dict[Union[int, str], Dict[str, Any]]) -> int:
    """
    批量更新多個用戶
    
    Args:
        updates: {'user_id': {'field': value, ...}, ...}
        
    Returns:
        成功更新的用戶數
    """
    db = get_db()
    count = 0
    for user_id, data in updates.items():
        if db.set_user(user_id, data):
            count += 1
    return count


# ============================================================
# 統計操作
# ============================================================

def get_db_stats() -> Dict[str, Any]:
    """取得資料庫統計資訊"""
    return get_db().get_stats()


def count_users() -> int:
    """計算用戶總數"""
    stats = get_db_stats()
    return stats.get('total_users', 0)


def get_column_count() -> int:
    """計算欄位總數"""
    stats = get_db_stats()
    return stats.get('total_columns', 0)


# ============================================================
# 向後相容性函數 (為舊代碼提供支持)
# ============================================================

def get_user_kkcoin(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家 kkcoin"""
    return get_user_field(user_id, 'kkcoin', default=0)


def update_user_kkcoin(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 增加或減少玩家 kkcoin"""
    return add_user_field(user_id, 'kkcoin', amount)


def get_user_level(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家等級"""
    return get_user_field(user_id, 'level', default=1)


def get_user_xp(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家經驗值"""
    return get_user_field(user_id, 'xp', default=0)


def add_user_xp(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 增加玩家經驗值"""
    return add_user_field(user_id, 'xp', amount)


def get_user_hp(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家 HP"""
    return get_user_field(user_id, 'hp', default=100)


def get_user_stamina(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家耐力"""
    return get_user_field(user_id, 'stamina', default=100)


def get_user_title(user_id: Union[int, str]) -> str:
    """(向後相容) 獲取玩家頭銜"""
    return get_user_field(user_id, 'title', default='新手')


def update_user_hp(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 更新玩家 HP"""
    return add_user_field(user_id, 'hp', amount)


def update_user_stamina(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 更新玩家耐力"""
    return add_user_field(user_id, 'stamina', amount)


# ============================================================
# 設備系統 (shop_commands 專用)
# ============================================================

def get_user_equipment(user_id: Union[int, str]) -> Dict[str, int]:
    """
    (向後相容) 獲取玩家所有裝備
    
    Returns:
        {'face': ..., 'hair': ..., 'skin': ..., 'top': ..., 'bottom': ..., 'shoes': ...}
    """
    user = get_user(user_id)
    if not user:
        return {
            'face': 20000, 'hair': 30000, 'skin': 12000,
            'top': 1040010, 'bottom': 1060096, 'shoes': 1072288
        }
    
    return {
        'face': user.get('face', 20000),
        'hair': user.get('hair', 30000),
        'skin': user.get('skin', 12000),
        'top': user.get('top', 1040010),
        'bottom': user.get('bottom', 1060096),
        'shoes': user.get('shoes', 1072288),
    }


def update_user_equipment(user_id: Union[int, str], equipment_type: str, item_id: int) -> bool:
    """
    (向後相容) 更新玩家某類型的裝備
    
    Args:
        user_id: 玩家 ID
        equipment_type: 裝備類型 ('face', 'hair', 'skin', 'top', 'bottom', 'shoes')
        item_id: 物品 ID
    """
    return set_user_field(user_id, equipment_type, item_id)


# ============================================================
# 匯出和導入
# ============================================================

def export_to_json(filename: str) -> bool:
    """導出所有資料到 JSON"""
    return get_db().export_json(filename)


def import_from_json(filename: str) -> bool:
    """從 JSON 匯入資料"""
    return get_db().import_json(filename)


def export_to_sheet_format() -> tuple:
    """
    導出為 SHEET 格式
    
    Returns:
        (headers, rows) 元組
    """
    return get_db().export_to_sheet_format()
