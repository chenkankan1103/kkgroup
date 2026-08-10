import sqlite3
conn = sqlite3.connect("user_data.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%anime%'")
for row in cursor.fetchall():
    print(row)
conn.close()