import sqlite3

conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# 列出所有表格
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('Tables in database:')
for table in tables:
    print(f'  - {table[0]}')

# 查看 users 表格的欄位
try:
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    if columns:
        print('\nCurrent users columns:')
        for col in columns:
            print(f'  {col[1]}: {col[2]}')
    else:
        print('\nuser_data table is empty or does not exist')
except:
    print('\nCannot access user_data table')

conn.close()
