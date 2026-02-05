from sheet_sync_manager import SheetSyncManager

manager = SheetSyncManager()

# Row1: grouping (ignored), Row2: actual headers (包含像 '第 1 欄' 的情形)
mock_sheet_data = [
    ['Group'],
    ['第 1 欄', 'nickname', 'level', 'kkcoin', 'title'],
    # 各種 user_id 表示法：科學記號、大整數、浮點、無效值
    ['1.23456789012345E+17', 'UserA', '1', '100', '新手'],
    ['1.23456789123456e+17', 'UserB', '2', '200', '勇者'],
    ['123456789012345678', 'UserC', '3', '300', '戰士'],
    ['1.0E+15', 'UserD', '1', '50', '小兵'],
    ['', 'UserE', '1', '10', '無'],
    ['N/A', 'UserF', '1', '0', '無'],
    ['abc123', 'UserG', '1', '0', '無'],
    ['1.2345E+5', 'UserH', '1', '0', '無']
]

print('='*60)
print('Running simulated SHEET sync test (with "第 1 欄" and scientific notation)')
print('='*60)

headers = manager.get_sheet_headers(mock_sheet_data)
print('\nHeaders:', headers)

data_rows = manager.get_sheet_data_rows(mock_sheet_data)
print('\nData rows count:', len(data_rows))

manager.ensure_db_schema(headers)

records = manager.parse_records(headers, data_rows)
print('\nParsed records count:', len(records))
for r in records:
    print(r)

updated, inserted, errors = manager.sync_records(records)
print(f"\nSync result: updated={updated}, inserted={inserted}, errors={errors}")

# Show DB counts for verification
import sqlite3
conn = sqlite3.connect('user_data.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM users')
count = cur.fetchone()[0]
cur.execute('PRAGMA table_info(users)')
cols = [row[1] for row in cur.fetchall()]
conn.close()

print('\nDB record count:', count)
print('DB columns sample:', cols[:10])
