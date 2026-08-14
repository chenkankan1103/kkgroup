"""
Async DB Adapter - 給 Cog 直接 import 的非同步便捷函數

用法：
    from shared.db.async_adapter import (
        get_user_kkcoin, update_user_kkcoin,
        get_user_field, set_user_field, add_user_field,
        get_user, set_user
    )

    # 在 async 函數中直接 await
    balance = await get_user_kkcoin(user_id)
    await update_user_kkcoin(user_id, 100)
"""

from .async_db import get_async_db
from typing import Any, Optional, Union, Dict, List, Tuple


# ========== 核心便捷函數 ==========

async def get_user(user_id: Union[int, str]) -> Optional[Dict[str, Any]]:
    """獲取用戶完整資料"""
    return await (await get_async_db()).get_user(user_id)


async def set_user(user_id: Union[int, str], data: Dict[str, Any]) -> bool:
    """設置用戶資料 (INSERT OR REPLACE)"""
    return await (await get_async_db()).set_user(user_id, data)


async def get_user_field(user_id: Union[int, str], field: str, default: Any = None) -> Any:
    """獲取用戶特定欄位的值"""
    return await (await get_async_db()).get_user_field(user_id, field, default)


async def set_user_field(user_id: Union[int, str], field: str, value: Any) -> bool:
    """更新用戶特定欄位"""
    return await (await get_async_db()).set_user_field(user_id, field, value)


async def add_user_field(
    user_id: Union[int, str], field: str, amount: Union[int, float]
) -> bool:
    """增加/減少用戶特定欄位的值 (僅限數字類型)"""
    return await (await get_async_db()).update_user_field(user_id, field, amount)


async def get_user_by_field(field: str, value: Any) -> Optional[Dict[str, Any]]:
    """根據指定欄位和值查詢用戶"""
    return await (await get_async_db()).get_user_by_field(field, value)


