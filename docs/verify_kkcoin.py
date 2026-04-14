import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
backup_db = '/home/e193752468/kkgroup/user_data.db.backup.20260206_054523'

conn_current = sqlite3.connect(current_db)
conn_backup = sqlite3.connect(backup_db)

c_current = conn_current.cursor()
c_backup = conn_backup.cursor()

print("=== 最高 KKCOIN 用戶對比（備份 vs 現在）===\n")

# 獲取備份中的前 10 個最高用戶
c_backup.execute('SELECT nickname, kkcoin FROM users WHERE kkcoin IS NOT NULL ORDER BY kkcoin DESC LIMIT 10')
backup_users = {nick: coins for nick, coins in c_backup.fetchall()}

print("備份中的最高用戶:")
for nick, coins in sorted(backup_users.items(), key=lambda x: x[1], reverse=True):
    print(f'   {nick:20} = {coins}')

print("\n現在 DB 中的對應用戶:")
for nick in sorted(backup_users.keys(), key=lambda x: backup_users[x], reverse=True):
    c_current.execute('SELECT kkcoin FROM users WHERE nickname = ?', (nick,))
    result = c_current.fetchone()
    if result:
        current_coins = result[0]
        expected_coins = backup_users[nick]
        status = "✅" if current_coins == expected_coins else f"❌ (should be {expected_coins})"
        print(f'   {nick:20} = {current_coins:6} {status}')
    else:
        print(f'   {nick:20} NOT FOUND ❌')

print("\n=== 驗證統計 ===")
c_current.execute('SELECT COUNT(*) FROM users WHERE kkcoin = 10000')
new_users = c_current.fetchone()[0]
print(f'新玩家 (KKCOIN=10000): {new_users}')

c_current.execute('SELECT COUNT(*) FROM users WHERE kkcoin != 10000 AND kkcoin IS NOT NULL')
old_users = c_current.fetchone()[0]
print(f'恢復的原始玩家: {old_users}')

c_current.execute('SELECT COUNT(*) FROM users')
total = c_current.fetchone()[0]
print(f'總用戶數: {total}')

conn_current.close()
conn_backup.close()
