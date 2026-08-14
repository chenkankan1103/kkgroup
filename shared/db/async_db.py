"""
Async SQLite Connection Pool + AsyncSheetDrivenDB

非阻塞資料庫操作層，專為 Discord Bot event loop 設計。
使用 aiosqlite + 連線池，解決：
- Event loop 阻塞 (run_in_executor 佔用執行緒池)
- 連線建立開銷 (每 query 新連線)
- 檔案描述符洩漏 (異常時未 close)
- 並發鎖定 (WAL + busy_timeout + 連線複用)
"""

import asyncio
import aiosqlite
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union, Set
from pathlib import Path

# 連線池配置
DEFAULT_POOL_SIZE = 8
MAX_POOL_SIZE = 16
BUSY_TIMEOUT_MS = 30000
ACQUIRE_TIMEOUT = 5.0  # 等待可用連線的最長秒數


class AsyncConnectionPool:
    """aiosqlite 連線池：WAL + busy_timeout + 自動回收"""

    def __init__(self, db_path: str, pool_size: int = DEFAULT_POOL_SIZE):
        self.db_path = db_path
        self.pool_size = pool_size
        self._queue: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=pool_size)
        self._created = 0
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """建立初始連線並啟用 WAL"""
        async with self._init_lock:
            if self._initialized:
                return
            for _ in range(self.pool_size):
                conn = await self._create_connection()
                await self._queue.put(conn)
            self._initialized = True

    async def _create_connection(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        # 每個連線都要設定 WAL + busy_timeout
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        self._created += 1
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        if not self._initialized:
            await self.initialize()
        try:
            # 等待可用連線
            conn = await asyncio.wait_for(self._queue.get(), timeout=ACQUIRE_TIMEOUT)
            # 驗證連線仍存活
            try:
                await conn.execute("SELECT 1")
            except Exception:
                conn = await self._create_connection()
            return conn
        except asyncio.TimeoutError:
            # 池滿時動態擴充 (上限 MAX_POOL_SIZE)
            if self._created < MAX_POOL_SIZE:
                return await self._create_connection()
            raise RuntimeError("DB connection pool exhausted")

    async def release(self, conn: aiosqlite.Connection):
        if self._created <= self.pool_size:
            await self._queue.put(conn)
        else:
            # 超過基礎池大小的連線用完即關閉
            await conn.close()
            self._created -= 1

    async def close_all(self):
        while not self._queue.empty():
            conn = await self._queue.get()
            await conn.close()
        self._created = 0
        self._initialized = False

    @asynccontextmanager
    async def connection(self):
        """async with pool.connection() as conn: ..."""
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)


# 全域單例
_pool: Optional[AsyncConnectionPool] = None

def get_pool(db_path: str = "user_data.db") -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(db_path)
    return _pool


