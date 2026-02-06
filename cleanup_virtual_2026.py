import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = "/home/e193752468/kkgroup/user_data.db"
BACKUP_DIR = "/tmp/kkgroup_backups"

print("=" * 80)
print("虛擬人物清除工具")
print("=" * 80)

# 【步驟1】備份
print("\n【步驟1】備份資料庫...")
Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{BACKUP_DIR}/user_data_backup_virtual_fix_{timestamp}.db"
import shutil
shutil.copy2(DB_PATH, backup_path)
print(f"✅ 備份完成: {backup_path}")

# 【步驟2】診斷虛擬人物
print("\n【步驟2】診斷虛擬人物...")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 尋找虛擬人物：user_id 不為 0 但 kkcoin 為 NULL 的用戶
cursor.execute("""
    SELECT user_id, nickname, level, xp, kkcoin
    FROM users 
    WHERE user_id != 0 AND (kkcoin IS NULL OR level IS NULL OR xp IS NULL)
    ORDER BY user_id DESC
""")

virtual_records = cursor.fetchall()
print(f"找到 {len(virtual_records)} 個虛擬人物：\n")

virtual_user_ids = []
for record in virtual_records:
    print(f"  user_id: {record['user_id']}")
    print(f"  nickname: {record['nickname']}")
    print(f"  level: {record['level']}, xp: {record['xp']}, kkcoin: {record['kkcoin']}")
    if record['user_id']:
        virtual_user_ids.append(record['user_id'])
    print()

conn.close()

# 【步驟3】清除虛擬人物
print(f"\n【步驟3】清除虛擬人物...")
if virtual_user_ids:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"刪除 {len(virtual_user_ids)} 個虛擬人物...")
    for user_id in virtual_user_ids:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        print(f"  ✓ 刪除 user_id {user_id}")
    
    conn.commit()
    conn.close()
    print(f"✅ 已刪除 {len(virtual_user_ids)} 個虛擬人物")
else:
    print("✅ 沒有虛擬人物需要刪除")

# 【步驟4】驗證
print("\n【步驟4】驗證...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT count(*) FROM users WHERE kkcoin IS NULL AND user_id != 0")
null_kkcoin_count = cursor.fetchone()[0]
print(f"✅ kkcoin 為 NULL 的用戶（user_id != 0）: {null_kkcoin_count}")

cursor.execute("SELECT count(*) FROM users WHERE level IS NULL AND user_id != 0")
null_level_count = cursor.fetchone()[0]
print(f"✅ level 為 NULL 的用戶（user_id != 0）: {null_level_count}")

cursor.execute("SELECT count(*) FROM users WHERE user_id = 0")
zero_id_count = cursor.fetchone()[0]
print(f"✅ user_id 為 0 的用戶: {zero_id_count}")

cursor.execute("SELECT count(*) FROM users")
total_count = cursor.fetchone()[0]
print(f"✅ 總用戶數: {total_count}")

conn.close()

print("\n" + "=" * 80)
print("✅ 虛擬人物清除完成")
print("=" * 80)
