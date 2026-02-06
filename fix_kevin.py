import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(current_db)
c = conn.cursor()

print("修復凱文的 KKCOIN...")

# 查找凱文並更新
c.execute('UPDATE users SET kkcoin = 100000 WHERE nickname = "No.60123 凱文" OR nickname LIKE "%凱文%"')
affected = c.rowcount

conn.commit()
print(f'受影響的列: {affected}')

# 驗證
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE nickname LIKE "%凱文%"')
result = c.fetchone()
if result:
    print(f'驗證: {result}')
    if result[2] == 100000:
        print('✅ 凱文 KKCOIN 已恢復到 100000')
    else:
        print(f'❌ 凱文 KKCOIN 仍然是 {result[2]}')
else:
    print('❌ 找不到凱文')

conn.close()
