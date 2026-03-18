#!/bin/bash
# 🚀 KKCoin API 伺服器啟動腳本
# 在 GCP VM 上運行此腳本來啟動 API 伺服器

set -e

# 配置
API_PORT=${API_PORT:-5000}
API_HOST="127.0.0.1"
PROJECT_DIR="/home/e193752468/kkgroup"
VENV_PATH="${PROJECT_DIR}/.venv"
LOG_FILE="/tmp/api_server.log"

echo "=================================================="
echo "🚀 KKCoin API 伺服器啟動"
echo "=================================================="
echo "📍 目錄: $PROJECT_DIR"
echo "🔧 端口: $API_PORT"
echo "📝 日誌: $LOG_FILE"
echo "=================================================="

# 檢查虛擬環境
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ 虛擬環境不存在，正在創建..."
    cd "$PROJECT_DIR"
    python3 -m venv .venv
fi

# 啟用虛擬環境
source "$VENV_PATH/bin/activate"

# 安裝依賴
echo "📦 檢查依賴..."
pip install -q flask flask-cors python-dotenv

# 啟動 API 伺服器
echo ""
echo "💫 啟動 API 伺服器..."
cd "$PROJECT_DIR"

# 使用 nohup 在後台運行，並重定向日誌
nohup python3 api_server.py \
    --host "$API_HOST" \
    --port "$API_PORT" \
    > "$LOG_FILE" 2>&1 &

API_PID=$!

echo "✅ API 伺服器已啟動"
echo "📊 PID: $API_PID"
echo "🔗 URL: http://$API_HOST:$API_PORT"
echo ""
echo "生效的端點:"
echo "  • http://$API_HOST:$API_PORT/api/stats          (即時統計)"
echo "  • http://$API_HOST:$API_PORT/api/stats/detailed (詳細統計)"
echo "  • http://$API_HOST:$API_PORT/api/health         (健康檢查)"
echo ""
echo "⏳ 等待 3 秒讓伺服器完成初始化..."
sleep 3

# 測試 API
echo "🧪 測試 API..."
if curl -s http://$API_HOST:$API_PORT/api/health > /dev/null; then
    echo "✅ API 健康檢查通過"
else
    echo "⚠️ 無法連接 API，請檢查日誌: $LOG_FILE"
fi

echo ""
echo "💡 提示: 使用以下命令查看日誌"
echo "   tail -f $LOG_FILE"
echo ""
echo "💡 停止 API 伺服器"
echo "   kill $API_PID"
