"""
商店系統數據庫適配層 - 使用 Sheet-Driven DB
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional

# 匯入新的 DB 適配層
import sys
import os
sys.path.insert(0, os.path.dirname(__file__) + '/../..')
from db_adapter import (
    get_user_field,
    set_user_field,
    add_user_field,
    get_user_equipment,
    update_user_equipment,
)

async def get_user_kkcoin(user_id: int) -> int:
    """獲取用戶KKcoin數量"""
    return get_user_field(user_id, 'kkcoin', default=0)


async def update_user_kkcoin(user_id: int, amount: int) -> bool:
    """
    更新用戶KKcoin數量
    正數 = 增加，負數 = 減少
    """
    return add_user_field(user_id, 'kkcoin', amount)


async def update_user_equipment(user_id: int, equipment_type: str, item_id: int) -> bool:
    """更新用戶裝備"""
    return set_user_field(user_id, equipment_type, item_id)


async def get_user_equipment(user_id: int) -> dict:
    """獲取用戶裝備信息"""
    equipment = {
        'face': get_user_field(user_id, 'face', default=20000),
        'hair': get_user_field(user_id, 'hair', default=30000),
        'skin': get_user_field(user_id, 'skin', default=12000),
        'top': get_user_field(user_id, 'top', default=1040010),
        'bottom': get_user_field(user_id, 'bottom', default=1060096),
        'shoes': get_user_field(user_id, 'shoes', default=1072288),
    }
    return equipment


async def create_temp_roles_table() -> bool:
    """創建臨時角色追蹤表"""
    try:
        from db_adapter import get_db
        db = get_db()
        # DB 引擎會自動管理所有表
        print("✅ 臨時角色表已就緒")
        return True
    except Exception as e:
        print(f"❌ 創建臨時角色表失敗: {e}")
        return False


async def add_temp_role(user_id: int, role_id: int, guild_id: int, duration_seconds: int) -> bool:
    """添加臨時角色記錄"""
    # 在新系統中，可以使用 JSON 欄位存儲臨時角色信息
    try:
        from db_adapter import set_user_field
        import json
        
        expires_at = (datetime.now() + timedelta(seconds=duration_seconds)).isoformat()
        
        # 存為 JSON 格式
        temp_role_data = {
            'user_id': user_id,
            'role_id': role_id,
            'guild_id': guild_id,
            'expires_at': expires_at,
            'created_at': datetime.now().isoformat()
        }
        
        # 可以存儲到一個 temp_roles JSON 欄位
        set_user_field(user_id, 'temp_role_info', json.dumps(temp_role_data, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"❌ 添加臨時角色失敗: {e}")
        return False


async def get_expired_roles() -> list:
    """獲取已過期的角色"""
    # 在新系統中，需要檢查所有用戶的 temp_role_info 是否已過期
    try:
        from db_adapter import get_db
        import json
        
        db = get_db()
        all_users = db.get_all_users()
        expired_roles = []
        
        now = datetime.now()
        for user in all_users:
            temp_role_str = user.get('temp_role_info')
            if temp_role_str:
                try:
                    temp_role = json.loads(temp_role_str)
                    expires_at = datetime.fromisoformat(temp_role['expires_at'])
                    if expires_at <= now:
                        expired_roles.append(temp_role)
                except:
                    pass
        
        return expired_roles
    except Exception as e:
        print(f"❌ 獲取過期角色失敗: {e}")
        return []


async def remove_temp_role_record(user_id: int) -> bool:
    """移除臨時角色記錄"""
    try:
        from db_adapter import set_user_field
        set_user_field(user_id, 'temp_role_info', None)
        return True
    except Exception as e:
        print(f"❌ 移除臨時角色失敗: {e}")
        return False
    """移除臨時角色記錄"""
    async with aiosqlite.connect('./user_data.db') as db:
        await db.execute('DELETE FROM temp_roles WHERE id = ?', (record_id,))
        await db.commit()

async def get_user_temp_roles(user_id: int):
    """獲取用戶的所有臨時角色"""
    async with aiosqlite.connect('./user_data.db') as db:
        cursor = await db.execute('''
            SELECT id, role_id, guild_id, expires_at 
            FROM temp_roles 
            WHERE user_id = ? AND expires_at > ?
        ''', (user_id, datetime.now()))
        return await cursor.fetchall()
