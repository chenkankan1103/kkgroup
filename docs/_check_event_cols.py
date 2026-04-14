import sqlite3
conn = sqlite3.connect('user_data.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(users)")
cols = [r[1] for r in cur.fetchall()]
event_cols = [c for c in cols if 'event' in c or 'message' in c]
print('event/message cols:', event_cols)
conn.close()
