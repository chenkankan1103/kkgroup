"""
KK群組 - Agent 任務持久化存儲 (SQLite)
========================================
提供任務狀態、結果、進度的持久化存儲。
支援：建立、更新、查詢、列表、清理。
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# 資料庫路徑
DB_PATH = Path(
    os.getenv("AGENT_TASK_DB", "/home/e193752468/kkgroup/shared/db/data/agent_tasks.db")
).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class SQLiteTaskStore:
    """SQLite 任務存儲實作"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._initialized = False

    async def _ensure_init(self):
        """延遲初始化資料庫結構"""
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,           -- JSON
                    result TEXT,                     -- JSON
                    error TEXT,
                    progress TEXT,                   -- 累積進度文字
                    user_id INTEGER,
                    channel_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks(status)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created
                ON tasks(created_at DESC)
            """)
            await db.commit()
        self._initialized = True

    async def create(self, task_id: str, task_type: str, payload: dict) -> None:
        """建立新任務"""
        await self._ensure_init()
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO tasks (task_id, task_type, status, payload, user_id, channel_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    task_type,
                    "pending",
                    json.dumps(payload, ensure_ascii=False),
                    payload.get("user_id"),
                    payload.get("channel_id"),
                    now,
                    now,
                ),
            )
            await db.commit()

    async def update(self, task_id: str, **fields) -> None:
        """更新任務欄位（動態）"""
        await self._ensure_init()
        if not fields:
            return

        # 允許更新的欄位
        allowed = {
            "status",
            "result",
            "error",
            "progress",
            "started_at",
            "completed_at",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return

        updates["updated_at"] = datetime.utcnow().isoformat()

        # JSON 欄位序列化
        for k in ("result", "payload"):
            if k in updates and not isinstance(updates[k], str):
                updates[k] = json.dumps(updates[k], ensure_ascii=False)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values)
            await db.commit()

    async def get(self, task_id: str) -> dict | None:
        """查詢單一任務"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return self._row_to_dict(row)

    async def list(self, status: str | None = None, limit: int = 50) -> list[dict]:
        """列出任務（可按狀態過濾）"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                async with db.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
                ) as cur:
                    rows = await cur.fetchall()
            return [self._row_to_dict(r) for r in rows]

    async def delete_old(self, days: int = 30) -> int:
        """清理舊任務"""
        await self._ensure_init()
        cutoff = datetime.utcnow().replace(day=datetime.utcnow().day - days).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM tasks WHERE created_at < ? AND status IN (?, ?, ?)",
                (cutoff, "completed", "failed", "cancelled"),
            )
            await db.commit()
            return cur.rowcount

    async def get_stats(self) -> dict:
        """取得統計資訊"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db, db.execute("""
                SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status
            """) as cur:
            rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows}

    def _row_to_dict(self, row: aiosqlite.Row) -> dict:
        d = dict(row)
        # 反序列化 JSON 欄位
        for k in ("payload", "result"):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except json.JSONDecodeError:
                    pass
        return d


# 全域實例（單例模式）
_task_store: SQLiteTaskStore | None = None


def get_task_store() -> SQLiteTaskStore:
    global _task_store
    if _task_store is None:
        _task_store = SQLiteTaskStore()
    return _task_store


# 便利函數
async def create_task(task_id: str, task_type: str, payload: dict):
    await get_task_store().create(task_id, task_type, payload)


async def update_task(task_id: str, **fields):
    await get_task_store().update(task_id, **fields)


async def get_task(task_id: str) -> dict | None:
    return await get_task_store().get(task_id)


async def list_tasks(status: str | None = None, limit: int = 50) -> list[dict]:
    return await get_task_store().list(status, limit)


async def delete_old_tasks(days: int = 30) -> int:
    return await get_task_store().delete_old(days)


async def get_task_stats() -> dict:
    return await get_task_store().get_stats()
