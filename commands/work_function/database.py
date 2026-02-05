"""
Work 系統數據庫適配層 - 使用新的 Sheet-Driven DB

該模塊提供了工作系統所需的所有數據庫操作，
使用新的 db_adapter (基於 Sheet-Driven DB 引擎)
"""

import os
import traceback
from typing import Dict, Any, Optional
from discord.ext import commands

# 匯入統一的數據庫適配層
from db_adapter import (
    get_user as db_get_user,
    set_user,
    get_user_field,
    set_user_field,
    add_user_field,
    delete_user as db_delete_user,
    get_all_users as db_get_all_users,
)

DB_PATH = os.getenv("DB_PATH", "user_data.db")


def init_db():
    """
    初始化數據庫 (已遷移到 Sheet-Driven 系統)
    
    Schema 現在從 SHEET Row 1 自動讀取，無需手動管理
    """
    try:
        from db_adapter import get_db
        db = get_db()
        stats = db.get_stats()
        print(f"✅ 數據庫已就緒: {stats['total_users']} 個用戶，{stats['total_columns']} 個欄位")
        return True
    except Exception as e:
        print(f"❌ 數據庫初始化失敗: {e}")
        traceback.print_exc()
        return False


def get_user(user_id) -> Optional[Dict[str, Any]]:
    """
    獲取用戶完整資料
    
    Args:
        user_id: 用戶 ID
        
    Returns:
        用戶資料字典，或 None
    """
    try:
        user = db_get_user(user_id)
        
        if not user:
            # 新用戶，自動建立
            set_user(user_id, {'user_id': int(user_id)})
            user = db_get_user(user_id)
        
        return user
    except Exception as e:
        traceback.print_exc()
        return None


def get_all_users():
    """取得所有用戶資料（用於重建持久化 View）"""
    try:
        return db_get_all_users()
    except Exception as e:
        traceback.print_exc()
        return []


def update_user(user_id, **kwargs):
    """
    更新用戶多個欄位
    
    示例:
        update_user(user_id, xp=100, level=5, title='武士')
    """
    try:
        if kwargs:
            set_user(user_id, kwargs)
        return True
    except Exception as e:
        traceback.print_exc()
        return False


def delete_user(user_id):
    """刪除用戶"""
    try:
        return db_delete_user(user_id)
    except Exception as e:
        traceback.print_exc()
        return False


def reset_user(user_id):
    """
    重置用戶資料（重置為初始狀態）
    """
    try:
        reset_data = {
            'level': 1,
            'xp': 0,
            'kkcoin': 0,
            'last_work_date': None,
            'streak': 0,
            'is_locked': 0,
            'actions_used': '{}',
            'hp': 100,
            'stamina': 100,
        }
        return set_user(user_id, reset_data)
    except Exception as e:
        traceback.print_exc()
        return False

class DatabaseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

# 設置函數 - Discord.py 需要這個函數來載入 cog
async def setup(bot):
    await bot.add_cog(DatabaseCog(bot))
