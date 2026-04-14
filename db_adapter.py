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
    from shared.db.adapter import (
        get_db,
        get_user,
        set_user,
        get_user_field,
        set_user_field,
        add_user_field,
        get_user_fields,
        batch_get_user_fields,
        batch_set_user_fields,
        get_all_users,
        count_users,
        delete_user,
        user_exists,
        search_users,
        get_leaderboard,
        add_backup,
        undo_change,
        get_change_log,
        export_to_json,
        import_from_json,
    )
except ImportError as e:
    import warnings
    warnings.warn(f"無法導入 shared.db.adapter: {e}。請確保已執行 Phase 2 import 更新。", DeprecationWarning)
    raise
