import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = "/home/e193752468/kkgroup/user_data.db"
BACKUP_DIR = "/tmp/kkgroup_backups"

print("=" * 80)
print("幽靈帳號完整清除工具")
print("=" * 80)

# 【步驟1】備份
print("\n【步驟1】備份資料庫...")
Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{BACKUP_DIR}/user_data_backup_ghost_fix_{timestamp}.db"
import shutil
shutil.copy2(DB_PATH, backup_path)
print(f"✅ 備份完成: {backup_path}")

# 【步驟2】診斷幽靈帳號
print("\n【步驟2】診斷幽靈帳號...")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. 同名異 ID 的幽靈帳號
cursor.execute("""
    SELECT user_id, nickname, level, xp, kkcoin
    FROM users 
    WHERE nickname IN (
        SELECT nickname FROM users GROUP BY nickname HAVING count(*) > 1
    )
    ORDER BY nickname, user_id
""")

duplicate_records = cursor.fetchall()
ghost_to_delete = []

print(f"\n【同名異 ID 幽靈帳號】找到 {len(duplicate_records)} 筆記錄：")
processed_nicknames = set()

for record in duplicate_records:
    nickname = record['nickname']
    if nickname in processed_nicknames:
        continue
    
    processed_nicknames.add(nickname)
    
    # 查詢該 nickname 的所有記錄
    cursor.execute("""
        SELECT user_id, nickname, level, xp, kkcoin
        FROM users 
        WHERE nickname = ?
        ORDER BY user_id
    """, (nickname,))
    
    same_name_records = cursor.fetchall()
    
    print(f"\n  📋 {nickname}:")
    for i, rec in enumerate(same_name_records, 1):
        print(f"     [{i}] user_id={rec['user_id']}, level={rec['level']}, xp={rec['xp']}, kkcoin={rec['kkcoin']}")
    
    # 保留最小 user_id，刪除其他
    if len(same_name_records) > 1:
        min_user_id = same_name_records[0]['user_id']
        print(f"     → 保留 user_id {min_user_id}，刪除其他 {len(same_name_records) - 1} 個幽靈")
        for rec in same_name_records[1:]:
            ghost_to_delete.append(rec['user_id'])

# 2. 其他異常記錄
print(f"\n【其他異常記錄】")

# user_id 為 0 的記錄
cursor.execute("SELECT count(*) FROM users WHERE user_id = 0")
zero_id_count = cursor.fetchone()[0]
if zero_id_count > 0:
    print(f"  - user_id = 0: {zero_id_count} 筆 ⚠️")
    cursor.execute("SELECT user_id FROM users WHERE user_id = 0")
    for rec in cursor.fetchall():
        ghost_to_delete.append(rec['user_id'])

# 負數 user_id 的記錄
cursor.execute("SELECT count(*) FROM users WHERE user_id < 0")
negative_id_count = cursor.fetchone()[0]
if negative_id_count > 0:
    print(f"  - user_id < 0: {negative_id_count} 筆 ⚠️")
    cursor.execute("SELECT user_id FROM users WHERE user_id < 0")
    for rec in cursor.fetchall():
        ghost_to_delete.append(rec['user_id'])

# 空 nickname 的記錄
cursor.execute("SELECT count(*) FROM users WHERE nickname IS NULL OR nickname = ''")
empty_nickname_count = cursor.fetchone()[0]
if empty_nickname_count > 0:
    print(f"  - nickname 為空: {empty_nickname_count} 筆 ⚠️")
    cursor.execute("SELECT user_id FROM users WHERE nickname IS NULL OR nickname = ''")
    for rec in cursor.fetchall():
        ghost_to_delete.append(rec['user_id'])

conn.close()

# 去重
ghost_to_delete = list(set(ghost_to_delete))

print(f"\n【清除計畫】")
print(f"總共需要刪除 {len(ghost_to_delete)} 個幽靈帳號")
print(f"刪除的 user_id: {sorted(ghost_to_delete)}")

# 【步驟3】執行刪除
print(f"\n【步驟3】執行刪除...")
if ghost_to_delete:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for user_id in sorted(ghost_to_delete):
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        print(f"  ✓ 刪除 user_id {user_id}")
    
    conn.commit()
    conn.close()
    print(f"✅ 已刪除 {len(ghost_to_delete)} 個幽靈帳號")
else:
    print("✅ 沒有幽靈帳號需要刪除")

# 【步驟4】驗證
print("\n【步驟4】驗證...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT count(*) FROM users")
total_count = cursor.fetchone()[0]
print(f"✅ 總用戶數: {total_count}")

cursor.execute("SELECT count(*) FROM users WHERE nickname IN (SELECT nickname FROM users GROUP BY nickname HAVING count(*) > 1)")
duplicate_count = cursor.fetchone()[0]
print(f"✅ 重複 nickname: {duplicate_count}")

cursor.execute("SELECT count(*) FROM users WHERE user_id = 0")
zero_id_count = cursor.fetchone()[0]
print(f"✅ user_id = 0: {zero_id_count}")

cursor.execute("SELECT count(*) FROM users WHERE user_id < 0")
negative_id_count = cursor.fetchone()[0]
print(f"✅ user_id < 0: {negative_id_count}")

cursor.execute("SELECT count(*) FROM users WHERE nickname IS NULL OR nickname = ''")
empty_nickname_count = cursor.fetchone()[0]
print(f"✅ nickname 為空: {empty_nickname_count}")

# 顯示最終的合法用戶
print(f"\n【最終合法用戶列表】")
cursor.execute("SELECT user_id, nickname, level, xp, kkcoin FROM users ORDER BY user_id DESC")
final_users = cursor.fetchall()
for user in final_users:
    user_id, nickname, level, xp, kkcoin = user
    print(f"  {user_id:>20} | {str(nickname):>20} | L{level} | XP:{xp} | ${kkcoin}")

conn.close()

print("\n" + "=" * 80)
print("✅ 幽靈帳號清除完成")
print("=" * 80)
