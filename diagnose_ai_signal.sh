#!/bin/bash
# AI 中控室訊號診斷腳本 - 完整檢查

echo "======================================"
echo "🔍 AI 中控室訊號診斷 ($(date))"
echo "======================================"

echo ""
echo "📊 === 第1部分：服務狀態 ==="
echo "🤖 Bot 服務狀態："
sudo systemctl status bot.service --no-pager | grep -E "Active|PID|Main"

echo ""
echo "🛒 Shopbot 服務狀態："
sudo systemctl status shopbot.service --no-pager | grep -E "Active|PID|Main"

echo ""
echo "📡 API 服務狀態："
sudo systemctl status kkgroup-api.service --no-pager | grep -E "Active|PID|Main"

echo ""
echo "🌐 === 第2部分：網絡連接 ==="
echo "監聽的端口："
sudo netstat -tlnp 2>/dev/null | grep -E "LISTEN.*python|LISTEN.*nginx|LISTEN.*cloudflare" || echo "無法獲取端口信息"

echo ""
echo "🔗 Python API 進程檢查："
ps aux | grep "python3.*unified_api.py" | grep -v grep || echo "API 進程未找到"

echo ""
echo "🌀 === 第3部分：API 響應測試 ==="
echo "本地 API 端點測試 (localhost:5000)："
curl -s http://127.0.0.1:5000/api/test -H "Content-Type: application/json" -d '{}' | head -c 200
echo ""

echo ""
echo "🌐 === 第4部分：隧道狀態 ==="
echo "隧道進程狀態："
sudo systemctl status cloudflared.service --no-pager | grep -E "Active|PID"

echo ""
echo "隧道最近錯誤（最近 10 行）："
sudo journalctl -u cloudflared.service -n 10 --no-pager | grep -E "ERR|WRN" || echo "無最近錯誤"

echo ""
echo "🔑 === 第5部分：AI API 配置檢查 ==="
echo "API 配置檢查："
if grep -q "AI_API_KEY=" /home/e193752468/kkgroup/.env; then
    echo "✅ AI_API_KEY: 已配置"
else
    echo "❌ AI_API_KEY: 未配置"
fi

if grep -q "GROQ_API_KEY=" /home/e193752468/kkgroup/.env; then
    echo "✅ GROQ_API_KEY: 已配置"
else
    echo "❌ GROQ_API_KEY: 未配置"
fi

echo ""
echo "📋 === 第6部分：最近的 AI 相關日誌 ==="
echo "Bot AI 調用最近 5 筆結果："
sudo journalctl -u bot.service -n 50 --no-pager | grep -E "AI|API|call_ai" | tail -5 || echo "無 AI 相關日誌"

echo ""
echo "======================================"
echo "✅ 診斷完成！"
echo "======================================"
