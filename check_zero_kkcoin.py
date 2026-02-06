import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(current_db)
c = conn.cursor()

print("檢查現在的 KKCOIN 分佈...\n")

# 檢查 KKCOIN = 0 的用戶
c.execute('SELECT COUNT(*) FROM users WHERE kkcoin = 0 OR kkcoin IS NULL')
zero_count = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM users WHERE kkcoin = 10000')
ten_k_count = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM users WHERE kkcoin > 0 AND kkcoin != 10000')
other_count = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM users')
total = c.fetchone()[0]

print(f"KKCOIN = 0 或 NULL: {zero_count}")
print(f"KKCOIN = 10000: {ten_k_count}")
print(f"其他 KKCOIN 值: {other_count}")
print(f"總用戶: {total}")

print(f"\n顯示部分 KKCOIN = 0 的用戶:")
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE kkcoin = 0 OR kkcoin IS NULL LIMIT 5')
for row in c.fetchall():
    print(f"   {row}")

conn.close()
