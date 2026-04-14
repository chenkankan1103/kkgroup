#!/bin/bash
# KK 群紙娃娃 RPG 遊戲 - 快速啟動腳本 (macOS/Linux)

cd "$(dirname "$0")"

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║   🎮 KK 群紙娃娃 RPG 遊戲 - 啟動腳本        ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# 檢查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 錯誤：找不到 Python3"
    echo "請確保 Python3 已安裝"
    exit 1
fi

# 檢查依賴
echo "📦 檢查依賴..."
python3 -c "import flask; import flask_cors" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  缺少依賴，正在安裝..."
    pip3 install -r requirements.txt
fi

# 啟動 Flask API
echo ""
echo "🚀 啟動 Flask API 伺服器..."
echo "📍 訪問地址: http://localhost:5000"
echo "🎮 遊戲頁面: http://localhost:5000/rpg-game.html?user_id=YOUR_USER_ID"
echo ""
echo "✅ 伺服器已啟動，按 Ctrl+C 停止"
echo ""

python3 unified_api.py
