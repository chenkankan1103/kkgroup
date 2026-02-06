#!/usr/bin/env python3
"""
詳細的 ID 和昵稱對應關係檢查
找出所有可能導致頭像加載失敗的原因
"""

import sqlite3

DB_PATH = '/home/e193752468/kkgroup/user_data.db'

def detailed_check():
    """詳細檢查"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print('=' * 90)
    print('📋 詳細 ID 與昵稱對應關係檢查')
    print('=' * 90)
    print()
    
    # 獲取所有欄位
    cursor.execute('PRAGMA table_info(users)')
    columns = [row[1] for row in cursor.fetchall()]
    print(f'📑 表格欄位: {", ".join(columns)}')
    print()
    
    # 完整用戶列表
    cursor.execute('SELECT * FROM users ORDER BY user_id')
    users = cursor.fetchall()
    
    col_names = ['user_id', 'nickname', 'status', 'points', 'level', 'avatar_url', 'last_seen', 'created_at']
    # 根據實際欄位數量調整
    if len(columns) >= 8:
        col_names = columns[:8]
    
    print(f'📊 所有用戶 ({len(users)} 個):')
    print()
    
    # 打印格式化的用戶列表
    print(f'{"#":<3} {"User ID":<20} {"昵稱":<20} {"狀態":<10}')
    print('-' * 55)
    
    for i, user in enumerate(users[:20], 1):  # 首先顯示前20個
        user_id = str(user[0]) if user[0] else 'NULL'
        nick = str(user[1])[:19] if user[1] else '[NULL]'
        status = str(user[2]) if len(user) > 2 and user[2] else 'N/A'
        
        # 檢查 ID 的有效性
        try:
            uid_int = int(user[0]) if user[0] else 0
            if uid_int <= 0:
                print(f'{i:<3} {user_id:<20} {nick:<20} ⚠️ INVALID  (ID <= 0)', end='')
            elif len(user_id) != 18:
                print(f'{i:<3} {user_id:<20} {nick:<20} ⚠️ ODD      (len={len(user_id)})', end='')
            else:
                print(f'{i:<3} {user_id:<20} {nick:<20} ✅ Valid', end='')
        except:
            print(f'{i:<3} {user_id:<20} {nick:<20} ❌ ERROR', end='')
        
        print()
    
    if len(users) > 20:
        print(f'... ({len(users) - 20} 個更多)')
    
    print()
    print('=' * 90)
    
    # 檢查昵稱重複
    print('🔎 檢查昵稱重複:')
    cursor.execute('SELECT nickname, COUNT(*) as cnt FROM users WHERE nickname IS NOT NULL AND nickname != "" GROUP BY nickname HAVING cnt > 1')
    duplicates = cursor.fetchall()
    
    if duplicates:
        print(f'   ❌ 發現 {len(duplicates)} 個重複昵稱:')
        for nick, count in duplicates:
            print(f'      "{nick}": {count} 次')
            cursor.execute('SELECT user_id FROM users WHERE nickname = ?', (nick,))
            ids = [str(row[0]) for row in cursor.fetchall()]
            print(f'         IDs: {", ".join(ids)}')
    else:
        print('   ✅ 沒有重複昵稱')
    
    print()
    
    # 檢查 ID 重複
    print('🔎 檢查 user_id 重複:')
    cursor.execute('SELECT user_id, COUNT(*) as cnt FROM users GROUP BY user_id HAVING cnt > 1')
    id_duplicates = cursor.fetchall()
    
    if id_duplicates:
        print(f'   ❌ 發現 {len(id_duplicates)} 個重複 ID:')
        for user_id, count in id_duplicates:
            print(f'      {user_id}: {count} 次')
            cursor.execute('SELECT nickname FROM users WHERE user_id = ?', (user_id,))
            nicks = [str(row[0]) if row[0] else '[NULL]' for row in cursor.fetchall()]
            print(f'         昵稱: {", ".join(nicks)}')
    else:
        print('   ✅ 沒有重複 ID')
    
    print()
    
    # 檢查無效的 ID
    print('🔎 檢查無效的 user_id:')
    cursor.execute('SELECT user_id, nickname FROM users WHERE user_id IS NULL OR user_id = 0')
    invalid = cursor.fetchall()
    
    if invalid:
        print(f'   ⚠️ 發現 {len(invalid)} 個無效 ID:')
        for user_id, nick in invalid:
            print(f'      {nick}: {user_id}')
    else:
        print('   ✅ 沒有無效 ID')
    
    print()
    
    # 檢查異常 ID 格式
    print('🔎 檢查異常 ID 格式:')
    cursor.execute('SELECT user_id, nickname FROM users')
    all_users = cursor.fetchall()
    
    invalid_format = []
    for user_id, nick in all_users:
        if user_id:
            uid_str = str(user_id)
            if not uid_str.isdigit():
                invalid_format.append((user_id, nick, f'非全數字: {uid_str}'))
            elif len(uid_str) != 18:
                invalid_format.append((user_id, nick, f'長度不符: {len(uid_str)}'))
    
    if invalid_format:
        print(f'   ⚠️ 發現 {len(invalid_format)} 個異常格式:')
        for user_id, nick, reason in invalid_format:
            print(f'      {nick}: {user_id} ({reason})')
    else:
        print('   ✅ 所有 ID 格式正確（18 位十進制數字）')
    
    print()
    print('=' * 90)
    print('✅ 檢查完成')
    
    conn.close()

if __name__ == '__main__':
    detailed_check()
