#!/bin/bash

echo "🚀 啟動 Flask API..."
cd /home/e193752468/kkgroup

# 停止舊的 gunicorn 進程（如果有）
echo "停止舊的 gunicorn 進程..."
pkill -f "gunicorn.*sheet_sync_api" 2>/dev/null || true
sleep 1

# 啟動 Flask API
echo "啟動 gunicorn..."
/home/e193752468/kkgroup/venv/bin/gunicorn \
    -w 4 \
    -b 0.0.0.0:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    sheet_sync_api:app > /tmp/gunicorn.log 2>&1 &

GUNICORN_PID=$!
echo "Gunicorn PID: $GUNICORN_PID"

# 等待一秒讓服務啟動
sleep 2

# 檢查服務是否啟動成功
if ps -p $GUNICORN_PID > /dev/null; then
    echo "✅ Flask API 已啟動"
    echo "日誌: tail -f /tmp/gunicorn.log"
else
    echo "❌ Flask API 啟動失敗"
    cat /tmp/gunicorn.log
    exit 1
fi
