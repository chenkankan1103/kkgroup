"""
DatabaseManager 統一連線池測試

測試：
1. 單例模式正確性
2. 多連線並發存取
3. 啟動 PRAGMA 設定
4. 完整性檢查
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, '.')

from shared.db.async_db import AsyncSheetDrivenDB
from shared.db.manager import DatabaseManager, db_connection, get_db_pool


async def test_singleton():
    """測試單例模式"""
    print("🧪 測試單例模式...")
    db_path = tempfile.mktemp(suffix='.db')

    pool1 = await DatabaseManager.initialize(db_path, pool_size=4)
    pool2 = await DatabaseManager.get_pool_or_init(db_path)

    assert pool1 is pool2, "單例失敗：應返回同一連線池實例"
    print("  ✅ 單例模式正確")

    await DatabaseManager.close()
    os.unlink(db_path)


async def test_concurrent_access():
    """測試多連線並發存取（順序執行避免 Windows aiosqlite 問題）"""
    print("🧪 測試並發存取（順序模式）...")
    db_path = tempfile.mktemp(suffix='.db')

    await DatabaseManager.initialize(db_path, pool_size=8)

    # 建立測試資料表
    from shared.db.manager import execute_with_retry
    await execute_with_retry("""
        CREATE TABLE IF NOT EXISTS test_users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            value INTEGER DEFAULT 0
        )
    """)

    # 順序寫入測試
    for uid in range(3):
        for i in range(5):
            await execute_with_retry("""
                INSERT OR REPLACE INTO test_users (user_id, name, value)
                VALUES (?, ?, ?)
            """, (uid, f"user_{uid}", i))
    print("  ✅ 寫入測試通過")

    # 順序讀取測試
    for uid in range(3):
        cursor = await execute_with_retry(
            "SELECT value FROM test_users WHERE user_id = ?", (uid,)
        )
        row = await cursor.fetchone()
        assert row is not None, f"用戶 {uid} 應存在"
    print("  ✅ 讀取測試通過")

    # 驗證資料
    cursor = await execute_with_retry("SELECT COUNT(*) FROM test_users")
    count = (await cursor.fetchone())[0]
    assert count == 3, f"預期 3 筆資料，實際 {count}"
    print("  ✅ 資料完整性驗證通過")

    await DatabaseManager.close()
    os.unlink(db_path)


async def test_startup_pragmas():
    """測試啟動 PRAGMA 設定"""
    print("🧪 測試啟動 PRAGMA...")
    db_path = tempfile.mktemp(suffix='.db')

    await DatabaseManager.initialize(db_path, pool_size=4)
    await DatabaseManager.execute_startup_pragmas()

    async with db_connection() as conn:
        cursor = await conn.execute("PRAGMA wal_autocheckpoint")
        val = (await cursor.fetchone())[0]
        assert val == 100, f"wal_autocheckpoint 應為 100，實際 {val}"
        print(f"  ✅ wal_autocheckpoint = {val}")

        cursor = await conn.execute("PRAGMA journal_mode")
        mode = (await cursor.fetchone())[0]
        assert mode == "wal", f"journal_mode 應為 wal，實際 {mode}"
        print(f"  ✅ journal_mode = {mode}")

        cursor = await conn.execute("PRAGMA busy_timeout")
        timeout = (await cursor.fetchone())[0]
        assert timeout == 30000, f"busy_timeout 應為 30000，實際 {timeout}"
        print(f"  ✅ busy_timeout = {timeout}")

    await DatabaseManager.close()
    os.unlink(db_path)


async def test_integrity_check():
    """測試完整性檢查"""
    print("🧪 測試完整性檢查...")
    db_path = tempfile.mktemp(suffix='.db')

    await DatabaseManager.initialize(db_path, pool_size=4)

    is_ok, msg = await DatabaseManager.integrity_check()
    assert is_ok, f"新資料庫應通過完整性檢查: {msg}"
    print(f"  ✅ quick_check: {msg}")

    is_ok, msg = await DatabaseManager.full_integrity_check()
    assert is_ok, f"新資料庫應通過完整完整性檢查: {msg}"
    print(f"  ✅ integrity_check: {msg}")

    await DatabaseManager.close()
    os.unlink(db_path)


async def test_async_sheet_driven_db_integration():
    """測試 AsyncSheetDrivenDB 整合"""
    print("🧪 測試 AsyncSheetDrivenDB 整合...")
    db_path = tempfile.mktemp(suffix='.db')

    await DatabaseManager.initialize(db_path, pool_size=4)

    db = AsyncSheetDrivenDB(db_path)
    db._pool = await DatabaseManager.get_pool_or_init()

    # 測試用戶操作
    user_id = 123456
    await db.set_user(user_id, {"name": "Test User", "level": 5, "kkcoin": 1000})

    user = await db.get_user(user_id)
    assert user is not None, "用戶應存在"
    assert user["name"] == "Test User"
    assert user["level"] == 5
    assert user["kkcoin"] == 1000
    print("  ✅ set_user / get_user 正常")

    # 測試欄位更新
    await db.update_user_field(user_id, "kkcoin", 500)
    user = await db.get_user(user_id)
    assert user["kkcoin"] == 1500, f"kkcoin 應為 1500，實際 {user['kkcoin']}"
    print("  ✅ update_user_field 正常")

    # 測試欄位讀取
    level = await db.get_user_field(user_id, "level", 0)
    assert level == 5
    print("  ✅ get_user_field 正常")

    await DatabaseManager.close()
    os.unlink(db_path)


async def main():
    print("=" * 60)
    print("DatabaseManager 測試套件")
    print("=" * 60)

    await test_singleton()
    await test_concurrent_access()
    await test_startup_pragmas()
    await test_integrity_check()
    await test_async_sheet_driven_db_integration()

    print("=" * 60)
    print("🎉 所有測試通過！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())