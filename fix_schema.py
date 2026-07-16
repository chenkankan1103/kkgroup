import sqlite3
import sys

conn = sqlite3.connect('/home/e193752468/kkgroup/user_data.db')
c = conn.cursor()

# Drop old NOT NULL columns
print('Dropping old NOT NULL columns...')
columns_to_drop = ['week_start_date', 'day_of_week', 'scheduled_time', 'anime_sn', 'created_at']
for col in columns_to_drop:
    try:
        c.execute(f'ALTER TABLE anime_weekly_schedule DROP COLUMN {col}')
        print(f'Dropped {col}')
    except Exception as e:
        print(f'Warning: {e}')

conn.commit()

# Verify new schema
c.execute('PRAGMA table_info(anime_weekly_schedule)')
print('\nNew schema:')
for row in c.fetchall():
    print(row)

# Also fix anime_check_history table
print('\n--- Fixing anime_check_history ---')
c.execute('PRAGMA table_info(anime_check_history)')
for row in c.fetchall():
    print(row)

# Migrate data from old columns to new columns
c.execute('''
    UPDATE anime_check_history
    SET weekStartDate = check_date,
        dayOfWeek = (strftime('%w', check_date) + 6) % 7 + 1,
        scheduledTime = scheduled_time
    WHERE weekStartDate IS NULL
''')
print(f'Migrated {c.rowcount} rows in anime_check_history')

# Drop old columns from anime_check_history
for col in ['check_date', 'scheduled_time']:
    try:
        c.execute(f'ALTER TABLE anime_check_history DROP COLUMN {col}')
        print(f'Dropped {col}')
    except Exception as e:
        print(f'Warning: {e}')

conn.commit()

c.execute('PRAGMA table_info(anime_check_history)')
print('\nNew anime_check_history schema:')
for row in c.fetchall():
    print(row)

print('\nAll fixes complete!')