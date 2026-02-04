import sqlite3

conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

print("📋 users 表的列定義:")
cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]}")

print("\n🔍 檢查重複的 user_id:")
cursor.execute("SELECT user_id, COUNT(*) as cnt FROM users GROUP BY user_id HAVING COUNT(*) > 1 LIMIT 10")
rows = cursor.fetchall()
if rows:
    print("🔴 發現重複記錄:")
    for row in rows:
        print(f"  user_id: {row[0]}, 計數: {row[1]}")
else:
    print("✅ 沒有重複的 user_id")

print("\n📊 users 表總記錄數:")
cursor.execute("SELECT COUNT(*) FROM users")
print(f"  總計: {cursor.fetchone()[0]} 筆記錄")

conn.close()
