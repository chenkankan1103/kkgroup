#!/usr/bin/env python3
"""
GCP 資料庫幽靈帳號清除腳本 (2026年2月6日)

目的：刪除精度損失產生的幽靈帳號

待刪除帳號:
- 5 個 NULL nickname 幽靈帳號: 535810695011368972, 564156950913351685, 740803743821594654, 1209509919699505184
- 1 個凱文重複 (精度損失): 776464975551660160

執行流程:
1. 備份資料庫
2. 查詢待刪除帳號詳情
3. 刪除幽靈帳號
4. 驗證刪除結果
5. 列出剩餘玩家
"""

import sqlite3
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# 設定區
# ============================================================

DB_PATH = '/home/e193752468/kkgroup/user_data.db'
BACKUP_DIR = '/tmp/kkgroup_backups'

# 待刪除的 user_id (6 個幽靈帳號)
GHOST_USER_IDS = [
    535810695011368972,      # NULL nickname
    564156950913351685,      # NULL nickname
    740803743821594654,      # NULL nickname
    1209509919699505184,     # NULL nickname
    776464975551660160,      # 凱文重複 (精度損失版本)
]

# ============================================================
# 帝陷函數
# ============================================================

def backup_database():
    """備份資料庫"""
    print("📦 開始備份資料庫...")
    
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        print(f"   ✓ 創建備份目錄: {BACKUP_DIR}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"user_data_backup_{timestamp}.db")
    
    try:
        shutil.copy2(DB_PATH, backup_path)
        print(f"   ✅ 備份完成: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"   ❌ 備份失敗: {str(e)}")
        sys.exit(1)

def connect_db():
    """連接資料庫"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        print(f"✅ 資料庫連接成功: {DB_PATH}")
        return conn
    except Exception as e:
        print(f"❌ 資料庫連接失敗: {str(e)}")
        sys.exit(1)

def get_ghost_details(conn):
    """查詢待刪除帳號的詳情"""
    print("\n📋 待刪除帳號詳情:")
    print("-" * 80)
    
    placeholders = ','.join(['?' * len(GHOST_USER_IDS)])
    query = f"""
    SELECT user_id, nickname, discord_username, hp, stamina, xp, level
    FROM users
    WHERE user_id IN ({placeholders})
    ORDER BY user_id
    """
    
    try:
        cursor = conn.execute(query, GHOST_USER_IDS)
        rows = cursor.fetchall()
        
        if not rows:
            print("   ⚠️  找不到待刪除的帳號")
            return False
        
        for row in rows:
            nickname = row['nickname'] if row['nickname'] else '[NULL]'
            username = row['discord_username'] if row['discord_username'] else '[未設定]'
            print(f"   ❌ user_id={row['user_id']:>20} | nickname={nickname:>10} | username={username}")
        
        print("-" * 80)
        print(f"   📊 共 {len(rows)} 個幽靈帳號待刪除")
        return True
    
    except Exception as e:
        print(f"   ❌ 查詢失敗: {str(e)}")
        return False

def delete_ghosts(conn):
    """刪除幽靈帳號"""
    print("\n🗑️  刪除幽靈帳號...")
    print("-" * 80)
    
    # 確認刪除
    print(f"\n⚠️  確認刪除 {len(GHOST_USER_IDS)} 個幽靈帳號?")
    print("   待刪除 user_id:", GHOST_USER_IDS)
    user_input = input("\n   請輸入 'YES' 確認刪除: ").strip().upper()
    
    if user_input != 'YES':
        print("   ❌ 取消刪除")
        return False
    
    try:
        placeholders = ','.join(['?' * len(GHOST_USER_IDS)])
        delete_query = f"DELETE FROM users WHERE user_id IN ({placeholders})"
        
        cursor = conn.execute(delete_query, GHOST_USER_IDS)
        deleted_count = cursor.rowcount
        conn.commit()
        
        print(f"\n   ✅ 成功刪除 {deleted_count} 個幽靈帳號")
        return True
    
    except Exception as e:
        print(f"   ❌ 刪除失敗: {str(e)}")
        conn.rollback()
        return False

def verify_deletion(conn):
    """驗證刪除結果"""
    print("\n✅ 驗證刪除結果:")
    print("-" * 80)
    
    # 1. 檢查是否還有幽靈帳號
    placeholders = ','.join(['?' * len(GHOST_USER_IDS)])
    check_query = f"SELECT COUNT(*) as count FROM users WHERE user_id IN ({placeholders})"
    
    try:
        cursor = conn.execute(check_query, GHOST_USER_IDS)
        result = cursor.fetchone()
        remaining = result['count']
        
        if remaining == 0:
            print(f"   ✅ 所有幽靈帳號已刪除 (剩餘: 0)")
        else:
            print(f"   ⚠️  還有 {remaining} 個幽靈帳號未刪除")
            return False
    
    except Exception as e:
        print(f"   ❌ 驗證失敗: {str(e)}")
        return False
    
    # 2. 檢查凱文重複
    check_kaiwen_query = "SELECT COUNT(*), GROUP_CONCAT(user_id) FROM users WHERE nickname = '凱文'"
    
    try:
        cursor = conn.execute(check_kaiwen_query)
        result = cursor.fetchone()
        count = result[0]
        user_ids = result[1]
        
        if count == 1:
            print(f"   ✅ 凱文重複已修復 (僅剩 1 筆記錄: user_id={user_ids})")
        elif count == 0:
            print(f"   ⚠️  凱文帳號已全部刪除")
        else:
            print(f"   ⚠️  凱文還有 {count} 筆記錄: {user_ids}")
            return False
    
    except Exception as e:
        print(f"   ❌ 檢查凱文失敗: {str(e)}")
        return False
    
    # 3. 檢查 NULL nickname 帳號
    check_null_query = "SELECT COUNT(*) as count FROM users WHERE nickname IS NULL OR nickname = ''"
    
    try:
        cursor = conn.execute(check_null_query)
        result = cursor.fetchone()
        null_count = result['count']
        
        if null_count == 0:
            print(f"   ✅ 沒有 NULL nickname 帳號")
        else:
            print(f"   ⚠️  還有 {null_count} 個 NULL nickname 帳號")
    
    except Exception as e:
        print(f"   ❌ 檢查 NULL 失敗: {str(e)}")
    
    print("-" * 80)
    return True

def show_remaining_users(conn):
    """列出剩餘玩家 (簡要統計)"""
    print("\n📊 資料庫統計:")
    print("-" * 80)
    
    try:
        # 1. 總玩家數
        cursor = conn.execute("SELECT COUNT(*) as count FROM users")
        total = cursor.fetchone()['count']
        print(f"   📈 總玩家: {total} 人")
        
        # 2. 真實玩家 (有 nickname)
        cursor = conn.execute("SELECT COUNT(*) as count FROM users WHERE nickname IS NOT NULL AND nickname != ''")
        real = cursor.fetchone()['count']
        print(f"   👥 真實玩家: {real} 人")
        
        # 3. 虛擬帳號 (無 nickname)
        cursor = conn.execute("SELECT COUNT(*) as count FROM users WHERE nickname IS NULL OR nickname = ''")
        virtual = cursor.fetchone()['count']
        print(f"   👻 虛擬帳號: {virtual} 個")
        
        # 4. 重複昵稱
        cursor = conn.execute("""
        SELECT COUNT(*) as count FROM (
            SELECT nickname FROM users 
            WHERE nickname IS NOT NULL AND nickname != ''
            GROUP BY nickname 
            HAVING COUNT(*) > 1
        )
        """)
        duplicates = cursor.fetchone()['count']
        print(f"   🔁 重複昵稱: {duplicates} 組")
        
        # 5. 總 KKCoin
        cursor = conn.execute("SELECT COALESCE(SUM(kkcoin), 0) as total FROM users")
        total_coin = cursor.fetchone()['total']
        print(f"   💰 總 KKCoin: {total_coin}")
        
        # 6. 列出前 10 個玩家
        print("\n   📋 前 10 個玩家:")
        cursor = conn.execute("""
        SELECT user_id, nickname, level, xp, kkcoin
        FROM users
        WHERE nickname IS NOT NULL AND nickname != ''
        ORDER BY level DESC, xp DESC
        LIMIT 10
        """)
        
        for i, row in enumerate(cursor.fetchall(), 1):
            nickname = row['nickname']
            level = row['level'] if row['level'] else 0
            kkcoin = row['kkcoin'] if row['kkcoin'] else 0
            print(f"      {i:>2}. {nickname:>15} | Lv {level:>3} | KKCoin: {kkcoin:>8}")
        
        print("-" * 80)
    
    except Exception as e:
        print(f"   ❌ 統計失敗: {str(e)}")

def main():
    """主函數"""
    print("=" * 80)
    print("🔧 GCP 資料庫幽靈帳號清除工具")
    print("=" * 80)
    print()
    
    # 步驟 1: 備份
    backup_path = backup_database()
    print()
    
    # 步驟 2: 連接資料庫
    conn = connect_db()
    print()
    
    # 步驟 3: 查詢待刪除帳號
    if not get_ghost_details(conn):
        print("\n❌ 待刪除帳號查詢失敗")
        conn.close()
        sys.exit(1)
    
    # 步驟 4: 刪除幽靈帳號
    if not delete_ghosts(conn):
        print("\n❌ 刪除操作取消或失敗")
        conn.close()
        sys.exit(1)
    
    # 步驟 5: 驗證刪除
    if not verify_deletion(conn):
        print("\n⚠️  驗證過程發現異常")
    
    # 步驟 6: 顯示統計
    show_remaining_users(conn)
    
    # 關閉連接
    conn.close()
    
    print("\n✅ 清除操作完成！")
    print(f"   備份位置: {backup_path}")
    print()

if __name__ == '__main__':
    main()
