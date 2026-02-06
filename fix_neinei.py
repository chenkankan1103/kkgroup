#!/usr/bin/env python3
import sqlite3

db_path = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print('=== Fix Neinei ID ===\n')

print('Before:')
c.execute('SELECT user_id, nickname FROM users WHERE user_id = 1209509919699505152')
result = c.fetchone()
if result:
    print(f'  ID: {result[0]}, Nickname: {result[1]}')
else:
    print('  Not found')

print('\nExecuting fix...')
old_id = 1209509919699505152
new_id = 1209509919699505184

c.execute('UPDATE users SET user_id = ? WHERE user_id = ?', (new_id, old_id))
affected = c.rowcount
print(f'  Updated {affected} rows')

conn.commit()

print('\nAfter:')
c.execute('SELECT user_id, nickname FROM users WHERE user_id = ?', (new_id,))
result = c.fetchone()
if result:
    print(f'  ID: {result[0]}, Nickname: {result[1]}')
    print('  Fixed!')
else:
    print('  Failed!')

conn.close()
