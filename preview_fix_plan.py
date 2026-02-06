#!/usr/bin/env python3
"""
Discord ID 修正計畫 - 預覽模式
只顯示要修正的內容，不執行任何變動
"""

import sqlite3
from pathlib import Path

DB_PATH = './user_data.db'

def preview_fixes():
    """顯示所有要修正的操作"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 取得所有用戶
        cursor.execute("SELECT user_id, nickname FROM users ORDER BY user_id DESC")
        users = cursor.fetchall()
        
        print("\n" + "="*80)
        print("📋 Discord ID 修正計畫 - 預覽模式")
        print("="*80)
        
        print(f"\n📊 資料庫中的用戶總數: {len(users)}\n")
        
        short_ids = []
        valid_ids = []
        no_nick = []
        test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB', 'Test_User']
        test_ids = []
        
        print(f"{'UserID':>20} | {'Nickname':<35} | 狀態")
        print("-" * 80)
        
        for user_id, nickname in users:
            nick_display = (nickname or "(無昵稱)")[:35]
            status = []
            
            # 檢查ID有效性
            if user_id < 100000000000000000:
                short_ids.append(user_id)
                status.append("❌ 短ID(無效)")
            else:
                valid_ids.append(user_id)
                status.append("✅ 有效")
            
            # 檢查昵稱
            if not nickname or nickname.strip() == '':
                no_nick.append(user_id)
                status.append("⚠️ 無昵稱")
            
            # 檢查測試ID
            if any(p in str(nickname or '').lower() for p in test_patterns):
                test_ids.append(user_id)
                status.append("🧪 測試ID")
            
            status_str = " | ".join(status)
            print(f"{user_id:>20} | {nick_display:<35} | {status_str}")
        
        conn.close()
        
        # 顯示修正計畫
        print("\n" + "="*80)
        print("🔧 修正計畫:")
        print("="*80)
        
        print(f"\n1️⃣ 短ID (需刪除): {len(short_ids)} 個")
        if short_ids:
            print("   🗑️ 將刪除的ID:")
            for sid in short_ids:
                print(f"      - {sid}")
        
        print(f"\n2️⃣ 測試ID (需刪除): {len(test_ids)} 個")
        if test_ids:
            print("   🗑️ 將刪除的ID:")
            for tid in test_ids:
                print(f"      - {tid} ({[u[1] for u in users if u[0] == tid][0]})")
        
        print(f"\n3️⃣ 無昵稱用戶: {len(no_nick)} 個")
        if no_nick:
            print("   (需要從Discord同步昵稱)")
            for nid in no_nick:
                print(f"      - {nid}")
        
        # 預估結果
        print("\n" + "="*80)
        print("📈 預估結果:")
        print("="*80)
        
        deleted_count = len(set(short_ids + test_ids))  # 去重
        print(f"\n修正前: {len(users)} 個用戶")
        print(f"將刪除: {deleted_count} 個用戶")
        print(f"修正後: {len(users) - deleted_count} 個用戶")
        
        print(f"\n✅ 最終有效用戶: {len(valid_ids) - deleted_count}")
        
        print("\n" + "="*80)
        print("⚠️ 要執行修正，請運行: python3 run_id_fix_pipeline.py")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

if __name__ == '__main__':
    preview_fixes()
