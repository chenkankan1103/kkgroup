#!/usr/bin/env python3
"""
修復 19 位異常 Discord ID
將其改回正確的 18 位格式
"""

import sqlite3
from datetime import datetime

DB_PATH = '/home/e193752468/kkgroup/user_data.db'

def fix_abnormal_ids():
    """修復異常 ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print('=' * 90)
    print('🔧 修復異常 Discord ID (19位 → 18位)')
    print(f'⏰ 時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 90)
    print()
    
    # 定義修復對應表（從移除末位得出）
    fixes = [
        ('𝓬𝓱𝓮𝓷𝓰.', 1016694532047388672, 101669453204738867),
        ('小筑', 1018549741920989312, 101854974192098931),
        ('protect', 1045940524265259008, 104594052426525900),
        ('yoru', 1129072804659208192, 112907280465920819),
        ('白鱼', 1148893517901463552, 114889351790146355),
        ('餒餒補給站', 1209509919699505152, 120950991969950515),
        ('lin_jack204473740', 1248646973943185408, 124864697394318540),
        ('梅川イブ', 1296436778021945344, 129643677802194534),
        ('你爸爸', 1318478389333458944, 131847838933345894),
        ('蘇門達臘', 1373284011472060416, 137328401147206041),
        ('江彥🏀', 1375651445231058944, 137565144523105894),
        ('lix', 1393778424535056384, 139377842453505638),
    ]
    
    print(f'📝 待修復列表:')
    print()
    
    success_count = 0
    for nick, wrong_id, correct_id in fixes:
        print(f'{nick}:')
        print(f'   {wrong_id} → {correct_id}')
        
        try:
            cursor.execute(
                'UPDATE users SET user_id = ? WHERE nickname = ?',
                (correct_id, nick)
            )
            
            if cursor.rowcount > 0:
                print(f'   ✅ 已修復')
                success_count += 1
            else:
                print(f'   ⚠️ 未找到該昵稱')
        except Exception as e:
            print(f'   ❌ 錯誤: {e}')
        
        print()
    
    conn.commit()
    
    print('=' * 90)
    print(f'✅ 修復完成: {success_count}/{len(fixes)} 個')
    print()
    
    # 驗證修復結果
    print('🔍 驗證修復結果:')
    cursor.execute('SELECT LENGTH(CAST(user_id AS TEXT)) as len, COUNT(*) as cnt FROM users GROUP BY len')
    lengths = cursor.fetchall()
    
    for length, count in sorted(lengths):
        status = '✅' if length == 18 else '❌'
        print(f'   {status} {length}位: {count}個')
    
    print()
    
    # 檢查是否還有異常
    cursor.execute('SELECT user_id, nickname FROM users WHERE LENGTH(CAST(user_id AS TEXT)) != 18')
    remaining = cursor.fetchall()
    
    if remaining:
        print(f'⚠️ 仍有 {len(remaining)} 個異常 ID:')
        for uid, nick in remaining:
            print(f'   {nick}: {uid}')
    else:
        print('✅ 所有 ID 已正常化為 18 位')
    
    print()
    print('=' * 90)
    
    conn.close()

if __name__ == '__main__':
    fix_abnormal_ids()
