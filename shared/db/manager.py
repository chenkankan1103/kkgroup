"""
Database Manager - 全域單例資料庫連線池管理器

解決多進程/多服務共用同一 SQLite 資料庫的連線衝突問題。
所有服務 (bot, shopbot, uibot, unified_api, auto_self_heal) 必須共用此單一連線池。
"""

import asyncio
import aiosqlite
from contextlib import asynccontextmanager
from typing import Optional

from .async_db import AsyncConnectionPool, BUSY_TIMEOUT_MS, DEFAULT_POOL_SIZE, MAX_POOL_SIZE


async def execute_with_retry(
    sql: str, params: tuple = (), max_retries: int = 3, base_delay: float = 0.1
):
    """全域重試執行器 - 透過 DatabaseManager 連線池"""
    pool = await DatabaseManager.get_pool_or_init()
    return await pool.execute_with_retry(sql, params, max_retries, base_delay)


class DatabaseManager:
    """全域資料庫管理器 - 單例模式"""

    _instance: Optional['DatabaseManager'] = None
    _pool: Optional[AsyncConnectionPool] = None
    _db_path: str = "user_data.db"
    _initialized: bool = False
    _init_lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def initialize(cls, db_path: str = "user_data.db", pool_size: int = DEFAULT_POOL_SIZE) -> AsyncConnectionPool:
        """初始化全域連線池（應用啟動時呼叫一次）"""
        async with cls._init_lock:
            if cls._initialized and cls._pool is not None:
                return cls._pool

            cls._db_path = db_path
            cls._pool = AsyncConnectionPool(db_path, pool_size=pool_size)
            await cls._pool.initialize()
            cls._initialized = True
            return cls._pool

    @classmethod
    def get_pool(cls) -> Optional[AsyncConnectionPool]:
        """取得連線池（未初始化返回 None）"""
        return cls._pool

    @classmethod
    async def get_pool_or_init(cls, db_path: str = "user_data.db") -> AsyncConnectionPool:
        """取得連線池，若未初始化則自動初始化"""
        if cls._pool is None:
            return await cls.initialize(db_path)
        return cls._pool

    @classmethod
    @asynccontextmanager
    async def connection(cls):
        """async with DatabaseManager.connection() as conn: ..."""
        pool = await cls.get_pool_or_init()
        async with pool.connection() as conn:
            yield conn

    @classmethod
    async def close(cls):
        """關閉所有連線（應用關閉時呼叫）"""
        async with cls._init_lock:
            if cls._pool is not None:
                await cls._pool.close_all()
                cls._pool = None
                cls._initialized = False

    @classmethod
    async def execute_startup_pragmas(cls):
        """啟動時執行的 PRAGMA 設定（減少 WAL 堆積、提升並發）"""
        pool = await cls.get_pool_or_init()
        async with pool.connection() as conn:
            # 更積極的 checkpoint：每 100 頁而非預設 1000
            await conn.execute("PRAGMA wal_autocheckpoint=100")
            # 啟動時清理 WAL
            await conn.execute("PRAGMA wal_checkpoint=TRUNCATE")
            # 確保外鍵約束
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.commit()

    @classmethod
    async def integrity_check(cls) -> tuple[bool, str]:
        """快速完整性檢查"""
        pool = await cls.get_pool_or_init()
        async with pool.connection() as conn:
            cursor = await conn.execute("PRAGMA quick_check")
            result = await cursor.fetchone()
            is_ok = result[0] == "ok" if result else False
            return is_ok, result[0] if result else "unknown"

    @classmethod
    async def full_integrity_check(cls) -> tuple[bool, str]:
        """完整完整性檢查（較慢）"""
        pool = await cls.get_pool_or_init()
        async with pool.connection() as conn:
            cursor = await conn.execute("PRAGMA integrity_check")
            result = await cursor.fetchone()
            is_ok = result[0] == "ok" if result else False
            return is_ok, result[0] if result else "unknown"


# 全域單例快捷函數
_db_manager = DatabaseManager()

async def get_db_pool(db_path: str = "user_data.db") -> AsyncConnectionPool:
    """取得全域連線池（相容原有 get_pool API）"""
    return await _db_manager.get_pool_or_init(db_path)

async def init_db_pool(db_path: str = "user_data.db", pool_size: int = DEFAULT_POOL_SIZE) -> AsyncConnectionPool:
    """初始化全域連線池"""
    return await _db_manager.initialize(db_path, pool_size)

async def close_db_pool():
    """關閉全域連線池"""
    await _db_manager.close()

@asynccontextmanager
async def db_connection():
    """async with db_connection() as conn: ..."""
    async with _db_manager.connection() as conn:
        yield conn