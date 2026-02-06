#!/usr/bin/env python3
"""
ID 偏差修復工具
找出並刪除重複昵稱中的幽靈帳號（較大的 ID）
"""

import sqlite3
import shutil
import os
from datetime import datetime

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/tmp/kkgroup_backups'

def main():
    print('=' * 80)
    print('🔧 ID 偏差修復工具')
    print('=' * 80)
    print()

    # 備份
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bp = os.path.join(BACKUP_DIR, f'backup_{ts}.db')
    shutil.copy2(DB_PATH, bp)
    print(f'📦 備份完成: {bp}')
    print()

    # 連接資料庫
    conn = sqlite3.connect(DB_PATH)

    # 查詢重複昵稱
    print('🔍 掃描重複昵稱...')
    cursor = conn.execute(
        'SELECT nickname FROM users WHERE nickname IS NOT NULL AND nickname != "" '
        'GROUP BY nickname HAVING COUNT(*) > 1'
    )
    nicks = [row[0] for row in cursor.fetchall()]

    if not nicks:
        print('✅ 沒有重複昵稱，資料庫狀態正常')
        conn.close()
        return

    print(f'⚠️  發現 {len(nicks)} 個重複昵稱')
    print()

    # 刪除重複
    print('🗑️  刪除幽靈帳號...')
    total_deleted = 0

    for nick in nicks:
        cursor = conn.execute(
            'SELECT user_id FROM users WHERE nickname = ? ORDER BY user_id',
            (nick,)
        )
        ids = [row[0] for row in cursor.fetchall()]

        if len(ids) > 1:
            keeper_id = min(ids)
            for remove_id in ids[1:]:
                cursor = conn.execute(
                    'DELETE FROM users WHERE user_id = ?',
                    (remove_id,)
                )
                deleted = cursor.rowcount
                total_deleted += deleted
                print(f'   ❌ {nick}: 刪除 {remove_id}，保留 {keeper_id}')

    conn.commit()
    print()
    print(f'✅ 共刪除 {total_deleted} 個幽靈帳號')
    print()

    # 驗證
    cursor = conn.execute('SELECT COUNT(*) FROM users')
    total = cursor.fetchone()[0]
    cursor = conn.execute('SELECT nickname FROM users WHERE nickname IS NOT NULL AND nickname != "" GROUP BY nickname HAVING COUNT(*) > 1')
    remaining = [row[0] for row in cursor.fetchall()]

    print('📊 驗證結果:')
    print(f'   總玩家數: {total}')
    if remaining:
        print(f'   ⚠️  仍有重複: {remaining}')
    else:
        print('   ✅ 所有重複已修復')

    conn.close()
    print()
    print('✅ 修復工作完成！')

if __name__ == '__main__':
    main()
