#!/usr/bin/env python3
"""
ID 偏差檢查與修復工具
比較資料庫中的 user_id 是否有錯誤，並列出潛在的問題
"""

import sqlite3
import json
from collections import defaultdict

DB_PATH = '/home/e193752468/kkgroup/user_data.db'

def check_id_issues():
    """檢查 ID 問題"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 獲取所有用戶及其昵稱
    cursor.execute('SELECT user_id, nickname FROM users ORDER BY user_id')
    all_users = cursor.fetchall()
    
    print('=' * 80)
    print('🔍 ID 偏差檢查報告')
    print('=' * 80)
    print()
    
    # 統計
    total_users = len(all_users)
    named_users = sum(1 for _, nick in all_users if nick)
    null_users = total_users - named_users
    
    print(f'📊 統計:')
    print(f'   總用戶: {total_users}')
    print(f'   有昵稱: {named_users}')
    print(f'   無昵稱（虛擬帳號）: {null_users}')
    print()
    
    # 檢查 NULL 或空昵稱的用戶
    print('👻 虛擬帳號（無有效昵稱）:')
    null_list = [(uid, nick) for uid, nick in all_users if not nick or not nick.strip()]
    
    if null_list:
        print(f'   發現 {len(null_list)} 個：')
        for uid, nick in null_list[:10]:
            print(f'      user_id={uid}, nickname={repr(nick)}')
        if len(null_list) > 10:
            print(f'      ... 還有 {len(null_list) - 10} 個')
    else:
        print('   ✅ 沒有虛擬帳號')
    
    print()
    
    # 檢查可疑的 ID 值（可能是浮點轉換的結果）
    print('⚠️ 檢查可疑的 ID 值:')
    suspicious = []
    for uid, nick in all_users:
        # 檢查末尾接近 37 的倍數（精度損失特徵）
        if uid % 100 in [37, 60, 23]:  # 可能的浮點損失特徵
            suspicious.append((uid, nick))
    
    if suspicious:
        print(f'   發現 {len(suspicious)} 個可疑 ID:')
        for uid, nick in suspicious[:10]:
            nick_display = nick or '[無昵稱]'
            print(f'      {nick_display}: {uid}')
        if len(suspicious) > 10:
            print(f'      ... 還有 {len(suspicious) - 10} 個')
    else:
        print('   ✅ 沒有發現可疑 ID')
    
    print()
    
    # 檢查昵稱長度異常的用戶
    print('🔤 檢查異常昵稱:')
    long_nicks = [(uid, nick) for uid, nick in all_users if nick and len(nick) > 50]
    short_nicks = [(uid, nick) for uid, nick in all_users if nick and len(nick) < 2]
    
    if long_nicks:
        print(f'   ⚠️ 昵稱過長（>50字）: {len(long_nicks)} 個')
    if short_nicks:
        print(f'   ⚠️ 昵稱過短（<2字）: {len(short_nicks)} 個')
    if not long_nicks and not short_nicks:
        print('   ✅ 昵稱長度正常')
    
    print()
    print('=' * 80)
    print('✅ 檢查完成')
    
    conn.close()

if __name__ == '__main__':
    check_id_issues()
