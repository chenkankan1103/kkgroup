# -*- coding: utf-8 -*-
"""
DB 適配層相容層 - 保持向後相容性

此檔案是向後相容性的相容層。
所有實現已移至 shared/db/db_adapter.py、shared/db/sheet_driven_db.py 等核心模塊

使用示例（現存代碼）:
    from db_adapter import get_user_field, set_user_field

新代碼應使用:
    from shared.db.db_adapter import get_user_field, set_user_field

說明：
  - 根目錄 db_adapter.py：相容層轉導文件（重定向 import）
  - shared/db/db_adapter.py：核心實現文件（實際邏輯）

  所有 import 都指向同一個實現，保持向後相容性。
"""

# 相容層轉導 - 導入所有公開函數以保持現存代碼正常運作
try:
    from shared.db.db_adapter import (  # 核心 DB 操作; 向後相容性函數 - kkcoin; 向後相容性函數 - 等級與經驗; 向後相容性函數 - HP 與耐力; 向後相容性函數 - 頭銜; 設備系統; 股票系統; 中央儲備系統; 動態費率與匯率系統; 非同步操作; 導入匯出
        add_stock_position, add_to_central_reserve,
        add_to_central_reserve_digital_usd, add_user_field, add_user_xp,
        async_batch_set_users, async_get_all_users, async_get_user,
        async_get_user_by_field, async_set_user, async_set_user_field,
        close_stock_position, count_users, delete_user, export_to_json,
        get_all_users, get_central_reserve, get_central_reserve_digital_usd,
        get_db, get_dynamic_exchange_rate, get_dynamic_fee_rate,
        get_reserve_announcement, get_reserve_pressure, get_total_reserves,
        get_user, get_user_by_field, get_user_equipment, get_user_field,
        get_user_hp, get_user_kkcoin, get_user_level, get_user_stamina,
        get_user_stocks, get_user_title, get_user_total_stock_value,
        get_user_xp, import_from_json, remove_from_central_reserve,
        remove_from_central_reserve_digital_usd, set_central_reserve,
        set_central_reserve_digital_usd, set_user, set_user_field,
        set_user_stocks, update_user_equipment, update_user_hp,
        update_user_kkcoin, update_user_stamina)
except ImportError as e:
    import warnings

    warnings.warn(
        f"無法導入 shared.db.db_adapter: {e}。請確保已執行 Phase 2 import 更新。",
        DeprecationWarning,
    )
    raise
