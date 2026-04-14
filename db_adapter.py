# -*- coding: utf-8 -*-
"""
DB 適配層相容層 - 保持向後相容性

このファイルは後方互換性のための相容層です。
所有的実装已移至 shared/db/adapter.py、shared/db/sheet_driven_db.py 等

使用示例（現存コード）:
    from db_adapter import get_user_field, set_user_field
    
新コード應使用:
    from shared.db.adapter import get_user_field, set_user_field
"""

# 相容層轉導 - 導入所有公開函數以保持現存代碼正常運作
try:
    from shared.db.db_adapter import (
        # 核心 DB 操作
        get_db,
        get_user,
        set_user,
        get_user_field,
        set_user_field,
        add_user_field,
        get_all_users,
        count_users,
        delete_user,
        get_user_by_field,
        # 向後相容性函數 - kkcoin
        get_user_kkcoin,
        update_user_kkcoin,
        # 向後相容性函數 - 等級與經驗
        get_user_level,
        get_user_xp,
        add_user_xp,
        # 向後相容性函數 - HP 與耐力
        get_user_hp,
        get_user_stamina,
        update_user_hp,
        update_user_stamina,
        # 向後相容性函數 - 頭銜
        get_user_title,
        # 設備系統
        get_user_equipment,
        update_user_equipment,
        # 股票系統
        get_user_stocks,
        set_user_stocks,
        add_stock_position,
        close_stock_position,
        get_user_total_stock_value,
        # 導入匯出
        export_to_json,
        import_from_json,
    )
except ImportError as e:
    import warnings
    warnings.warn(f"無法導入 shared.db.db_adapter: {e}。請確保已執行 Phase 2 import 更新。", DeprecationWarning)
    raise
