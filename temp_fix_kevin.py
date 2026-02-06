import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = "/home/e193752468/kkgroup/user_data.db"
BACKUP_DIR = "/tmp/kkgroup_backups"  # 使用 /tmp 因為權限受限

print("=" * 80)
print("凱文重複和虛擬人物修復工具")
print("=" * 80)

# 【步驟1】備份
print("\n【步驟1】備份資料庫...")
Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{BACKUP_DIR}/user_data_backup_kevin_fix_{timestamp}.db"
shutil.copy2(DB_PATH, backup_path)
print(f"✅ 備份完成: {backup_path}")

# 【步驟2】診斷
print("\n【步驟2】診斷凱文重複問題...")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT user_id, nickname, level, xp, kkcoin
    FROM users 
    WHERE user_id = 776464975551660123 OR nickname LIKE '%凱文%'
    ORDER BY user_id DESC
""")

kevin_records = cursor.fetchall()
print(f"找到 {len(kevin_records)} 個凱文相關記錄")

virtual_kevins = []
for record in kevin_records:
    print(f"\n  user_id: {record['user_id']}")
    print(f"  nickname: {record['nickname']}")
    print(f"  level: {record['level']}")
    print(f"  kkcoin: {record['kkcoin']}")
    
    if record['user_id'] != 776464975551660123:
        virtual_kevins.append(record['user_id'])
        print(f"  ➜ 虛擬人物")

conn.close()

# 【步驟3】修復
print("\n【步驟3】修復凱文重複問題...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

if virtual_kevins:
    print(f"刪除 {len(virtual_kevins)} 個虛擬人物凱文")
    for user_id in virtual_kevins:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        print(f"  ✓ 刪除 user_id {user_id}")

cursor.execute("""
    INSERT OR REPLACE INTO users 
    (user_id, nickname, level, xp, kkcoin, title, hp, stamina)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (776464975551660123, "凱文", 4, 100000, 100006, '', 100, 100))
print(f"  ✓ 確保原始凱文 user_id 776464975551660123 存在")

conn.commit()

# 【步驟4】驗證
print("\n【步驟4】驗證修復...")
cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = 776464975551660123")
kevin_count = cursor.fetchone()[0]
print(f"✅ 凱文記錄數: {kevin_count}")

cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = 0")
virtual_count = cursor.fetchone()[0]
print(f"✅ 虛擬人物 (user_id=0): {virtual_count}")

conn.close()

print("\n" + "=" * 80)
print("✅ 所有修復操作完成")
print("=" * 80)
