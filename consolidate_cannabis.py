import sqlite3
from datetime import datetime
from status_dashboard import add_log

db_path = '/home/e193752468/kkgroup/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

add_log("bot", "=== 統一大麻系統到 users 表 ===")

# 步驟 1：確認獨立表為空
add_log("bot", "1️⃣ 驗證獨立表狀態")
c.execute('SELECT COUNT(*) FROM cannabis_plants')
plants_count = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM cannabis_inventory')
inventory_count = c.fetchone()[0]
add_log("bot", f"   cannabis_plants: {plants_count} 筆")
add_log("bot", f"   cannabis_inventory: {inventory_count} 筆")

if plants_count > 0 or inventory_count > 0:
    add_log("bot", "❌ 表中有數據，放棄")
    conn.close()
    exit(1)

add_log("bot", "✅ 表為空，可以刪除")

# 步驟 2：刪除獨立表
add_log("bot", "2️⃣ 刪除獨立表")
c.execute('DROP TABLE IF EXISTS cannabis_plants')
add_log("bot", "   ✅ 刪除 cannabis_plants")
c.execute('DROP TABLE IF EXISTS cannabis_inventory')
add_log("bot", "   ✅ 刪除 cannabis_inventory")

# 步驟 3：在 users 表添加大麻字段（如果不存在）
add_log("bot", "3️⃣ 在 users 表添加大麻相關字段")

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
        add_log("bot", f"   ✅ 添加欄位: {field}")
    else:
        add_log("bot", f"   ℹ️ 欄位已存在: {field}")

conn.commit()

# 步驟 4：驗證
add_log("bot", "4️⃣ 驗證結果")
c.execute("PRAGMA table_info(users)")
all_cols = [row[1] for row in c.fetchall()]
add_log("bot", f"   users 表現有欄位數: {len(all_cols)}")

has_new_fields = all([f in all_cols for f in new_fields])
add_log("bot", f"   包含大麻相關欄位: {'✅' if has_new_fields else '❌'}")

# 檢查是否還有獨立表
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cannabis%'")
remaining = c.fetchall()
add_log("bot", f"   剩餘的 cannabis* 表: {len(remaining)} 個")

conn.close()

add_log("bot", "✅ 大麻系統統一完成！")
