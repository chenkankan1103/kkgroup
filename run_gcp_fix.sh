#!/bin/bash
# GCP 虛擬環境中執行 Discord ID 修正

cd /home/e193752468/kkgroup

# 激活虛擬環境
source venv/bin/activate

echo "================================================================"
echo "🔍 Discord ID 修正工具 - GCP 版本"
echo "================================================================"
echo ""
echo "環境:"
echo "  Python: $(python3 --version)"
echo "  目錄: $(pwd)"
echo ""

# 執行診斷預覽（不修改資料庫）
python3 << 'EOF'
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()

DB_PATH = './user_data.db'

print("📊 === 現有資料庫狀態 ===\n")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 獲取統計信息
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT user_id, nickname FROM users ORDER BY user_id DESC")
    users = cursor.fetchall()
    
    print(f"用戶總數: {total}\n")
    print(f"{'UserID':>20} | {'Nickname':<40}")
    print("-" * 65)
    
    short_ids = []
    valid_ids = []
    test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB']
    
    for user_id, nick in users:
        nick_str = (nick or '(無昵稱)')[:40]
        print(f"{user_id:>20} | {nick_str:<40}")
        
        if user_id < 100000000000000000:
            short_ids.append((user_id, nick))
        else:
            valid_ids.append((user_id, nick))
    
    print(f"\n📈 統計:")
    print(f"  ✅ 有效ID (18位): {len(valid_ids)}")
    print(f"  ❌ 無效/短ID: {len(short_ids)}")
    
    if short_ids:
        print(f"\n🗑️ 需要刪除的無效ID:")
        for sid, nick in short_ids:
            print(f"    - {sid} ({nick})")
    
    conn.close()
    
except Exception as e:
    print(f"❌ 錯誤: {e}")
    sys.exit(1)

print("\n✅ 診斷完成")
EOF

echo ""
echo "================================================================"
echo "下一步："
echo "  選項1: 自動刪除所有短ID"
echo "  選項2: 手動執行 python3 fix_user_ids.py"
echo "  選項3: 取消操作"
echo "================================================================"
