#!/usr/bin/env python3
"""
診斷排行榜重複問題 - 檢查資料庫中的重複用戶 ID 和排行榜數據
"""

import sqlite3
from collections import Counter
from typing import List, Dict, Any, Tuple

def diagnose_database(db_path: str = 'user_data.db'):
    """診斷資料庫中的重複問題"""
    
    print("=" * 80)
    print("🔍 排行榜重複問題診斷")
    print("=" * 80)
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1️⃣ 檢查表結構
        print("\n📋 資料庫表結構：")
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")
        
        # 2️⃣ 檢查總記錄數
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        print(f"\n📊 總用戶記錄數：{total_users}")
        
        # 3️⃣ 檢查重複的 user_id
        print("\n🔎 檢查重複的 user_id：")
        cursor.execute("""
            SELECT user_id, COUNT(*) as count 
            FROM users 
            GROUP BY user_id 
            HAVING count > 1
            ORDER BY count DESC
        """)
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"  ⚠️ 發現 {len(duplicates)} 個重複的 user_id：")
            for row in duplicates:
                user_id = row['user_id']
                count = row['count']
                print(f"    - user_id {user_id}: {count} 筆記錄")
                
                # 顯示該 user_id 的所有記錄
                cursor.execute(f"""
                    SELECT user_id, nickname, kkcoin, level, xp 
                    FROM users 
                    WHERE user_id = ?
                """, (user_id,))
                records = cursor.fetchall()
                for i, rec in enumerate(records, 1):
                    print(f"      記錄 {i}: nickname={rec['nickname']}, kkcoin={rec['kkcoin']}, level={rec['level']}, xp={rec['xp']}")
        else:
            print("  ✅ 沒有重複的 user_id")
        
        # 4️⃣ 獲取排行榜前 20 名
        print("\n🏆 排行榜前 20 名（原始數據）：")
        print("-" * 80)
        
        cursor.execute("""
            SELECT user_id, nickname, kkcoin, level, xp
            FROM users
            WHERE kkcoin > 0
            ORDER BY kkcoin DESC
            LIMIT 20
        """)
        leaderboard = cursor.fetchall()
        
        user_ids_in_leaderboard = []
        for i, row in enumerate(leaderboard, 1):
            user_id = row['user_id']
            nickname = row['nickname'] or f"User {user_id}"
            kkcoin = row['kkcoin']
            user_ids_in_leaderboard.append(user_id)
            print(f"{i:2d}. ID={user_id:18d} | {nickname:15s} | {kkcoin:6d} coins")
        
        # 5️⃣ 檢查排行榜中是否有重複的 user_id
        print("\n🔎 檢查排行榜前 20 名中的重複：")
        user_id_counts = Counter(user_ids_in_leaderboard)
        duplicates_in_leaderboard = {uid: count for uid, count in user_id_counts.items() if count > 1}
        
        if duplicates_in_leaderboard:
            print(f"  ⚠️ 發現 {len(duplicates_in_leaderboard)} 個重複出現在排行榜中：")
            for user_id, count in duplicates_in_leaderboard.items():
                print(f"    - user_id {user_id}: 出現 {count} 次")
        else:
            print("  ✅ 排行榜中沒有重複用戶")
        
        # 6️⃣ 檢查排行榜邏輯的詳細分析
        print("\n📈 排行榜邏輯分析：")
        cursor.execute("""
            SELECT user_id, COUNT(*) as record_count, 
                   MAX(kkcoin) as max_kkcoin,
                   SUM(kkcoin) as total_kkcoin
            FROM users
            GROUP BY user_id
            HAVING record_count > 1
            ORDER BY record_count DESC
        """)
        multi_record_users = cursor.fetchall()
        
        if multi_record_users:
            print(f"  ⚠️ {len(multi_record_users)} 個用戶有多筆記錄：")
            for row in multi_record_users:
                user_id = row['user_id']
                count = row['record_count']
                max_kkcoin = row['max_kkcoin']
                total_kkcoin = row['total_kkcoin']
                print(f"    - user_id {user_id}: {count} 筆 | 最高 kkcoin={max_kkcoin} | 總計={total_kkcoin}")
        
        # 7️⃣ 建議修復方案
        print("\n💡 修復建議：")
        if duplicates:
            print("  1. ❌ 資料庫中確實存在重複記錄")
            print("  2. 📝 需要清理重複記錄 - 保留 kkcoin 最高的記錄")
            print("  3. 🔧 可使用以下 SQL 進行修復：")
            print("""
                -- 方案 A: 保留 ROWID 最小的記錄（最舊的）
                DELETE FROM users 
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) 
                    FROM users 
                    GROUP BY user_id
                );
                
                -- 方案 B: 保留 kkcoin 最高的記錄（推薦）
                WITH keep_records AS (
                    SELECT user_id, MAX(rowid) as keep_rowid
                    FROM users
                    GROUP BY user_id
                )
                DELETE FROM users
                WHERE rowid NOT IN (SELECT keep_rowid FROM keep_records);
            """)
        else:
            print("  ✅ 資料庫中沒有重複記錄 - 問題可能在應用邏輯中")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 診斷失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose_database()
    
    print("\n" + "=" * 80)
    print("💡 執行說明：")
    print("  - 在 GCP 服務器上執行此腳本")
    print("  - 確保 user_data.db 文件存在")
    print("  - 根據診斷結果決定是否需要清理重複記錄")
    print("=" * 80)
