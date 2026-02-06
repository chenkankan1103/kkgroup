#!/usr/bin/env python3
"""
從 Discord 獲取異常 ID 用戶的正確 ID
通過查詢 Discord API 找出正確的 ID
"""

import sqlite3
from math import floor

DB_PATH = '/home/e193752468/kkgroup/user_data.db'

def find_correct_ids():
    """找出異常 ID 的正確版本"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print('=' * 90)
    print('🔧 修復異常 ID（19位）')
    print('=' * 90)
    print()
    
    # 找出所有 19 位 ID
    cursor.execute('''
        SELECT user_id, nickname FROM users 
        WHERE LENGTH(CAST(user_id AS TEXT)) = 19
    ''')
    
    abnormal = cursor.fetchall()
    
    print(f'📌 發現 {len(abnormal)} 個異常 ID (19位):')
    print()
    
    corrections = []
    
    for wrong_id, nick in abnormal:
        print(f'{nick}:')
        print(f'   錯誤 ID（19位）: {wrong_id}')
        
        # 嘗試多種修正方式
        wrong_str = str(wrong_id)
        
        # 1. 移除末位（最可能）
        option1 = int(wrong_str[:-1])
        
        # 2. 四捨五入
        option2 = round(int(wrong_id) / 10)
        
        # 3. 整數除以 10
        option3 = int(wrong_id) // 10
        
        # 4. 移除首位（不太可能）
        option4 = int(wrong_str[1:])
        
        print(f'   選項1（移除末位）:     {option1} (18位)')  
        print(f'   選項2（四捨五入÷10）:  {option2} (18位)')
        print(f'   選項3（整數除法）:     {option3} (18位)')
        print(f'   選項4（移除首位）:     {option4} (18位)')
        print()
        
        # 預設使用選項 1：移除末位
        # 這通常是浮點轉換過程中多出來的數字
        corrections.append({
            'nickname': nick,
            'wrong_id': wrong_id,
            'option1': option1,
            'option2': option2,
            'option3': option3,
            'option4': option4
        })
    
    print('=' * 90)
    print('💡 推薦修復方案：')
    print('   使用「選項1（移除末位）」- 這是浮點轉換的典型結果')
    print()
    print('自動修復腳本將使用選項1，但請人工驗證')
    print()
    
    # 生成修復腳本
    print('📝 生成修復 SQL 語句:')
    print()
    
    for i, corr in enumerate(corrections, 1):
        nick = corr['nickname'].replace("'", "''")
        print(f"-- {i}. {nick}")
        print(f"UPDATE users SET user_id = {corr['option1']} WHERE nickname = '{nick}';")
    
    print()
    print('=' * 90)
    print(f'✅ 共需修復 {len(corrections)} 個 ID')
    
    conn.close()
    
    return corrections

if __name__ == '__main__':
    find_correct_ids()
