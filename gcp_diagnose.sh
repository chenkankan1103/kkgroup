#!/bin/bash
# GCP 環境診斷指令

echo "🔍 GCP kkgroup 專案環境診斷"
echo "======================================"
echo ""

# 1. 檢查 user_data.db
echo "1️⃣ 檢查資料庫檔案..."
if [ -f "user_data.db" ]; then
    echo "✅ user_data.db 存在"
    ls -lh user_data.db
    echo ""
    echo "   資料庫統計："
    sqlite3 user_data.db ".tables"
    echo ""
    echo "   users 表結構："
    sqlite3 user_data.db "PRAGMA table_info(users);" | head -20
    echo ""
    echo "   用戶數量："
    sqlite3 user_data.db "SELECT COUNT(*) as total_users FROM users;"
else
    echo "❌ user_data.db 不存在"
    echo "   位置：$(pwd)/user_data.db"
fi

echo ""

# 2. 檢查 Flask 伺服器
echo "2️⃣ 檢查 Flask 伺服器狀態..."
if pgrep -f "python.*sheet_sync_api" > /dev/null; then
    echo "✅ Flask 伺服器運行中"
    ps aux | grep "sheet_sync_api" | grep -v grep
else
    echo "❌ Flask 伺服器未運行"
fi

echo ""

# 3. 檢查 Bot 狀態
echo "3️⃣ 檢查 Discord Bot 狀態..."
systemctl status bot.service --no-pager

echo ""

# 4. 驗證 API 連接
echo "4️⃣驗證 API 連接..."
curl -s http://localhost:5000/api/health | jq . || echo "❌ API 無回應"

echo ""

# 5. 檢查日誌
echo "5️⃣ 最近的 Bot 日誌（最後 20 行）..."
if [ -f "bot.log" ]; then
    tail -20 bot.log
else
    echo "⚠️ 日誌檔案不存在"
fi

echo ""
echo "======================================"
echo "診斷完成"
