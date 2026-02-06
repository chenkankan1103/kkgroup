import sqlite3

current_db = '/home/e193752468/kkgroup/user_data.db'

conn = sqlite3.connect(current_db)
c = conn.cursor()

print("查詢凱文（用 ID），確認 KKCOIN = 100000\n")

# 查詢新 ID（現在 DB 中的）
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = 776464975551660123')
result = c.fetchone()
if result:
    print(f"✅ 凱文在 DB 中: {result}")
    print(f"   昵稱: {result[0]}")
    print(f"   ID: {result[1]}")
    print(f"   KKCOIN: {result[2]}")
    if result[2] == 100000:
        print("   ✅ KKCOIN 正確修復到 100000")
    else:
        print(f"   ❌ KKCOIN 應該是 100000，但現在是 {result[2]}")
else:
    print("❌ 凱文（ID 776464975551660123）未找到")

# 檢查是否還有舊 ID
c.execute('SELECT nickname, user_id, kkcoin FROM users WHERE user_id = 776464975551660160')
result = c.fetchone()
if result:
    print(f"\n⚠️ 舊 ID 仍存在: {result}")
else:
    print("\n✅ 舊 ID 已清理")

conn.close()