async def get_all_users(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """獲取所有用戶"""
    return await (await get_async_db()).get_all_users(limit)


async def delete_user(user_id: Union[int, str]) -> bool:
    """刪除用戶"""
    return await (await get_async_db()).delete_user(user_id)


async def get_db_stats() -> Dict[str, Any]:
    """取得資料庫統計資訊"""
    return await (await get_async_db()).get_stats()


async def count_users() -> int:
    """計算用戶總數"""
    stats = await get_db_stats()
    return stats.get("total_users", 0)


# ========== 向後相容別名 (供 kcoin.py 等現有代碼使用) ==========

async def get_user_balance(user_id: Union[int, str]) -> int:
    """向後相容：獲取玩家 KKCoin 餘額"""
    return await get_user_kkcoin(user_id)


async def update_user_balance(user_id: Union[int, str], amount: int) -> bool:
    """向後相容：更新玩家 KKCoin 餘額"""
    return await update_user_kkcoin(user_id, amount)


# ========== 向後相容性函數 (為舊代碼提供支持) ==========

async def get_user_kkcoin(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家 kkcoin"""
    return await get_user_field(user_id, "kkcoin", default=0)


async def update_user_kkcoin(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 增加或減少玩家 kkcoin"""
    return await add_user_field(user_id, "kkcoin", amount)


async def get_user_level(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家等級"""
    return await get_user_field(user_id, "level", default=1)


async def get_user_xp(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家經驗值"""
    return await get_user_field(user_id, "xp", default=0)


async def add_user_xp(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 增加玩家經驗值"""
    return await add_user_field(user_id, "xp", amount)


async def get_user_hp(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家 HP"""
    return await get_user_field(user_id, "hp", default=100)


async def get_user_stamina(user_id: Union[int, str]) -> int:
    """(向後相容) 獲取玩家耐力"""
    return await get_user_field(user_id, "stamina", default=100)


async def get_user_title(user_id: Union[int, str]) -> str:
    """(向後相容) 獲取玩家頭銜"""
    return await get_user_field(user_id, "title", default="新手")


async def update_user_hp(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 更新玩家 HP"""
    return await add_user_field(user_id, "hp", amount)


async def update_user_stamina(user_id: Union[int, str], amount: int) -> bool:
    """(向後相容) 更新玩家耐力"""
    return await add_user_field(user_id, "stamina", amount)


# ========== 裝備系統 (shop_commands 專用) ==========

async def get_user_equipment(user_id: Union[int, str]) -> Dict[str, int]:
    """(向後相容) 獲取玩家所有裝備"""
    user = await get_user(user_id)
    if not user:
        return {
            "face": 20000,
            "hair": 30000,
            "skin": 12000,
            "top": 1040010,
            "bottom": 1060096,
            "shoes": 1072288,
        }
    return {
        "face": user.get("face", 20000),
        "hair": user.get("hair", 30000),
        "skin": user.get("skin", 12000),
        "top": user.get("top", 1040010),
        "bottom": user.get("bottom", 1060096),
        "shoes": user.get("shoes", 1072288),
    }


async def update_user_equipment(
    user_id: Union[int, str], equipment_type: str, item_id: int
) -> bool:
    """(向後相容) 更新玩家某類型的裝備"""
    return await set_user_field(user_id, equipment_type, item_id)


# ========== 匯出和導入 ==========

async def export_to_json(filename: str) -> bool:
    """導出所有資料到 JSON"""
    db = await get_async_db()
    return await db.export_json(filename)


async def import_from_json(filename: str) -> bool:
    """從 JSON 匯入資料"""
    db = await get_async_db()
    return await db.import_json(filename)


async def export_to_sheet_format() -> tuple:
    """導出為 SHEET 格式"""
    db = await get_async_db()
    return await db.export_to_sheet_format()


# ========== 股票市場系統 ==========

async def get_user_stocks(user_id: Union[int, str]) -> List[Dict[str, Any]]:
    """獲取使用者持有的股票列表"""
    import json
    stocks_json = await get_user_field(user_id, "stocks", default="[]")
    try:
        if isinstance(stocks_json, str):
            return json.loads(stocks_json) if stocks_json else []
        elif isinstance(stocks_json, list):
            return stocks_json
        else:
            return []
    except (json.JSONDecodeError, TypeError):
        return []


async def set_user_stocks(user_id: Union[int, str], stocks: List[Dict[str, Any]]) -> bool:
    """設置使用者的股票列表"""
    import json
    stocks_json = json.dumps(stocks, ensure_ascii=False)
    return await set_user_field(user_id, "stocks", stocks_json)


async def add_stock_position(
    user_id: Union[int, str], symbol: str, shares: int, price: float
) -> bool:
    """增加或更新使用者的股票持倉（買入）"""
    stocks = await get_user_stocks(user_id)
    for position in stocks:
        if position["symbol"] == symbol:
            old_shares = position["shares"]
            old_cost = position["avg_cost"]
            new_total_cost = old_shares * old_cost + shares * price
            new_total_shares = old_shares + shares
            new_avg_cost = new_total_cost / new_total_shares
            position["shares"] = new_total_shares
            position["avg_cost"] = new_avg_cost
            break
    else:
        stocks.append({"symbol": symbol, "shares": shares, "avg_cost": price})
    return await set_user_stocks(user_id, stocks)


async def close_stock_position(
    user_id: Union[int, str], symbol: str, shares: int, price: float
) -> Tuple[bool, Optional[float]]:
    """減少或平掉使用者的股票持倉（賣出）"""
    stocks = await get_user_stocks(user_id)
    for idx, position in enumerate(stocks):
        if position["symbol"] == symbol:
            if position["shares"] < shares:
                return (False, None)
            realized_pnl = (price - position["avg_cost"]) * shares
            position["shares"] -= shares
            if position["shares"] == 0:
                stocks.pop(idx)
            success = await set_user_stocks(user_id, stocks)
            return (success, realized_pnl)
    return (False, None)


async def get_user_total_stock_value(
    user_id: Union[int, str], current_prices: Dict[str, float]
) -> Tuple[float, float, float]:
    """計算使用者股票投資組合的總價值"""
    stocks = await get_user_stocks(user_id)
    total_market_value = 0.0
    total_cost = 0.0
    for position in stocks:
        symbol = position["symbol"]
        shares = position["shares"]
        avg_cost = position["avg_cost"]
        cost = shares * avg_cost
        total_cost += cost
        if symbol in current_prices:
            market_value = shares * current_prices[symbol]
            total_market_value += market_value
    unrealized_pnl = total_market_value - total_cost
    return (total_market_value, total_cost, unrealized_pnl)


# ========== 園區中央儲備池 ==========

SYSTEM_CONFIG_ID = 999999999
CENTRAL_RESERVE_FIELD = "central_reserve"
CENTRAL_RESERVE_DIGITAL_USD_FIELD = "central_reserve_digital_usd"


async def get_central_reserve() -> int:
    """獲取園區中央儲備池的總額"""
    value = await get_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, default=0)
    try:
        if isinstance(value, str):
            return int(float(value))
        return int(value)
    except (ValueError, TypeError):
        return 0


async def add_to_central_reserve(amount: int) -> bool:
    """增加中央儲備池的金額"""
    if amount < 0:
        return False
    current = await get_central_reserve()
    new_amount = current + amount
    return await set_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, new_amount)


async def remove_from_central_reserve(amount: int) -> bool:
    """從中央儲備池中取出金額"""
    current = await get_central_reserve()
    if current < amount:
        return False
    return await add_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, -amount)


async def set_central_reserve(amount: int) -> bool:
    """直接設置中央儲備池的金額"""
    return await set_user_field(SYSTEM_CONFIG_ID, CENTRAL_RESERVE_FIELD, amount)


async def get_central_reserve_digital_usd() -> float:
    """獲取園區中央儲備池中的數位美金總額"""
    value = await get_user_field(
        SYSTEM_CONFIG_ID, CENTRAL_RESERVE_DIGITAL_USD_FIELD, default=0
    )
    try:
        if isinstance(value, str):
            return float(value)
        return float(value)
    except (ValueError, TypeError):
        return 0.0


async def add_to_central_reserve_digital_usd(amount: float) -> bool:
    """增加中央儲備池的數位美金"""
    if amount < 0:
        return False
    current = await get_central_reserve_digital_usd()
    new_amount = current + amount
    return await set_user_field(
        SYSTEM_CONFIG_ID, CENTRAL_RESERVE_DIGITAL_USD_FIELD, new_amount
    )


async def remove_from_central_reserve_digital_usd(amount: float) -> bool:
    """從中央儲備池中取出數位美金"""
    current = await get_central_reserve_digital_usd()
    if current < amount:
        return False
    new_amount = current - amount
    return await set_user_field(
        SYSTEM_CONFIG_ID, CENTRAL_RESERVE_DIGITAL_USD_FIELD, new_amount
    )


async def set_central_reserve_digital_usd(amount: float) -> bool:
    """直接設置中央儲備池的數位美金"""
    return await set_user_field(
        SYSTEM_CONFIG_ID, CENTRAL_RESERVE_DIGITAL_USD_FIELD, amount
    )


async def get_user_digital_usd(user_id: Union[int, str]) -> float:
    """(向後相容) 獲取玩家數位美金（洗出的白錢）"""
    value = await get_user_field(user_id, "digital_usd", default=0)
    # 確保返回的是數字類型（處理字符串情況）
    if isinstance(value, str):
        # 處理空字符串
        if not value or value.strip() == "":
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    return float(value) if value else 0.0


async def update_user_digital_usd(user_id: Union[int, str], amount: float) -> bool:
    """(向後相容) 更新玩家數位美金"""
    return await add_user_field(user_id, "digital_usd", amount)


async def get_total_reserves() -> Dict[str, float]:
    """獲取中央儲備池的完整狀態（KK + D-USD）"""
    kkcoin = await get_central_reserve()
    digital_usd = await get_central_reserve_digital_usd()
    exchange_rate = await get_dynamic_exchange_rate()
    usd_as_kk = digital_usd * exchange_rate
    total_value = kkcoin + usd_as_kk
    return {
        "kkcoin": kkcoin,
        "digital_usd": digital_usd,
        "total_value_in_kk": total_value,
        "exchange_rate": exchange_rate,
    }


async def get_reserve_pressure() -> float:
    """計算洗錢壓力百分比 (0-100%)"""
    RESERVE_THRESHOLD = 1_000_000
    current = await get_central_reserve()
    if current <= 0:
        return 0.0
    if current >= RESERVE_THRESHOLD:
        return 100.0
    return (current / RESERVE_THRESHOLD) * 100.0


async def get_dynamic_fee_rate() -> float:
    """根據儲備池狀態計算動態手續費率"""
    pressure = await get_reserve_pressure()
    if pressure >= 80:
        return 0.03
    elif pressure >= 50:
        return 0.05
    else:
        return 0.08


async def get_reserve_announcement() -> str:
    """根據儲備池狀態生成每日公告"""
    pressure = await get_reserve_pressure()
    if pressure >= 80:
        return "[充裕] 金庫充裕，今日斷點手續費優待中 (3%)。"
    elif pressure >= 50:
        return "[正常] 金庫運轉正常，斷點手續費維持標準 (5%)。"
    else:
        return "[警報] 金庫風險警報！斷點手續費提升至 8%，請謹慎操作。"


# ========== 浮動匯率系統 ==========

async def get_total_kkcoin_supply() -> float:
    """計算全網 KK 幣總供應量"""
    all_users = await get_all_users()
    total = 0.0
    for user in all_users:
        kkcoin = float(user.get("kkcoin", 0) or 0)
        total += kkcoin
    return total


async def calculate_inflation_rate() -> float:
    """計算通膨指數 (百分比)"""
    BASE_SUPPLY = 1_000_000
    current_supply = await get_total_kkcoin_supply()
    if current_supply <= BASE_SUPPLY:
        return 0.0
    inflation_percent = ((current_supply - BASE_SUPPLY) / BASE_SUPPLY) * 100
    return inflation_percent


async def get_dynamic_exchange_rate() -> float:
    """計算浮動匯率（KK 幣對 D-USD）"""
    BASE_RATE = 35.0
    inflation_percent = await calculate_inflation_rate()
    dynamic_rate = BASE_RATE * (1 + inflation_percent / 100)
    return dynamic_rate


async def get_inflation_info() -> Dict[str, float]:
    """獲取通膨和匯率相關的完整信息"""
    total_supply = await get_total_kkcoin_supply()
    inflation = await calculate_inflation_rate()
    current_rate = await get_dynamic_exchange_rate()
    return {
        "total_supply": total_supply,
        "inflation_percent": inflation,
        "base_rate": 35.0,
        "current_rate": current_rate,
    }


# ========== 初始化/關閉 ==========

async def init_async_db(db_path: str = "user_data.db"):
    """應用啟動時呼叫：初始化連線池並建立資料表"""
    from .async_db import get_pool, AsyncSheetDrivenDB
    pool = get_pool(db_path)
    await pool.initialize()
    db = AsyncSheetDrivenDB(db_path)
    await db._ensure_initialized()
    return db


async def close_async_db():
    """應用關閉時呼叫：關閉所有連線"""
    from .async_db import _pool
    if _pool:
        await _pool.close_all()
