import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
backup_db = '/home/e193752468/kkgroup/user_data.db.backup.20260206_054523'

# 先從備份中獲取原始用戶的 ID 列表
conn_backup = sqlite3.connect(backup_db)
c_backup = conn_backup.cursor()
c_backup.execute('SELECT user_id FROM users')
original_user_ids = set(row[0] for row in c_backup.fetchall())
conn_backup.close()

print(f"原始用戶數: {len(original_user_ids)}\n")

# 在現在的 DB 中，所有不在原始列表中的用戶就是新用戶
conn_current = sqlite3.connect(current_db)
c = conn_current.cursor()

# 找出所有 KKCOIN = 10000 且不在原始用戶列表中的新用戶
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE kkcoin = 10000')
new_users_with_10k = [(nick, uid, kkcoin) for nick, uid, kkcoin in c.fetchall() if uid not in original_user_ids]

print(f"需要改成 0 的新用戶數: {len(new_users_with_10k)}\n")

if new_users_with_10k:
    print("部分新用戶列表:")
    for nick, uid, kkcoin in new_users_with_10k[:5]:
        print(f"   {nick:20} {uid:20} {kkcoin}")
    if len(new_users_with_10k) > 5:
        print(f"   ... 還有 {len(new_users_with_10k) - 5} 個用戶\n")

    # 執行更新：所有 KKCOIN = 10000 且不在原始用戶列表中的用戶改成 0
    new_user_ids = [uid for _, uid, _ in new_users_with_10k]
    c.execute('UPDATE users SET kkcoin = 0 WHERE kkcoin = 10000 AND user_id NOT IN ({})'.format(
        ','.join('?' * len(original_user_ids))
    ), list(original_user_ids))
    
    affected = c.rowcount
    conn_current.commit()
    
    print(f"更新完成，受影響 {affected} 列\n")
    
    # 驗證
    print("驗證修復結果:")
    c.execute('SELECT COUNT(*) FROM users WHERE kkcoin = 0')
    zero_count = c.fetchone()[0]
    print(f"   KKCOIN = 0 的用戶: {zero_count}")
    
    c.execute('SELECT COUNT(*) FROM users WHERE kkcoin = 10000')
    ten_k_count = c.fetchone()[0]
    print(f"   KKCOIN = 10000 的用戶: {ten_k_count}")
    
    c.execute('SELECT COUNT(*) FROM users WHERE kkcoin > 0 AND kkcoin != 10000')
    other_count = c.fetchone()[0]
    print(f"   其他 KKCOIN 值: {other_count}")
    
    print(f"\n✅ 所有新用戶的 KKCOIN 已改成 0")
else:
    print("❌ 沒有找到 KKCOIN = 10000 的新用戶")

conn_current.close()
