import sqlite3

# 修復欄位類型
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

print('修復大麻欄位類型...')

# 將 INTEGER 類型的欄位改為 TEXT
try:
    # 先將數據備份到臨時欄位
    cursor.execute('ALTER TABLE users ADD COLUMN cannabis_inventory_temp TEXT')
    cursor.execute('ALTER TABLE users ADD COLUMN cannabis_plants_temp TEXT')

    # 複製數據（雖然現在是空的，但為了完整性）
    cursor.execute('UPDATE users SET cannabis_inventory_temp = CAST(cannabis_inventory AS TEXT)')
    cursor.execute('UPDATE users SET cannabis_plants_temp = CAST(cannabis_plants AS TEXT)')

    # 刪除舊欄位
    cursor.execute('ALTER TABLE users DROP COLUMN cannabis_inventory')
    cursor.execute('ALTER TABLE users DROP COLUMN cannabis_plants')

    # 重新創建為 TEXT 類型
    cursor.execute('ALTER TABLE users ADD COLUMN cannabis_inventory TEXT DEFAULT "{}"')
    cursor.execute('ALTER TABLE users ADD COLUMN cannabis_plants TEXT DEFAULT "[]"')

    # 恢復數據
    cursor.execute('UPDATE users SET cannabis_inventory = cannabis_inventory_temp')
    cursor.execute('UPDATE users SET cannabis_plants = cannabis_plants_temp')

    # 清理臨時欄位
    cursor.execute('ALTER TABLE users DROP COLUMN cannabis_inventory_temp')
    cursor.execute('ALTER TABLE users DROP COLUMN cannabis_plants_temp')

    conn.commit()
    print('✅ 欄位類型修復完成')

except Exception as e:
    print(f'❌ 修復失敗: {e}')
    conn.rollback()

# 驗證修復結果
cursor.execute('PRAGMA table_info(users)')
columns = cursor.fetchall()
print('\n修復後的欄位:')
for col in columns:
    if 'cannabis' in col[1]:
        print(f'  {col[1]} ({col[2]})')

conn.close()