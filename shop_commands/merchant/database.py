import aiosqlite
import sqlite3
from datetime import datetime, timedelta
from .config import DB_PATH

async def get_user_kkcoin(user_id: int) -> int:
    """獲取用戶KKcoin數量"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT kkcoin FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def update_user_kkcoin(user_id: int, amount: int):
    """更新用戶KKcoin數量"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                kkcoin INTEGER DEFAULT 0,
                face INTEGER DEFAULT 20000,
                hair INTEGER DEFAULT 30000,
                skin INTEGER DEFAULT 12000,
                top INTEGER DEFAULT 1040010,
                bottom INTEGER DEFAULT 1060096,
                shoes INTEGER DEFAULT 1072288
            )
        """)
        await db.execute("""
            INSERT INTO users (user_id, kkcoin)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET kkcoin = kkcoin + ?
        """, (user_id, amount, amount))
        await db.commit()

async def update_user_equipment(user_id: int, equipment_type: str, item_id: int):
    """更新用戶裝備"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {equipment_type} = ? WHERE user_id = ?", (item_id, user_id))
        await db.commit()

async def get_user_equipment(user_id: int) -> dict:
    """獲取用戶裝備信息"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT face, hair, skin, top, bottom, shoes FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'face': row[0] or 20000, 
                    'hair': row[1] or 30000, 
                    'skin': row[2] or 12000,
                    'top': row[3] or 1040010, 
                    'bottom': row[4] or 1060096, 
                    'shoes': row[5] or 1072288
                }
            return {
                'face': 20000, 
                'hair': 30000, 
                'skin': 12000, 
                'top': 1040010, 
                'bottom': 1060096, 
                'shoes': 1072288
            }
async def create_temp_roles_table():
    """創建臨時角色追蹤表"""
    async with aiosqlite.connect('./user_data.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS temp_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

async def add_temp_role(user_id: int, role_id: int, guild_id: int, duration_seconds: int):
    """添加臨時角色記錄"""
    expires_at = datetime.now() + timedelta(seconds=duration_seconds)
    
    async with aiosqlite.connect('./user_data.db') as db:
        await db.execute('''
            INSERT INTO temp_roles (user_id, role_id, guild_id, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, role_id, guild_id, expires_at))
        await db.commit()

async def get_expired_roles():
    """獲取已過期的角色"""
    now = datetime.now()
    async with aiosqlite.connect('./user_data.db') as db:
        cursor = await db.execute('''
            SELECT id, user_id, role_id, guild_id 
            FROM temp_roles 
            WHERE expires_at <= ?
        ''', (now,))
        return await cursor.fetchall()

async def remove_temp_role_record(record_id: int):
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
