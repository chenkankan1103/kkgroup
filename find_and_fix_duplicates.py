#!/usr/bin/env python3
"""
找出並修復 ID 偏差的帳號（重複昵稱）
"""

import sqlite3
import shutil
from datetime import datetime

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/tmp/kkgroup_backups'

def find_duplicates():
    """找出所有重複昵稱"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT nickname FROM users WHERE nickname IS NOT NULL AND nickname != '' "
        "GROUP BY nickname HAVING COUNT(*) > 1"
    )
    nicks = [row[0] for row in cursor.fetchall()]
    
    duplicates = {}
    for nick in nicks:
        cursor = conn.execute(
            "SELECT user_id FROM users WHERE nickname = ? ORDER BY user_id",
            (nick,)
        )
        ids = [row[0] for row in cursor.fetchall()]
        duplicates[nick] = ids
    
    conn.close()
    return duplicates

def identify_ghost_ids(duplicates):
    """
    識別哪個是幽靈帳號
    規則: ID 末位相差 37 的，較大的是幽靈帳號（精度損失版本）
    """
    ghost_to_delete = []
    
    for nick, ids in duplicates.items():
        if len(ids) != 2:
            continue
        
        id1, id2 = sorted(ids)
        diff = id2 - id1
        
        # 精度損失的特徵：差值為 37（或接近）
        if diff > 0 and diff <= 100:
            print(f"  {nick}: ID差={diff}")
            # 較大的 ID 是精度損失版本，應該刪除
            ghost_to_delete.append((id2, nick))
    
    return ghost_to_delete

def main():
    print("=" * 80)
    print("🔧 ID 偏差修復工具")
    print("=" * 80)
    print()
    
    # Step 1: 備份
    print("📦 備份資料庫...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{BACKUP_DIR}/user_data_backup_{timestamp}.db'
    shutil.copy2(DB_PATH, backup_path)
    print(f"   ✅ 備份完成: {backup_path}")
    print()
    
    # Step 2: 找出重複
    print("🔍 掃描重複昵稱...")
    duplicates = find_duplicates()
    
    if not duplicates:
        print("   ✅ 沒有重複昵稱，資料庫狀態正常")
        return
    
    print(f"   ⚠️  發現 {len(duplicates)} 個重複昵稱:")
    for nick, ids in duplicates.items():
        print(f"      {nick}: {ids}")
    print()
    
    # Step 3: 識別幽靈帳號
    print("👻 識別幽靈帳號...")
    ghosts = identify_ghost_ids(duplicates)
    
    if not ghosts:
        print("   ℹ️  無法自動識別幽靈帳號")
        print("   手動刪除方案: 保留最小 user_id，刪除較大的 user_id")
        
        # 自動刪除較大的 ID
        conn = sqlite3.connect(DB_PATH)
        deleted_count = 0
        
        for nick, ids in duplicates.items():
            if len(ids) == 2:
                id_to_delete = max(ids)
                print(f"   🗑️  {nick}: 刪除 {id_to_delete}，保留 {min(ids)}")
                cursor = conn.execute("DELETE FROM users WHERE user_id = ?", (id_to_delete,))
                deleted_count += cursor.rowcount
        
        conn.commit()
        conn.close()
        print(f"   ✅ 已刪除 {deleted_count} 個幽靈帳號")
    else:
        print(f"   👻 發現 {len(ghosts)} 個幽靈帳號:")
        
        # 刪除幽靈帳號
        conn = sqlite3.connect(DB_PATH)
        for ghost_id, ghost_nick in ghosts:
            print(f"      🗑️  {ghost_nick}: 刪除 ID {ghost_id}")
            cursor = conn.execute("DELETE FROM users WHERE user_id = ?", (ghost_id,))
        
        conn.commit()
        conn.close()
        print(f"   ✅ 已刪除 {len(ghosts)} 個幽靈帳號")
    
    print()
    
    # Step 4: 驗證
    print("✅ 驗證結果...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT nickname FROM users WHERE nickname IS NOT NULL AND nickname != '' "
        "GROUP BY nickname HAVING COUNT(*) > 1"
    )
    remaining = [row[0] for row in cursor.fetchall()]
    
    if remaining:
        print(f"   ⚠️  仍有 {len(remaining)} 個重複昵稱: {remaining}")
    else:
        print("   ✅ 所有重複昵稱已修復")
    
    # 統計
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    cursor = conn.execute("SELECT COUNT(*) FROM users WHERE nickname IS NOT NULL AND nickname != ''")
    real = cursor.fetchone()[0]
    
    print()
    print("📊 資料庫統計:")
    print(f"   總玩家: {total} 人")
    print(f"   實名玩家: {real} 人")
    
    conn.close()
    
    print()
    print("✅ 修復完成!")

if __name__ == '__main__':
    main()
