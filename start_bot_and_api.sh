#!/bin/bash

# Bot 與 Flask API 自動重啟腳本
# 用途：一次性重啟 Bot 和 Flask API，無需手動介入

set -e  # 任何錯誤立即退出

echo "=================================================="
echo "🚀 Bot + Flask API 自動重啟"
echo "=================================================="
echo ""

# 0. 拉取最新代碼
echo "0️⃣ 拉取最新代碼..."
if git rev-parse --git-dir > /dev/null 2>&1; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    echo "   📍 當前分支: $CURRENT_BRANCH"
    git pull origin "$CURRENT_BRANCH" || true
    echo "✅ 代碼已更新"
else
    echo "⚠️ 不在 Git 倉庫中，跳過 git pull"
fi
echo ""

# 1. 停止舊進程
echo "1️⃣ 停止舊進程..."

# 停止舊的 gunicorn
echo "   🔴 停止舊的 gunicorn 進程..."
pkill -f "gunicorn.*sheet_sync_api" || true
pkill -f "python.*sheet_sync_api" || true
sleep 2

# 檢查並停止舊的 Bot 進程
if pgrep -f "python.*bot.py" > /dev/null; then
    echo "   🔴 停止舊的 Bot 進程..."
    pkill -f "python.*bot.py" || true
    sleep 2
fi

echo "✅ 舊進程已停止"
echo ""

# 2. 檢查環境
echo "2️⃣ 檢查環境..."
if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在"
    exit 1
fi
echo "✅ .env 存在"

if [ ! -f "bot.py" ]; then
    echo "❌ bot.py 不存在"
    exit 1
fi
echo "✅ bot.py 存在"

if [ ! -f "sheet_sync_api.py" ]; then
    echo "❌ sheet_sync_api.py 不存在"
    exit 1
fi
echo "✅ sheet_sync_api.py 存在"

echo ""

# 3. 驗證虛擬環境
echo "3️⃣ 驗證虛擬環境..."
if [ ! -d "venv" ]; then
    echo "❌ 虛擬環境不存在: venv"
    exit 1
fi
echo "✅ 虛擬環境存在"

# 啟動虛擬環境
source venv/bin/activate
echo "✅ 虛擬環境已啟動"

echo ""

# 4. 驗證 Python 語法
echo "4️⃣ 驗證 Python 語法..."
python3 -m py_compile bot.py sheet_sync_api.py
echo "✅ 語法檢查通過"

echo ""

# 5. 啟動 Flask API (後臺)
echo "5️⃣ 啟動 Flask API..."

if [ -f "./venv/bin/gunicorn" ]; then
    GUNICORN="./venv/bin/gunicorn"
    echo "   使用虛擬環境 gunicorn: $GUNICORN"
elif [ -f "./venv/bin/python" ]; then
    GUNICORN="./venv/bin/python -m gunicorn"
    echo "   使用 python -m gunicorn"
else
    echo "❌ 找不到 gunicorn"
    exit 1
fi

# 使用 nohup 在後臺啟動 gunicorn
nohup $GUNICORN \
    -w 4 \
    -b 0.0.0.0:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    sheet_sync_api:app > gunicorn.log 2>&1 &

GUNICORN_PID=$!
echo "✅ gunicorn 已啟動 (PID: $GUNICORN_PID)"

# 等待 API 啟動
echo "   ⏳ 等待 Flask API 啟動..."
for i in {1..10}; do
    if curl -s http://localhost:5000/api/health > /dev/null; then
        echo "   ✅ Flask API 已就緒"
        break
    fi
    sleep 1
done

echo ""

# 6. 啟動 Bot (前臺 - 一直運行)
echo "6️⃣ 啟動 Discord Bot..."
echo "=================================================="
echo "📍 若要停止 Bot，按 Ctrl+C"
echo "=================================================="
echo ""

python3 bot.py

# BOT 退出时的處理（由 systemd/supervisor 負責重啟，不要無限循環！）
BOT_EXIT_CODE=$?
echo ""
echo "⚠️ Bot 已停止 (代碼: $BOT_EXIT_CODE)"

# 清理舊的 API 進程
echo "   🔴 停止 Flask API 進程..."
pkill -f "gunicorn.*sheet_sync_api" || true
pkill -f "python.*sheet_sync_api" || true

# 正常退出，讓 systemd/supervisor 處理重啟
echo "   ✅ 清理完成，等待系統重啟..."
sleep 2
exit $BOT_EXIT_CODE
