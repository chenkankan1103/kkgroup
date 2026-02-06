import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'
backup_db = '/home/e193752468/kkgroup/user_data.db.backup.20260206_054523'

conn_current = sqlite3.connect(current_db)
conn_backup = sqlite3.connect(backup_db)

c_current = conn_current.cursor()
c_backup = conn_backup.cursor()

print("=== 尋找所有 ID 變化的用戶 ===\n")

# 獲取備份中所有用戶
c_backup.execute('SELECT nickname, user_id, kkcoin FROM users ORDER BY kkcoin DESC NULLS LAST')
backup_users = c_backup.fetchall()

mismatches = []

for nick, backup_id, kkcoin in backup_users:
    if kkcoin is None:
        continue
        
    # 在現在DB中用 nickname 查找
    c_current.execute('SELECT user_id, kkcoin FROM users WHERE nickname = ?', (nick,))
    current_result = c_current.fetchone()
    
    if current_result:
        current_id, current_kkcoin = current_result
        if current_id != backup_id:
            mismatches.append({
                'nickname': nick,
                'backup_id': backup_id,
                'current_id': current_id,
                'expected_kkcoin': kkcoin,
                'current_kkcoin': current_kkcoin,
                'needs_fix': kkcoin != current_kkcoin
            })

print(f"找到 {len(mismatches)} 個 ID 變化的用戶:\n")
for m in mismatches:
    nick = m['nickname']
    bid = m['backup_id']
    cid = m['current_id']
    status = '(正確✅)' if not m['needs_fix'] else f"→ {m['expected_kkcoin']}"
    print(f"昵稱: {nick:20}")
    print(f"  ID: {bid:20} → {cid:20}")
    print(f"  KKCOIN: {m['current_kkcoin']:6} {status}")
    print()

# 修復所有需要修復的
print("=" * 50)
print("開始修復...\n")

fixes = 0
for m in mismatches:
    if m['needs_fix']:
        c_current.execute('UPDATE users SET kkcoin = ? WHERE user_id = ?', 
                         (m['expected_kkcoin'], m['current_id']))
        fixes += 1
        print(f"✅ 修復 {m['nickname']:20} KKCOIN: {m['current_kkcoin']} → {m['expected_kkcoin']}")

conn_current.commit()
print(f"\n共修復 {fixes} 個用戶的 KKCOIN")

conn_current.close()
conn_backup.close()
