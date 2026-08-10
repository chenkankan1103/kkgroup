#!/usr/bin/env python3
import sqlite3

db = sqlite3.connect("user_data.db")
cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
for r in cur.fetchall():
    print(r[0])
db.close()
