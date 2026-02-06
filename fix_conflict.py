#!/usr/bin/env python3
import sqlite3

db_path = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print('=== Resolving conflict for Green Sadness ===\n')

# Delete ghost record
print('Deleting ghost record(ID: 535810695011368972)...')
c.execute('DELETE FROM users WHERE user_id = 535810695011368972 AND nickname = ""')
rows = c.rowcount
print(f'Deleted {rows} rows\n')

# Fix Green Sadness
print('Fixing Green Sadness (535810695011368960 -> 535810695011368972)...')
c.execute(
    'UPDATE users SET user_id = ? WHERE user_id = ?',
    (535810695011368972, 535810695011368960)
)
print(f'Updated\n')

# Verify
c.execute('SELECT user_id, nickname FROM users WHERE nickname LIKE "%小哀%"')
result = c.fetchone()
if result:
    print(f'Verified: {result[0]} -> {result[1]}')
else:
    print('Verification failed')

conn.commit()
conn.close()
