#!/bin/bash

# 診斷 SHEET 同步問題

API_URL="http://localhost:5000"
DB_PATH="user_data.db"

echo "=================================================="
echo "🔍 SHEET 同步診斷工具"
echo "=================================================="
echo ""

# 1. 測試 API 連接
echo "1️⃣ 測試 API 連接..."
if curl -s "$API_URL/api/health" > /dev/null 2>&1; then
    echo "✅ API 連接正常"
    curl -s "$API_URL/api/health" | jq .
else
    echo "❌ API 無響應"
    exit 1
fi

echo ""

# 2. 檢查數據庫存在
echo "2️⃣ 檢查數據庫..."
if [ -f "$DB_PATH" ]; then
    echo "✅ 數據庫存在: $DB_PATH"
    ls -lh "$DB_PATH"
else
    echo "❌ 數據庫不存在: $DB_PATH"
    exit 1
fi

echo ""

# 3. 檢查數據庫內的用戶
echo "3️⃣ 檢查數據庫中的用戶..."
echo "📊 用戶總數:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM users;" | xargs echo "   總計:"

echo ""
echo "📋 用户清單（前 5 筆）:"
sqlite3 -header -column "$DB_PATH" "SELECT user_id, user_name, level, kkcoin FROM users LIMIT 5;"

echo ""

# 4. 檢查表結構
echo "4️⃣ 檢查表結構..."
echo "📐 users 表欄位:"
sqlite3 -header -column "$DB_PATH" "PRAGMA table_info(users);" | head -20

echo ""

# 5. 測試 API 同步端點
echo "5️⃣ 測試 API /api/sync 端點..."
echo ""
echo "準備測試數據..."

# 創建測試 JSON
TEST_DATA='{
  "headers": ["user_id", "user_name", "level", "kkcoin"],
  "rows": [
    ["999888777", "TestUser_Sync", "10", "500"],
    ["999888778", "TestUser_Sync2", "5", "100"]
  ]
}'

echo "📤 發送測試數據："
echo "$TEST_DATA" | jq .

echo ""
echo "⏳ 呼叫 /api/sync..."

RESPONSE=$(curl -s -X POST "$API_URL/api/sync" \
  -H "Content-Type: application/json" \
  -d "$TEST_DATA")

echo "📥 API 回應："
echo "$RESPONSE" | jq .

echo ""

# 6. 驗證數據是否寫入
echo "6️⃣ 驗證測試數據是否寫入數據庫..."
INSERTED_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM users WHERE user_id IN (999888777, 999888778);")
echo "✅ 寫入的測試用戶數: $INSERTED_COUNT"

if [ "$INSERTED_COUNT" -gt "0" ]; then
    echo "📊 檢查寫入的數據："
    sqlite3 -header -column "$DB_PATH" "SELECT user_id, user_name, level, kkcoin FROM users WHERE user_id IN (999888777, 999888778);"
    
    # 清理測試數據
    echo ""
    echo "🧹 清理測試數據..."
    sqlite3 "$DB_PATH" "DELETE FROM users WHERE user_id IN (999888777, 999888778);"
    echo "✅ 测试数据已删除"
else
    echo "❌ 沒有寫入任何數據！"
    echo ""
    echo "🔍 可能的原因："
    echo "   1. API 錯誤：檢查 Flask 日誌"
    echo "   2. 數據庫寫入失敗"
    echo "   3. PRIMARY KEY 衝突"
fi

echo ""
echo "7️⃣ 檢查 Flask 錯誤日誌..."
echo ""
if [ -f "gunicorn.log" ]; then
    echo "📋 最後 10 行 gunicorn 日誌："
    tail -10 gunicorn.log
else
    echo "⚠️ gunicorn.log 不存在"
fi

echo ""
echo "=================================================="
echo "✅ 診斷完成"
echo "=================================================="
