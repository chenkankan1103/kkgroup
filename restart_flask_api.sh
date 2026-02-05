#!/bin/bash
# GCP 修復並重啟 Flask API

echo "🔧 GCP Flask API 修復與重啟指南"
echo "======================================"
echo ""

# 1. 等待 git pull（如果啟用了自動部署）
echo "1️⃣ 等待 GitHub 自動部署..."
echo "   如果啟用了自動拉取，等待 5-10 秒..."
sleep 5
git status

echo ""

# 2. 手動拉取最新代碼
echo "2️⃣ 從 GitHub 拉取最新代碼..."
git pull origin main

echo ""

# 3. 檢查 Python 語法
echo "3️⃣ 檢查 Python 語法..."
python3 -m py_compile sheet_sync_api.py
if [ $? -eq 0 ]; then
    echo "✅ 語法正確"
else
    echo "❌ 語法錯誤，請檢查代碼"
    exit 1
fi

echo ""

# 4. 停止舊的 gunicorn 進程
echo "4️⃣ 停止舊的 gunicorn 進程..."
pkill -f "gunicorn.*sheet_sync_api"
sleep 2
echo "✅ 舊進程已停止"

echo ""

# 5. 測試簡化版 Flask（驗證 Python 環境）
echo "5️⃣ 測試簡化版 Flask..."
echo "   (會在 5 秒後停止)"
timeout 5 python3 test_flask_simple.py 2>&1 || true

echo ""

# 6. 直接啟動 gunicorn（前景運行，便於查看日誌）
echo "6️⃣ 啟動 gunicorn..."
echo ""
echo "   命令: gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 sheet_sync_api:app"
echo ""

# 使用 nohup 在後台運行，並保存日誌
nohup gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --access-logfile - --error-logfile - sheet_sync_api:app > gunicorn.log 2>&1 &
GUNICORN_PID=$!
echo "✅ gunicorn 已啟動 (PID: $GUNICORN_PID)"

echo ""

# 7. 等待啟動完成
echo "7️⃣ 等待 Flask API 啟動..."
sleep 3

# 檢查端口是否開放
if nc -z localhost 5000 2>/dev/null; then
    echo "✅ Flask API 已在 5000 端口監聽"
else
    echo "⏳ 端口尚未開放，再等 2 秒..."
    sleep 2
fi

echo ""

# 8. 測試 API /api/health
echo "8️⃣ 測試 API /api/health..."
curl -s http://localhost:5000/api/health | python3 -m json.tool
if [ $? -eq 0 ]; then
    echo "✅ API 響應正常"
else
    echo "❌ API 無響應，檢查日誌..."
    echo ""
    echo "日誌內容："
    tail -30 gunicorn.log
fi

echo ""

# 9. 檯面顯示狀態
echo "9️⃣ 最終狀態檢查..."
echo "   gunicorn 進程︰"
ps aux | grep gunicorn | grep -v grep

echo ""
echo "   監聽端口︰"
lsof -i :5000 || echo "   (沒有進程監聽 5000 端口)"

echo ""
echo "======================================"
echo "✅ 修復完成！"
echo ""
echo "📍 下一步："
echo "   - 檢查 bot.service 狀態︰systemctl status bot.service"
echo "   - 檢查 gunicorn 日誌︰tail -f gunicorn.log"
echo "   - 測試同步︰在 Discord 執行 /sync_from_sheet"
