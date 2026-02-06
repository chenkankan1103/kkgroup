import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
backup_db = '/home/e193752468/kkgroup/user_data.db.backup.20260206_054523'

conn_current = sqlite3.connect(current_db)
conn_backup = sqlite3.connect(backup_db)

c_current = conn_current.cursor()
c_backup = conn_backup.cursor()

print("=== 凱文的確切資訊 ===\n")

# 備份中的凱文
c_backup.execute('SELECT nickname, user_id, kkcoin FROM users WHERE nickname LIKE "%凱文%"')
backup_kevin = c_backup.fetchone()
if backup_kevin:
    print(f"備份中: {backup_kevin}")
    backup_kevin_id = backup_kevin[1]
else:
    print("備份中找不到凱文")
    backup_kevin_id = None

# 現在 DB 中的
if backup_kevin_id:
    c_current.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = ?', (backup_kevin_id,))
    current_kevin = c_current.fetchone()
    if current_kevin:
        print(f"現在DB中: {current_kevin}")
        if current_kevin[2] == 100000:
            print("✅ KKCOIN 已正確恢復到 100000")
        else:
            print(f"❌ KKCOIN 是 {current_kevin[2]}, 需要修復到 100000")
    else:
        print(f"現在DB中找不到 ID {backup_kevin_id}")

print("\n=== 餒餒補給站的確切資訊 ===")

# 備份中的餒餒補給站
c_backup.execute('SELECT nickname, user_id, kkcoin FROM users WHERE nickname LIKE "%餒餒%"')
neinei_backup = c_backup.fetchone()
if neinei_backup:
    print(f"備份中: {neinei_backup}")
    neinei_id = neinei_backup[1]
    
    # 現在 DB 中的
    c_current.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = ?', (neinei_id,))
    neinei_current = c_current.fetchone()
    if neinei_current:
        print(f"現在DB中: {neinei_current}")
        if neinei_current[2] == 70000:
            print("✅ KKCOIN 正確")
        else:
            print(f"❌ KKCOIN 是 {neinei_current[2]}, 應該是 70000")
    else:
        print(f"現在DB中找不到 ID {neinei_id}")
else:
    print("備份中找不到餒餒補給站")

# 列出所有 nickname 包含凱文或餒餒的
print("\n=== 所有相關用戶（現在DB） ===")
c_current.execute('SELECT nickname, user_id, kkcoin FROM users WHERE nickname LIKE "%凱文%" OR nickname LIKE "%餒餒%"')
for row in c_current.fetchall():
    print(f"   {row}")

conn_current.close()
conn_backup.close()
