import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(current_db)
c = conn.cursor()

print("=== 目前資料庫中的凱文 ===")
# 查找 nickname 包含凱文的所有用戶
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE nickname LIKE "%凱文%"')
for row in c.fetchall():
    print(f'   {row}')

# 查找特定 ID
print("\n檢查原始 ID (備份中的):")
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = 776464975551660160')
result = c.fetchone()
if result:
    print(f'   找到: {result}')
else:
    print(f'   NOT FOUND in current DB')

print("\n檢查現在的 ID:")
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = 776464975551660123')
result = c.fetchone()
if result:
    print(f'   找到: {result}')
else:
    print(f'   NOT FOUND in current DB')

# 顯示最高 KKCOIN 用戶
print("\n目前 DB 中 KKCOIN 最高的用戶:")
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE kkcoin IS NOT NULL ORDER BY kkcoin DESC LIMIT 5')
for nick, uid, coins in c.fetchall():
    print(f'   {nick:20} {uid:20} = {coins}')

conn.close()
