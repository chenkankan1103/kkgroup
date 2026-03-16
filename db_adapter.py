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
from typing import Any, Optional, Union, Dict, List, Tuple
import asyncio
import json

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
# 非同步操作 (用於避免事件迴圈阻塞)
# ============================================================

async def async_set_user(user_id: Union[int, str], data: Dict[str, Any]) -> bool:
    """
    非同步版本的 set_user - 在線程池中執行以避免阻塞事件迴圈
    
    Args:
        user_id: 用戶 ID
        data: 更新的資料
        
    Returns:
        是否成功
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: set_user(user_id, data))


async def async_set_user_field(user_id: Union[int, str], field: str, value: Any) -> bool:
    """
    非同步版本的 set_user_field
    
    Args:
        user_id: 用戶 ID
        field: 欄位名
        value: 新值
        
    Returns:
        是否成功
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: set_user_field(user_id, field, value))


async def async_batch_set_users(updates: Dict[Union[int, str], Dict[str, Any]]) -> int:
    """
    非同步批量更新多個用戶，避免事件迴圈阻塞
    
    Args:
        updates: {'user_id': {'field': value, ...}, ...}
        
    Returns:
        成功更新的用戶數
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: batch_set_users(updates))


async def async_get_all_users(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    非同步版本的 get_all_users
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: get_all_users(limit))


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


# ============================================================
# 股票市場系統 (shop_commands/stock_market 專用)
# ============================================================

def get_user_stocks(user_id: Union[int, str]) -> List[Dict[str, Any]]:
    """
    獲取使用者持有的股票列表
    
    Args:
        user_id: 用戶 ID
        
    Returns:
        [{'symbol': '2330.TW', 'shares': 10, 'avg_cost': 500.0}, ...] 或 []
    """
    stocks_json = get_user_field(user_id, 'stocks', default='[]')
    
    try:
        if isinstance(stocks_json, str):
            return json.loads(stocks_json) if stocks_json else []
        elif isinstance(stocks_json, list):
            return stocks_json
        else:
            return []
    except (json.JSONDecodeError, TypeError):
        return []


def set_user_stocks(user_id: Union[int, str], stocks: List[Dict[str, Any]]) -> bool:
    """
    設置使用者的股票列表
    
    Args:
        user_id: 用戶 ID
        stocks: [{'symbol': '2330.TW', 'shares': 10, 'avg_cost': 500.0}, ...]
        
    Returns:
        是否成功
    """
    import json
    stocks_json = json.dumps(stocks, ensure_ascii=False)
    return set_user_field(user_id, 'stocks', stocks_json)


def add_stock_position(
    user_id: Union[int, str],
    symbol: str,
    shares: int,
    price: float
) -> bool:
    """
    增加或更新使用者的股票持倉（買入）
    
    Args:
        user_id: 用戶 ID
        symbol: 股票代號（例如 '2330.TW'）
        shares: 買入數量
        price: 買入價格
        
    Returns:
        是否成功
    """
    stocks = get_user_stocks(user_id)
    
    # 查找是否已有該持倉
    for position in stocks:
        if position['symbol'] == symbol:
            # 更新平均成本與持倉數
            old_shares = position['shares']
            old_cost = position['avg_cost']
            
            new_total_cost = old_shares * old_cost + shares * price
            new_total_shares = old_shares + shares
            new_avg_cost = new_total_cost / new_total_shares
            
            position['shares'] = new_total_shares
            position['avg_cost'] = new_avg_cost
            break
    else:
        # 新增持倉
        stocks.append({
            'symbol': symbol,
            'shares': shares,
            'avg_cost': price
        })
    
    return set_user_stocks(user_id, stocks)


def close_stock_position(
    user_id: Union[int, str],
    symbol: str,
    shares: int,
    price: float
) -> Tuple[bool, Optional[float]]:
    """
    減少或平掉使用者的股票持倉（賣出）
    
    Args:
        user_id: 用戶 ID
        symbol: 股票代號
        shares: 賣出數量
        price: 賣出價格
        
    Returns:
        (是否成功, 實現損益金額)
        實現損益 = (賣出價 - 平均成本) * 賣出數量
    """
    stocks = get_user_stocks(user_id)
    
    for idx, position in enumerate(stocks):
        if position['symbol'] == symbol:
            if position['shares'] < shares:
                return (False, None)  # 持倉不足
            
            # 計算實現損益
            realized_pnl = (price - position['avg_cost']) * shares
            
            # 更新持倉
            position['shares'] -= shares
            
            if position['shares'] == 0:
                # 持倉清空，移除該項
                stocks.pop(idx)
            
            success = set_user_stocks(user_id, stocks)
            return (success, realized_pnl)
    
    return (False, None)  # 找不到該持倉


def get_user_total_stock_value(
    user_id: Union[int, str],
    current_prices: Dict[str, float]
) -> Tuple[float, float, float]:
    """
    計算使用者股票投資組合的總價值
    
    Args:
        user_id: 用戶 ID
        current_prices: {'2330.TW': 500.0, ...} 當前價格字典
        
    Returns:
        (總市值, 總成本, 未實現損益)
    """
    stocks = get_user_stocks(user_id)
    
    total_market_value = 0.0
    total_cost = 0.0
    
    for position in stocks:
        symbol = position['symbol']
        shares = position['shares']
        avg_cost = position['avg_cost']
        
        cost = shares * avg_cost
        total_cost += cost
        
        if symbol in current_prices:
            market_value = shares * current_prices[symbol]
            total_market_value += market_value
    
    unrealized_pnl = total_market_value - total_cost
    
    return (total_market_value, total_cost, unrealized_pnl)


# ============================================================
# 園區中央儲備池 (全局金庫系統)
# ============================================================

SYSTEM_CONFIG_ID = 999999999  # 系統配置的特殊 ID（特殊數字，避免與真實玩家ID衝突）
CENTRAL_RESERVE_FIELD = "central_reserve"  # 中央儲備池欄位名


def get_central_reserve() -> int:
    """
    獲取園區中央儲備池的總額
    
    Returns:
        儲備池中的 KK 幣總額 (預設 0)
    """
    value = get_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, default=0)
    # 確保返回的是整數（可能從資料庫以字符串形式存儲）
    try:
        if isinstance(value, str):
            return int(float(value))  # 先轉為 float 再轉 int，支持 "123.0" 形式
        return int(value)
    except (ValueError, TypeError):
        return 0


def add_to_central_reserve(amount: int) -> bool:
    """
    增加中央儲備池的金額 (當玩家輸錢、購買道具或支付手續費時)
    
    Args:
        amount: 要加入的 KK 幣數量 (應為正整數)
        
    Returns:
        是否成功
    """
    if amount < 0:
        print(f"⚠️ 嘗試向儲備池添加負數: {amount}")
        return False
    return add_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, amount)


def remove_from_central_reserve(amount: int) -> bool:
    """
    從中央儲備池中取出金額 (當玩家完成金流斷點、領取獎勵時)
    
    Args:
        amount: 要取出的 KK 幣數量 (應為正整數)
        
    Returns:
        是否成功
    """
    current = get_central_reserve()
    if current < amount:
        print(f"⚠️ 儲備池餘額不足: 當前 {current}, 要取 {amount}")
        return False
    return add_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, -amount)


def set_central_reserve(amount: int) -> bool:
    """
    直接設置中央儲備池的金額 (用於初始化或管理員操作)
    
    Args:
        amount: 新的總額
        
    Returns:
        是否成功
    """
    return set_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, amount)


def get_reserve_pressure() -> float:
    """
    計算洗錢壓力百分比 (0-100%)
    
    壓力計算邏輯：
    - 儲備池滿（充裕）: 手續費低，鼓勵洗錢
    - 儲備池空（枯竭）: 手續費高，限制洗錢
    
    Returns:
        壓力百分比 (0.0 = 空虛, 100.0 = 充裕)
    """
    RESERVE_THRESHOLD = 1_000_000  # 目標儲備額 100 萬 KK 幣
    current = get_central_reserve()
    
    if current <= 0:
        return 0.0
    if current >= RESERVE_THRESHOLD:
        return 100.0
    
    return (current / RESERVE_THRESHOLD) * 100.0


def get_dynamic_fee_rate() -> float:
    """
    根據儲備池狀態計算動態手續費率
    
    手續費率邏輯：
    - 儲備池充裕 (>80%): 3% (優待)
    - 儲備池正常 (50-80%): 5% (正常)
    - 儲備池枯竭 (<50%): 8% (高額)
    
    Returns:
        手續費率 (小數表示，如 0.05 = 5%)
    """
    pressure = get_reserve_pressure()
    
    if pressure >= 80:
        return 0.03  # 優待費率
    elif pressure >= 50:
        return 0.05  # 正常費率
    else:
        return 0.08  # 高額費率


def get_reserve_announcement() -> str:
    """
    根據儲備池狀態生成每日公告
    
    Returns:
        公告文字
    """
    pressure = get_reserve_pressure()
    
    if pressure >= 80:
        return "[充裕] 金庫充裕，今日斷點手續費優待中 (3%)。"
    elif pressure >= 50:
        return "[正常] 金庫運轉正常，斷點手續費維持標準 (5%)。"
    else:
        return "[警報] 金庫風險警報！斷點手續費提升至 8%，請謹慎操作。"
