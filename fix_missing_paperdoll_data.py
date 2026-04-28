# -*- coding: utf-8 -*-
import sqlite3
from cogs.ui.utils import paperdoll_manager

conn = sqlite3.connect('user_data.db')
c = conn.cursor()

# 取得預設配置
MALE_DEFAULT = paperdoll_manager.MALE_DEFAULT
FEMALE_DEFAULT = paperdoll_manager.FEMALE_DEFAULT

# 查詢所有有空紙娃娃字段的用戶
c.execute('SELECT user_id, face, hair, skin, top, bottom, shoes, gender FROM users WHERE face IS NULL OR face = ""')
missing_users = c.fetchall()

print(f"🔍 找到 {len(missing_users)} 個有空紙娃娃字段的用戶")

fixed_count = 0
for user_id, face, hair, skin, top, bottom, shoes, gender in missing_users:
    try:
        # 根據性別選擇預設值
        defaults = FEMALE_DEFAULT if gender == 'female' else MALE_DEFAULT
        
        # 只更新空的字段
        updates = {}
        if not face:
            updates['face'] = defaults.get('face')
        if not hair:
            updates['hair'] = defaults.get('hair')
        if not skin:
            updates['skin'] = defaults.get('skin')
        if not top:
            updates['top'] = defaults.get('top')
        if not bottom:
            updates['bottom'] = defaults.get('bottom')
        if not shoes:
            updates['shoes'] = defaults.get('shoes')
        
        # 執行更新
        if updates:
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [user_id]
            c.execute(f'UPDATE users SET {set_clause} WHERE user_id = ?', values)
            fixed_count += 1
            print(f"✅ 已修復用戶 {user_id}: {updates}")
    
    except Exception as e:
        print(f"❌ 修復用戶 {user_id} 失敗: {e}")

conn.commit()
conn.close()

print(f"\n✅ 完成！修復了 {fixed_count} 個用戶")
