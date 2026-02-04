#!/usr/bin/env python3
"""
清理虛擬帳號腳本
移除數據庫中所有 nickname 為 Unknown_XXXX 的虛擬帳號
"""

import sqlite3
import sys
from datetime import datetime

def cleanup_virtual_accounts(db_path='user_data.db', skip_confirm=False):
    """清理虛擬帳號"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("="*60)
    print("🧹 虛擬帳號清理工具")
    print("="*60)
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"資料庫: {db_path}")
    print("="*60)
    
    try:
        # 1. 查詢虛擬帳號
        cursor.execute("""
            SELECT user_id, nickname, level, kkcoin 
            FROM users 
            WHERE nickname LIKE 'Unknown_%' 
            ORDER BY user_id
        """)
        virtual_accounts = cursor.fetchall()
        
        print(f"\n📊 檢測到 {len(virtual_accounts)} 個虛擬帳號：\n")
        
        total_kkcoin = 0
        for i, (user_id, nickname, level, kkcoin) in enumerate(virtual_accounts, 1):
            print(f"{i:3d}. user_id={user_id}, nickname={nickname}, level={level}, kkcoin={kkcoin}")
            total_kkcoin += kkcoin
        
        print(f"\n💰 虛擬帳號持有的 KKCOIN 總計: {total_kkcoin}")
        
        if virtual_accounts:
            # 2. 確認刪除
            if not skip_confirm:
                response = input(f"\n🚨 確認刪除 {len(virtual_accounts)} 個虛擬帳號？(yes/no): ").strip().lower()
                if response != 'yes':
                    print("❌ 取消操作")
                    return 0
            
            # 3. 執行刪除
            cursor.execute("""
                DELETE FROM users 
                WHERE nickname LIKE 'Unknown_%'
            """)
            deleted = cursor.rowcount
            conn.commit()
            
            print(f"\n✅ 已刪除 {deleted} 個虛擬帳號")
            
            # 4. 驗證
            cursor.execute("SELECT COUNT(*) FROM users WHERE nickname LIKE 'Unknown_%'")
            remaining = cursor.fetchone()[0]
            
            if remaining == 0:
                print("✅ 驗證完成：所有虛擬帳號已清理")
            else:
                print(f"⚠️ 警告：仍有 {remaining} 個虛擬帳號未清理")
        else:
            print("\n✅ 沒有虛擬帳號需要清理")
            return 0
        
        # 5. 顯示統計
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE nickname NOT LIKE 'Unknown_%'")
        real_users = cursor.fetchone()[0]
        
        print(f"\n📈 資料庫統計:")
        print(f"   - 真實玩家: {real_users}")
        print(f"   - 虛擬帳號: {total_users - real_users}")
        print(f"   - 總計: {total_users}")
        
        return deleted
    
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
        return 0
    
    finally:
        conn.close()
    
    print("="*60)

if __name__ == '__main__':
    # 使用 --force 參數跳過確認直接刪除
    skip_confirm = '--force' in sys.argv
    cleanup_virtual_accounts(skip_confirm=skip_confirm)
