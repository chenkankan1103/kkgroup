import sqlite3
from datetime import datetime

db_path = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== 統一大麻系統到 users 表 ===\n")

# 步驟 1：確認獨立表為空
print("1️⃣ 驗證獨立表狀態")
c.execute('SELECT COUNT(*) FROM cannabis_plants')
plants_count = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM cannabis_inventory')
inventory_count = c.fetchone()[0]
print(f"   cannabis_plants: {plants_count} 筆")
print(f"   cannabis_inventory: {inventory_count} 筆")

if plants_count > 0 or inventory_count > 0:
    print("❌ 表中有數據，放棄")
    conn.close()
    exit(1)

print("✅ 表為空，可以刪除\n")

# 步驟 2：刪除獨立表
print("2️⃣ 刪除獨立表")
c.execute('DROP TABLE IF EXISTS cannabis_plants')
print("   ✅ 刪除 cannabis_plants")
c.execute('DROP TABLE IF EXISTS cannabis_inventory')
print("   ✅ 刪除 cannabis_inventory")

# 步驟 3：在 users 表添加大麻字段（如果不存在）
print("\n3️⃣ 在 users 表添加大麻相關字段")

# 獲取現有欄位
c.execute("PRAGMA table_info(users)")
existing_cols = {row[1] for row in c.fetchall()}

new_fields = {
    'cannabis_plants': "TEXT DEFAULT '[]'",
    'cannabis_inventory': "TEXT DEFAULT '{}'"
}

for field, col_type in new_fields.items():
    if field not in existing_cols:
        c.execute(f'ALTER TABLE users ADD COLUMN "{field}" {col_type}')
        print(f"   ✅ 添加欄位: {field}")
    else:
        print(f"   ℹ️ 欄位已存在: {field}")

conn.commit()

# 步驟 4：驗證
print("\n4️⃣ 驗證結果")
c.execute("PRAGMA table_info(users)")
all_cols = [row[1] for row in c.fetchall()]
print(f"   users 表現有欄位數: {len(all_cols)}")

has_new_fields = all([f in all_cols for f in new_fields])
print(f"   包含大麻相關欄位: {'✅' if has_new_fields else '❌'}")

# 檢查是否還有獨立表
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cannabis%'")
remaining = c.fetchall()
print(f"   剩餘的 cannabis* 表: {len(remaining)} 個")

conn.close()

print("\n✅ 大麻系統統一完成！")
