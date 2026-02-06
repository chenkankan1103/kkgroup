import sqlite3

backup_db = '/home/e193752468/kkgroup/user_data.db.backup.20260206_054523'
conn_backup = sqlite3.connect(backup_db)
c = conn_backup.cursor()

# Check total users in backup
c.execute('SELECT COUNT(*) FROM users')
total = c.fetchone()[0]
print(f'Backup total users: {total}')

# Check for Kevin/凱文 variants
print('\nSearching for Kevin/凱文:')
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE nickname LIKE "%凱文%"')
for row in c.fetchall():
    print(f'   Found: {row}')

# Check for specific IDs
print('\nChecking specific IDs:')
for uid in [776464975551660123, 101669453204738867]:
    c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = ?', (uid,))
    result = c.fetchone()
    if result:
        print(f'   {uid}: {result}')
    else:
        print(f'   {uid}: NOT FOUND')

# Show top KKCOIN users
print('\nTop KKCOIN users in backup:')
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE kkcoin IS NOT NULL ORDER BY kkcoin DESC LIMIT 15')
for nick, uid, coins in c.fetchall():
    print(f'   {nick:20} {uid:20} = {coins}')

# Show all users with kkcoin > 40000
print('\nAll users with KKCOIN > 40000:')
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE kkcoin > 40000 ORDER BY kkcoin DESC')
for nick, uid, coins in c.fetchall():
    print(f'   {nick:20} {uid:20} = {coins}')

conn_backup.close()
