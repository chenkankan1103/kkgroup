#!/bin/bash
# BOT 重啟腳本

echo "=================================================="
echo "🚀 正在重啟所有 BOT 服務..."
echo "=================================================="
echo ""

SERVICES=("bot.service" "shopbot.service" "uibot.service")

for SERVICE in "${SERVICES[@]}"; do
    echo "⏹️  停止 $SERVICE..."
    sudo systemctl stop "$SERVICE"
    sleep 1
done

echo ""
echo "⏳ 等待 3 秒..."
sleep 3

echo ""
echo "▶️  啟動 BOT 服務..."

for SERVICE in "${SERVICES[@]}"; do
    echo "🚀 啟動 $SERVICE..."
    sudo systemctl start "$SERVICE"
    sleep 2
done

echo ""
echo "📊 驗證服務狀態..."
echo "=================================================="

for SERVICE in "${SERVICES[@]}"; do
    STATUS=$(systemctl is-active "$SERVICE")
    if [ "$STATUS" = "active" ]; then
        echo "✅ $SERVICE: $STATUS"
    else
        echo "❌ $SERVICE: $STATUS"
    fi
done

echo "=================================================="
echo ""
echo "進程檢查："
ps aux | grep -E 'python.*bot|gunicorn' | grep -v grep

echo ""
echo "Flask API 檢查 (port 5000)："
ss -ltnp | grep ':5000' | head -1 || echo "⚠️  Flask API 未監聽"

echo ""
echo "=================================================="
echo "✅ 重啟完成！"
echo "=================================================="
echo ""
echo "BOT 應該在 1-2 分鐘內上線到 Discord。"
