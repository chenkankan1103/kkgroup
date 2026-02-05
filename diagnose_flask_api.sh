#!/bin/bash
# GCP Flask API 錯誤診斷

echo "🔍 檢查 Flask API 錯誤日誌..."
echo "======================================"
echo ""

# 1. 檢查 Flask 進程
echo "1️⃣ 查看 Flask 進程..."
ps aux | grep gunicorn | grep -v grep

echo ""

# 2. 檢查 Flask 日誌（如果有）
echo "2️⃣ 查找 Flask 日誌文件..."
find ~ -name "*.log" -type f 2>/dev/null | head -10

echo ""

# 3. 檢查 systemd 日誌
echo "3️⃣ 檢查 Flask API 的 systemd 日誌..."
if systemctl status sheet-sync-api &>/dev/null; then
    echo "✅ sheet-sync-api.service 存在"
    journalctl -u sheet-sync-api.service -n 50 --no-pager
else
    echo "⚠️ sheet-sync-api.service 不存在"
fi

echo ""

# 4. 測試 API 的詳細響應
echo "4️⃣ 測試 API 詳細響應..."
echo ""
echo "HTTP Headers + Body:"
curl -v http://localhost:5000/api/health 2>&1 | head -40

echo ""

# 5. 測試同步端點（帶詳細信息）
echo "5️⃣ 測試同步端點..."
cat << 'EOF' > /tmp/test_sync.json
{
  "headers": ["user_id", "nickname", "level"],
  "rows": [
    ["123456789", "TestPlayer", "1"]
  ]
}
EOF

echo "📤 發送測試請求..."
curl -X POST http://localhost:5000/api/sync \
  -H "Content-Type: application/json" \
  -d @/tmp/test_sync.json \
  -w "\n\nHTTP Status: %{http_code}\n" 2>&1

echo ""

# 6. 檢查 Python 環境
echo "6️⃣ 檢查 Python 環境..."
which python3
python3 --version
pip3 list | grep -E "flask|gunicorn|sheet"

echo ""

# 7. 測試 Python 導入
echo "7️⃣ 測試 Python 導入..."
python3 -c "from sheet_sync_api import app; print('✅ Flask 應用導入成功')" 2>&1

echo ""
echo "======================================"
echo "診斷完成"
