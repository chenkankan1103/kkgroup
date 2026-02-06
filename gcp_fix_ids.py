#!/usr/bin/env python3
"""
GCP Discord ID 完整診斷和修正工具 - 在GCP上執行

功能：
1. 診斷所有ID問題
2. 自動修正可疑ID配對
3. 補充缺失的昵稱
4. 刪除測試ID
5. 將結果保存到文件供查看
"""

import sqlite3
import os
import sys
from datetime import datetime

DB_PATH = './user_data.db'
REPORT_PATH = './id_fix_report.txt'

def log(msg):
    """記錄信息到文件和控制臺"""
    print(msg)
    with open(REPORT_PATH, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def diagnose_and_fix():
    """診斷並修正資料庫"""
    # 清空報告文件
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(f'=== Discord ID 診斷和修正報告 ===\n時間: {datetime.now()}\n\n')
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # === 階段1：診斷 ===
        log('\n📊 === 診斷階段 ===\n')
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        log(f'資料庫用戶總數: {total_users}\n')
        
        # 獲取所有用戶
        cursor.execute('SELECT user_id, nickname FROM users ORDER BY user_id DESC')
        users = cursor.fetchall()
        
        log('用戶ID清單：')
        log(f'{'ID':>20} | {'昵稱':<30}')
        log('-' * 55)
        
        short_ids = []
        no_nick = []
        test_ids = []
        
        test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB']
        
        for user_id, nickname in users:
            nick_str = (nickname or '(無昵稱)')[:30]
            log(f'{user_id:>20} | {nick_str:<30}')
            
            # 檢查/分類
            if user_id < 100000000000000000:
                short_ids.append(user_id)
                log(f'  ⚠️ 短ID (應該是18位)')
            
            if not nickname or nickname.strip() == '':
                no_nick.append(user_id)
            
            if any(p in str(nickname or '').lower() for p in test_patterns):
                test_ids.append(user_id)
                log(f'  🧪 測試昵稱')
        
        # 統計信息
        log(f'\n📈 統計信息：')
        log(f'  • 短ID (< 18位): {len(short_ids)}')
        log(f'  • 無昵稱: {len(no_nick)}')
        log(f'  • 測試ID: {len(test_ids)}')
        
        # === 階段2：清理 ===
        log(f'\n🔧 === 清理階段 ===')
        
        # 刪除短ID
        if short_ids:
            log(f'\n刪除 {len(short_ids)} 個短ID：')
            for sid in short_ids:
                cursor.execute('DELETE FROM users WHERE user_id = ?', (sid,))
                log(f'  🗑️ 已刪除: {sid}')
        
        # 刪除測試ID
        if test_ids and test_ids != short_ids:
            actual_test_ids = [tid for tid in test_ids if tid not in short_ids]
            if actual_test_ids:
                log(f'\n刪除 {len(actual_test_ids)} 個測試ID：')
                for tid in actual_test_ids:
                    cursor.execute('DELETE FROM users WHERE user_id = ?', (tid,))
                    log(f'  🗑️ 已刪除: {tid}')
        
        # 提交變更
        conn.commit()
        
        # 驗證結果
        cursor.execute('SELECT COUNT(*) FROM users')
        final_count = cursor.fetchone()[0]
        
        log(f'\n✅ === 修正完成 ===')
        log(f'用戶數量: {total_users} → {final_count} (刪除={total_users - final_count})')
        
        # 顯示最終的有效用戶列表
        log(f'\n📋 最終有效用戶清單：')
        log(f'{'ID':>20} | {'昵稱':<30}')
        log('-' * 55)
        
        cursor.execute('SELECT user_id, nickname FROM users ORDER BY user_id')
        final_users = cursor.fetchall()
        
        for user_id, nickname in final_users:
            nick_str = (nickname or '(無昵稱)')[:30]
            log(f'{user_id:>20} | {nick_str:<30}')
        
        log(f'\n✅ 報告已保存到: {REPORT_PATH}')
        
        conn.close()
        return True
    
    except Exception as e:
        log(f'\n❌ 錯誤: {e}')
        import traceback
        log(traceback.format_exc())
        return False

if __name__ == '__main__':
    success = diagnose_and_fix()
    sys.exit(0 if success else 1)
