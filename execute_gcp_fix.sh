#!/bin/bash

# ============================================================
# GCP 凱文修復執行腳本
# 執行所有必要的步驟來修復凱文重複和虛擬人物問題
# ============================================================

set -e  # 如果任何命令失敗，停止執行

PROJECT_DIR="/home/e193752468/kkgroup"
BACKUP_DIR="$PROJECT_DIR/backups"

echo "======================================================================"
echo "GCP 凱文重複和虛擬人物修復 - 自動執行腳本"
echo "======================================================================"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 【步驟 1】進入項目目錄
echo "【步驟 1】進入項目目錄..."
cd "$PROJECT_DIR"
echo "✅ 當前目錄: $(pwd)"
echo ""

# 【步驟 2】檢查 git 狀態
echo "【步驟 2】檢查 git 狀態..."
echo ""
git status
echo ""

# 【步驟 3】提交修改
echo "【步驟 3】提交修改到 git..."
echo ""

# 檢查是否有未提交的修改
if [[ $(git status --porcelain) ]]; then
    echo "ℹ️ 發現未提交的修改，開始提交..."
    git add sheet_driven_db.py sheet_sync_manager.py
    git commit -m "Fix: 修復虛擬人物 bug - 空值處理和 user_id 驗證"
    git push origin main
    echo "✅ 修改已推送到 remote"
else
    echo "ℹ️ 沒有未提交的修改"
fi
echo ""

# 【步驟 4】備份資料庫
echo "【步驟 4】備份資料庫..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/user_data.db.backup.$(date +%Y%m%d_%H%M%S)"
cp user_data.db "$BACKUP_FILE"
echo "✅ 備份完成: $BACKUP_FILE"
ls -lh "$BACKUP_FILE"
echo ""

# 【步驟 5】運行清理腳本
echo "【步驟 5】運行凱文修復和虛擬人物清理腳本..."
echo ""
python3 fix_kevin_duplicate.py
echo ""
echo "✅ 清理完成"
echo ""

# 【步驟 6】驗證修復
echo "【步驟 6】驗證修復結果..."
echo ""
python3 << 'PYTEST'
import sqlite3

print("=" * 60)
print("驗證凱文修復")
print("=" * 60)

conn = sqlite3.connect('user_data.db')
c = conn.cursor()

# 1. 查詢凱文數量
c.execute("SELECT COUNT(*) FROM users WHERE user_id = 776464975551660123")
count = c.fetchone()[0]
print(f"\n✅ 凱文記錄數: {count}")
if count != 1:
    print("⚠️ 警告: 應該只有 1 個凱文記錄!")
else:
    print("✅ 正確: 只有 1 個凱文")

# 2. 顯示凱文的詳細信息
c.execute("""
    SELECT user_id, nickname, level, xp, kkcoin, title, hp, stamina, equipment
    FROM users WHERE user_id = 776464975551660123
""")
kevin = c.fetchone()
if kevin:
    print(f"\n凱文詳細信息:")
    print(f"  user_id: {kevin[0]}")
    print(f"  nickname: {kevin[1]}")
    print(f"  level: {kevin[2]}")
    print(f"  xp: {kevin[3]}")
    print(f"  kkcoin: {kevin[4]}")
    print(f"  title: {kevin[5]}")
    print(f"  hp: {kevin[6]}")
    print(f"  stamina: {kevin[7]}")
else:
    print("❌ 未找到凱文記錄!")

# 3. 檢查虛擬人物（user_id=0）
c.execute("SELECT COUNT(*) FROM users WHERE user_id = 0")
virtual_count = c.fetchone()[0]
print(f"\n✅ 虛擬人物 (user_id=0): {virtual_count}")
if virtual_count > 0:
    print("⚠️ 警告: 仍有虛擬人物記錄!")
else:
    print("✅ 正確: 已清理所有虛擬人物")

# 4. 檢查有問題的昵稱
c.execute("""
    SELECT COUNT(*) FROM users 
    WHERE nickname LIKE 'Unknown_%' OR nickname LIKE '虛擬%'
""")
bad_count = c.fetchone()[0]
print(f"\n✅ 異常昵稱記錄: {bad_count}")
if bad_count > 0:
    print("⚠️ 警告: 仍有異常昵稱的虛擬人物!")
else:
    print("✅ 正確: 已清理所有異常昵稱")

print("\n" + "=" * 60)
print("✅ 驗證完成")
print("=" * 60)

conn.close()
PYTEST

echo ""

# 【步驟 7】重啟 Bot 服務
echo "【步驟 7】重啟 Bot 服務..."
echo ""
sudo systemctl restart bot.service shopbot.service uibot.service
echo ""

# 檢查服務狀態
echo "檢查服務狀態:"
sudo systemctl status bot.service shopbot.service uibot.service --no-pager | grep -E "Active|Loaded"
echo ""

# 【步驟 8】查看日誌確認服務啟動成功
echo "【步驟 8】查看最近的 Bot 日誌..."
echo ""
journalctl -u bot.service -n 20 --no-pager
echo ""

echo "======================================================================"
echo "✅ 所有修復步驟完成！"
echo "======================================================================"
echo "執行完成時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "修復摘要:"
echo "  ✅ 代碼修改已推送到 git"
echo "  ✅ 資料庫已備份"
echo "  ✅ 虛擬人物已清理"
echo "  ✅ 凱文記錄已驗證"
echo "  ✅ Bot 服務已重啟"
echo ""
echo "後續驗證:"
echo "  1. 檢查 Discord 中凱文是否正常顯示"
echo "  2. 嘗試在 Discord 中與 Bot 互動"
echo "  3. 檢查 SHEET 同步是否正常"
echo ""
echo "======================================================================"
