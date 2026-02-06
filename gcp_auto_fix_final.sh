#!/bin/bash
# GCP 完整修正腳本 - 自動化版本
# 在虛擬環境中執行，無需交互

set -e  # 任何錯誤立即退出

cd /home/e193752468/kkgroup
source venv/bin/activate

echo "=================================="
echo "🔧 GCP Discord ID 自動修正"
echo "=================================="
echo ""

# Step 1: Backup
echo "📦 Step 1: 備份資料庫..."
cp user_data.db user_data.db.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ 備份完成"

# Step 2: Diagnose
echo ""
echo "🔍 Step 2: 掃描資料庫..."
python3 << 'DIAGNOSE_SCRIPT'
import sqlite3
conn = sqlite3.connect('user_data.db')
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM users")
total = c.fetchone()[0]
c.execute("SELECT user_id, nickname FROM users ORDER BY user_id DESC")
users = c.fetchall()
print(f"✅ 掃描完成: {total} 個用戶\n")
conn.close()
DIAGNOSE_SCRIPT

# Step 3: Clean
echo ""
echo "🧹 Step 3: 清理短ID和測試ID..."
python3 << 'CLEANUP_SCRIPT'
import sqlite3

conn = sqlite3.connect('user_data.db')
c = conn.cursor()

# 測試ID模式
test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB', 'UserA', 'UserB', 'UserC', 'UserD', 'UserH']

# 1. 刪除所有短ID (< 100000000000000000)
c.execute("SELECT user_id, nickname FROM users WHERE user_id < 100000000000000000")
short_ids = c.fetchall()
for uid, nick in short_ids:
    c.execute("DELETE FROM users WHERE user_id = ?", (uid,))
    print(f"  🗑️ 已刪除短ID: {uid:20d} | {nick}")

# 2. 刪除測試昵稱的有效ID
c.execute("SELECT user_id, nickname FROM users WHERE user_id >= 100000000000000000")
valid_ids = c.fetchall()
deleted_count = 0
for uid, nick in valid_ids:
    if nick and any(p in nick.lower() for p in test_patterns):
        c.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        print(f"  🗑️ 已刪除測試ID: {uid:20d} | {nick}")
        deleted_count += 1

conn.commit()
total_deleted = len(short_ids) + deleted_count
conn.close()
print(f"\n✅ 清理完成: 刪除了 {total_deleted} 個無效/測試ID")
CLEANUP_SCRIPT

# Step 4: Verify
echo ""
echo "✓ Step 4: 驗證修正..."
python3 << 'VERIFY_SCRIPT'
import sqlite3
conn = sqlite3.connect('user_data.db')
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM users")
final = c.fetchone()[0]
c.execute("SELECT user_id, nickname FROM users ORDER BY user_id")
valid = c.fetchall()
print(f"✅ 驗證完成: 現有 {final} 個有效用戶\n")
if valid:
    print(f"{'UserID':>20} | {'Nickname':<40}")
    print("-" * 65)
    for uid, nick in valid:
        print(f"{uid:>20} | {(nick or '(無)')[:40]}")
conn.close()
VERIFY_SCRIPT

echo ""
echo "=================================="
echo "✅ 修正完成！"
echo "=================================="
echo "後續步驟："
echo "  - 重啟 Bot: systemctl restart bot"
echo "  - 重啟 UIBot: systemctl restart uibot"
