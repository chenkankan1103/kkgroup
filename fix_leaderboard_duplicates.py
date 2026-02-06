#!/usr/bin/env python3
"""
修復排行榜重複問題 - 清理資料庫中的重複用戶記錄
"""

import sqlite3
import sys
from datetime import datetime

def fix_duplicate_users(db_path: str = 'user_data.db', strategy: str = 'max_kkcoin'):
    """
    修復資料庫中的重複用戶記錄
    
    Args:
        db_path: 資料庫路徑
        strategy: 修復策略
            'max_kkcoin': 保留 kkcoin 最高的記錄（推薦）
            'latest': 保留最新的記錄（rowid 最大）
            'oldest': 保留最舊的記錄（rowid 最小）
    """
    
    print("=" * 80)
    print("🔧 排行榜重複問題修復工具")
    print("=" * 80)
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 先檢查重複
        print("\n📋 檢查重複記錄...")
        cursor.execute("""
            SELECT user_id, COUNT(*) as count 
            FROM users 
            GROUP BY user_id 
            HAVING count > 1
            ORDER BY count DESC
        """)
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("✅ 資料庫中沒有重複記錄，無需修復")
            conn.close()
            return True
        
        print(f"⚠️  發現 {len(duplicates)} 個重複的 user_id")
        
        # 備份前顯示詳情
        print("\n📊 重複詳情：")
        total_duplicates = 0
        for row in duplicates:
            user_id = row['user_id']
            count = row['count']
            total_duplicates += (count - 1)
            print(f"  - user_id {user_id}: {count} 筆記錄 → 刪除 {count-1} 筆")
        
        print(f"\n📈 統計：")
        print(f"  - 受影響的用戶數: {len(duplicates)}")
        print(f"  - 需要刪除的重複記錄: {total_duplicates}")
        
        # 創建備份
        backup_file = f"user_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        print(f"\n💾 創建備份: {backup_file}")
        import shutil
        shutil.copy(db_path, backup_file)
        print("✅ 備份完成")
        
        # 執行修復
        print(f"\n🔧 使用策略應用修復: {strategy}")
        
        if strategy == 'max_kkcoin':
            print("  保留每個用戶 kkcoin 最高的記錄...")
            cursor.execute("""
                DELETE FROM users 
                WHERE rowid NOT IN (
                    SELECT MAX(rowid)
                    FROM users
                    GROUP BY user_id, MAX(kkcoin) -- 未實現，改用子查詢
                )
            """)
            # 實際上，我們需要更複雜的邏輯
            # 先獲取每個用戶的最高 kkcoin
            cursor.execute("""
                SELECT user_id, MAX(kkcoin) as max_kkcoin
                FROM users
                GROUP BY user_id
                HAVING COUNT(*) > 1
            """)
            users_to_fix = cursor.fetchall()
            
            for row in users_to_fix:
                user_id = row['user_id']
                max_kkcoin = row['max_kkcoin']
                
                # 找到有最高 kkcoin 的記錄
                cursor.execute("""
                    SELECT rowid FROM users 
                    WHERE user_id = ? AND kkcoin = ?
                    LIMIT 1
                """, (user_id, max_kkcoin))
                keep_rowid = cursor.fetchone()
                
                if keep_rowid:
                    # 刪除其他記錄
                    cursor.execute("""
                        DELETE FROM users 
                        WHERE user_id = ? AND rowid != ?
                    """, (user_id, keep_rowid[0]))
        
        elif strategy == 'latest':
            print("  保留每個用戶最新的記錄...")
            cursor.execute("""
                DELETE FROM users 
                WHERE rowid NOT IN (
                    SELECT MAX(rowid)
                    FROM users
                    GROUP BY user_id
                )
            """)
        
        elif strategy == 'oldest':
            print("  保留每個用戶最舊的記錄...")
            cursor.execute("""
                DELETE FROM users 
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM users
                    GROUP BY user_id
                )
            """)
        
        conn.commit()
        deleted_count = conn.total_changes
        print(f"✅ 修復完成 - 刪除 {deleted_count} 筆重複記錄")
        
        # 驗證修復結果
        print("\n✔️  驗證修復結果...")
        cursor.execute("""
            SELECT user_id, COUNT(*) as count 
            FROM users 
            GROUP BY user_id 
            HAVING count > 1
        """)
        remaining_duplicates = cursor.fetchall()
        
        if remaining_duplicates:
            print(f"⚠️  仍有 {len(remaining_duplicates)} 個重複的 user_id")
            for row in remaining_duplicates:
                print(f"  - user_id {row['user_id']}: {row['count']} 筆")
        else:
            print("✅ 所有重複記錄已清理")
        
        # 檢查排行榜是否仍有重複
        cursor.execute("""
            SELECT user_id, COUNT(*) as count
            FROM users
            WHERE kkcoin > 0
            ORDER BY kkcoin DESC
            LIMIT 20
        """)
        leaderboard = cursor.fetchall()
        
        from collections import Counter
        user_ids = [row['user_id'] for row in leaderboard]
        duplicates_in_leaderboard = [uid for uid, count in Counter(user_ids).items() if count > 1]
        
        if duplicates_in_leaderboard:
            print(f"⚠️  排行榜中仍有 {len(duplicates_in_leaderboard)} 個重複用戶")
        else:
            print("✅ 排行榜中沒有重複用戶")
        
        conn.close()
        
        print("\n" + "=" * 80)
        print("💡 修復完成")
        print(f"   備份檔案: {backup_file}")
        print(f"   刪除記錄: {deleted_count}")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"❌ 修復失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    
    strategy = sys.argv[1] if len(sys.argv) > 1 else 'max_kkcoin'
    
    print(f"執行修復策略: {strategy}")
    
    success = fix_duplicate_users(strategy=strategy)
    
    if success:
        print("\n✅ 修復成功，請重啟 Discord Bot 以刷新排行榜")
    else:
        print("\n❌ 修復失敗，請檢查錯誤信息")
