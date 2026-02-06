import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
backup_db = '/home/e193752468/kkgroup/user_data.db.backup.20260206_054523'

conn_current = sqlite3.connect(current_db)
conn_backup = sqlite3.connect(backup_db)

c_current = conn_current.cursor()
c_backup = conn_backup.cursor()

print("=" * 60)
print("最終驗證：備份 vs 現在資料庫")
print("=" * 60 + "\n")

# 獲取備份中的前 15 個最高用戶
c_backup.execute('SELECT nickname, kkcoin FROM users WHERE kkcoin IS NOT NULL ORDER BY kkcoin DESC LIMIT 15')
backup_top = c_backup.fetchall()

print(f"{'昵稱':20} {'備份':>10} {'現在':>10} {'狀態':>20}")
print("-" * 60)

all_correct = True
for nick, expected_coins in backup_top:
    c_current.execute('SELECT kkcoin FROM users WHERE nickname = ?', (nick,))
    result = c_current.fetchone()
    
    if result:
        current_coins = result[0]
        if current_coins == expected_coins:
            status = "✅ 正確"
        else:
            status = f"❌ {current_coins} != {expected_coins}"
            all_correct = False
        print(f"{nick:20} {expected_coins:10} {current_coins:10} {status:>20}")
    else:
        # User not in current DB (likely left Discord)
        status = "⚠️ 不在DB中"
        print(f"{nick:20} {expected_coins:10} {'N/A':>10} {status:>20}")

print("\n" + "=" * 60)
print("統計摘要")
print("=" * 60)

c_current.execute('SELECT COUNT(*) FROM users WHERE kkcoin = 10000')
new_count = c_current.fetchone()[0]

c_current.execute('SELECT COUNT(*) FROM users WHERE kkcoin != 10000 AND kkcoin IS NOT NULL')
restored_count = c_current.fetchone()[0]

c_current.execute('SELECT COUNT(*) FROM users')
total = c_current.fetchone()[0]

print(f"新玩家 (KKCOIN=10000): {new_count}")
print(f"恢復的原始玩家: {restored_count}")
print(f"總用戶數: {total}")

if all_correct:
    print("\n✅ 所有頂級用戶的 KKCOIN 已正確恢復！")
else:
    print("\n⚠️ 還有部分用戶的 KKCOIN 不正確")

conn_current.close()
conn_backup.close()
