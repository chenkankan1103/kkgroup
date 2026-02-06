#!/bin/bash
# GCP自動診斷和修正腳本

cd /home/e193752468/kkgroup

echo "=================================="
echo "GCP Discord ID 自動修正系統"
echo "=================================="
echo ""

# 1. 診斷
echo "🔍 第一步：資料庫診斷"
python3 << 'PYEOF'
import sqlite3

db = './user_data.db'
conn = sqlite3.connect(db)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM users")
total = c.fetchone()[0]

c.execute("SELECT user_id, nickname FROM users ORDER BY user_id DESC")
users = c.fetchall()

print(f"✅ 發現用戶數: {total}\n")
print(f"{'UserID':>20} | {'Nickname':<40}")
print("-" * 65)

short_count = 0
valid_count = 0
for uid, nick in users:
    nick_str = (nick or "(無昵稱)")[:40]
    print(f"{uid:>20} | {nick_str:<40}")
    if uid < 100000000000000000:
        short_count += 1
    else:
        valid_count += 1

print(f"\n📊 統計:")
print(f"   有效ID: {valid_count}")
print(f"   無效/短ID: {short_count}")

conn.close()
PYEOF

echo ""
echo "✅ 診斷完成"
