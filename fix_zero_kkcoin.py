import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(current_db)
c = conn.cursor()

print("修復所有 KKCOIN = 0 或 NULL 的用戶...\n")

# 找出所有 KKCOIN = 0 或 NULL 的用戶
c.execute('SELECT nickname, user_id FROM users WHERE kkcoin = 0 OR kkcoin IS NULL')
users_to_fix = c.fetchall()

print(f"找到 {len(users_to_fix)} 個需要修復的用戶:")
for nick, uid in users_to_fix:
    print(f"   {nick:20} {uid}")

# 修復：設置為 10000
c.execute('UPDATE users SET kkcoin = 10000 WHERE kkcoin = 0 OR kkcoin IS NULL')
affected = c.rowcount

conn.commit()

print(f"\n修復完成，受影響 {affected} 列\n")

# 驗證
print("驗證修復結果:")
for nick, uid in users_to_fix:
    c.execute('SELECT kkcoin FROM users WHERE user_id = ?', (uid,))
    result = c.fetchone()
    if result and result[0] == 10000:
        print(f"   ✅ {nick:20} = 10000")
    else:
        print(f"   ❌ {nick:20} = {result[0] if result else 'NOT FOUND'}")

conn.close()
