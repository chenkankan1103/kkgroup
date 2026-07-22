#!/usr/bin/env python3
import sqlite3
db = sqlite3.connect('/home/e193752468/kkgroup/user_data.db')
cur = db.execute('SELECT user_id, kkcoin FROM users LIMIT 5')
for r in cur.fetchall():
    print(r)
db.close()