class AsyncSheetDrivenDB:
    """非同步版 SheetDrivenDB - API 與同步版對齊"""

    def __init__(self, db_path: str = "user_data.db"):
        self.db_path = db_path
        self.table_name = "users"
        self._columns_cache: Optional[Set[str]] = None
        self._columns_cache_valid = False
        self._pool = get_pool(db_path)

    async def _ensure_initialized(self):
        """確保資料表存在、系統欄位存在、pool 已初始化"""
        await self._pool.initialize()
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (self.table_name,)
            )
            if not await cursor.fetchone():
                await conn.execute(f"""
                    CREATE TABLE {self.table_name} (
                        user_id INTEGER PRIMARY KEY,
                        _created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        _updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await conn.commit()
            else:
                await self._ensure_system_columns(conn)
            await self._refresh_columns_cache(conn)

    async def _ensure_system_columns(self, conn: aiosqlite.Connection):
        cursor = await conn.execute(f"PRAGMA table_info({self.table_name})")
        existing = {row[1] async for row in cursor}
        for col in ("_created_at", "_updated_at"):
            if col not in existing:
                await conn.execute(f'ALTER TABLE {self.table_name} ADD COLUMN "{col}" TIMESTAMP')
                await conn.commit()

    async def _refresh_columns_cache(self, conn: aiosqlite.Connection):
        cursor = await conn.execute(f"PRAGMA table_info({self.table_name})")
        self._columns_cache = {row[1] async for row in cursor}
        self._columns_cache_valid = True

    # ========== 公開 API (與同步版同名) ==========

    async def get_user(self, user_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        await self._ensure_initialized()
        user_id = int(user_id)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT * FROM {self.table_name} WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def set_user(self, user_id: Union[int, str], data: Dict[str, Any]) -> bool:
        await self._ensure_initialized()
        user_id = int(user_id)

        async with self._pool.connection() as conn:
            # 1. 讀現有資料
            cursor = await conn.execute(
                f"SELECT * FROM {self.table_name} WHERE user_id = ?", (user_id,)
            )
            existing_row = await cursor.fetchone()

            if existing_row:
                existing_data = self._row_to_dict(existing_row)
                existing_data.update(data)
                existing_data["_updated_at"] = datetime.now().isoformat()
            else:
                existing_data = {
                    "user_id": user_id,
                    "_created_at": datetime.now().isoformat(),
                    "_updated_at": datetime.now().isoformat(),
                }
                existing_data.update(data)

            # 2. 確保欄位存在 (需在同一連線交易內)
            await self._ensure_columns(conn, list(existing_data.keys()))

            # 3. INSERT OR REPLACE
            columns = list(existing_data.keys())
            placeholders = ", ".join(["?" for _ in columns])
            columns_str = ", ".join([f'"{c}"' for c in columns])
            sql = f"INSERT OR REPLACE INTO {self.table_name} ({columns_str}) VALUES ({placeholders})"

            values = []
            for col in columns:
                val = existing_data.get(col)
                if isinstance(val, (dict, list)):
                    values.append(json.dumps(val, ensure_ascii=False))
                else:
                    values.append(val)

            await conn.execute(sql, values)
            await conn.commit()

            # 4. 驗證
            cursor = await conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name} WHERE user_id = ?", (user_id,)
            )
            count = (await cursor.fetchone())[0]
            return count > 0

    async def get_user_field(self, user_id: Union[int, str], field: str, default: Any = None) -> Any:
        user = await self.get_user(user_id)
        return user.get(field, default) if user else default

    async def set_user_field(self, user_id: Union[int, str], field: str, value: Any) -> bool:
        return await self.set_user(user_id, {field: value})

    async def update_user_field(
        self, user_id: Union[int, str], field: str, amount: Union[int, float]
    ) -> bool:
        current = await self.get_user_field(user_id, field, 0)
        # 型別轉換邏輯同步版
        if isinstance(current, str):
            try:
                current = float(current) if "." in current else int(current)
            except ValueError:
                return False
        if not isinstance(current, (int, float)):
            return False
        return await self.set_user_field(user_id, field, current + amount)

    async def ensure_columns(self, headers: List[str]):
        """同步 SHEET 表頭時呼叫"""
        await self._ensure_initialized()
        async with self._pool.connection() as conn:
            await self._ensure_columns(conn, headers)

    async def _ensure_columns(self, conn: aiosqlite.Connection, headers: List[str]):
        if not self._columns_cache_valid:
            await self._refresh_columns_cache(conn)
        existing = self._columns_cache

        added = 0
        for header in headers:
            if header in existing or header.startswith("_"):
                continue
            col_type = self._infer_sql_type(header)
            try:
                await conn.execute(f'ALTER TABLE {self.table_name} ADD COLUMN "{header}" {col_type}')
                added += 1
            except aiosqlite.OperationalError:
                pass

        if added:
            await conn.execute(
                f"UPDATE {self.table_name} SET _updated_at = CURRENT_TIMESTAMP"
            )
            await conn.commit()
            self._columns_cache_valid = False  # 強制下次刷新

    def _infer_sql_type(self, header: str) -> str:
        """沿用同步版邏輯"""
        h = header.lower()
        if any(w in h for w in ["id", "level", "xp", "coin", "kkcoin", "hp", "stamina", "streak", "count", "num", "amount", "is_", "unlocked", "enabled"]):
            return "INTEGER DEFAULT 0"
        if any(w in h for w in ["date", "time", "timestamp", "at"]):
            return "TEXT DEFAULT NULL"
        if any(w in h for w in ["config", "setting", "data", "json", "info", "inventory"]):
            return "TEXT DEFAULT '{}'"
        return "TEXT DEFAULT ''"

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        data = dict(row)
        for k, v in data.items():
            if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
                try:
                    data[k] = json.loads(v)
                except:
                    pass
        return data

    # ========== 批量/統計操作 ==========

    async def get_user_by_field(self, field: str, value: Any) -> Optional[Dict[str, Any]]:
        await self._ensure_initialized()
        if not self._columns_cache_valid:
            async with self._pool.connection() as conn:
                await self._refresh_columns_cache(conn)
        if field not in self._columns_cache:
            return None
        async with self._pool.connection() as conn:
            cursor = await conn.execute(f'SELECT * FROM {self.table_name} WHERE "{field}" = ?', (value,))
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def get_all_users(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        await self._ensure_initialized()
        async with self._pool.connection() as conn:
            sql = f"SELECT * FROM {self.table_name}"
            if limit:
                sql += f" LIMIT {limit}"
            cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def delete_user(self, user_id: Union[int, str]) -> bool:
        await self._ensure_initialized()
        user_id = int(user_id)
        async with self._pool.connection() as conn:
            await conn.execute(
                f"DELETE FROM {self.table_name} WHERE user_id = ?", (user_id,)
            )
            await conn.commit()
            return True

    async def get_stats(self) -> Dict[str, Any]:
        await self._ensure_initialized()
        async with self._pool.connection() as conn:
            cursor = await conn.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            total_users = (await cursor.fetchone())[0]

            cursor = await conn.execute(f"PRAGMA table_info({self.table_name})")
            columns = {row[1] async for row in cursor}

            stats = {
                "total_users": total_users,
                "total_columns": len(columns),
                "columns": sorted(list(columns)),
            }

            for field in ["level", "xp", "kkcoin", "hp", "stamina"]:
                if field in columns:
                    try:
                        cursor = await conn.execute(
                            f'AVG("{field}"), MAX("{field}"), MIN("{field}") FROM {self.table_name}'
                        )
                        avg, max_val, min_val = await cursor.fetchone()
                        stats[f"{field}_avg"] = round(avg, 2) if avg else 0
                        stats[f"{field}_max"] = max_val
                        stats[f"{field}_min"] = min_val
                    except:
                        pass

            return stats


# 全域單例
_async_db_instance: Optional[AsyncSheetDrivenDB] = None

async def get_async_db(db_path: str = "user_data.db") -> AsyncSheetDrivenDB:
    global _async_db_instance
    if _async_db_instance is None:
        _async_db_instance = AsyncSheetDrivenDB(db_path)
    return _async_db_instance
