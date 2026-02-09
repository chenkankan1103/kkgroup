#!/bin/bash
# Discord BOT 启动脚本（由 systemd 管理）
# 用途：启动 BOT，系统故障由 systemd 自动处理重启
# 注意：不使用 set -e，以允许更灵活的错误处理

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "🚀 Discord BOT 启动脚本"
echo "=================================================="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "PID: $$"
echo ""

# 0. 清理函数
cleanup() {
    echo ""
    echo "⚠️  收到中止信号，优雅关闭 BOT..."
    # systemd 会处理进程清理
    exit 0
}
trap cleanup SIGTERM SIGINT

# 1. 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 虚拟环境不存在!"
    exit 1
fi
source venv/bin/activate || { echo "❌ 激活虚拟环境失败!"; exit 1; }

# 2. 检查 bot.py
if [ ! -f "bot.py" ]; then
    echo "❌ bot.py 不存在!"
    exit 1
fi

# 3. 拉取最新代码（允许失败）
echo "📥 拉取最新代码..."
if git rev-parse --git-dir > /dev/null 2>&1; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if git pull origin "$CURRENT_BRANCH" 2>/dev/null; then
        echo "✅ 代码更新成功"
    else
        echo "⚠️  无法获取最新代码（可能离线），继续使用本地代码"
    fi
else
    echo "⚠️  不在 Git 仓库中"
fi

# 4. 检查并清理旧的 BOT 进程（防止重复）
echo "🔍 检查旧的 BOT 进程..."
CURRENT_PID=$$
OLD_PIDS=$(pgrep -f "python.*bot\.py" 2>/dev/null | grep -v "^$$" || echo "")

if [ -n "$OLD_PIDS" ]; then
    for PID in $OLD_PIDS; do
        if [ "$PID" != "$CURRENT_PID" ]; then
            echo "🔴 杀死旧的 BOT 进程: $PID"
            kill -9 "$PID" 2>/dev/null || true
        fi
    done
    sleep 1  # 等待进程完全退出
fi

# 5. 确保 Flask API 正在运行（允许失败）
echo "✅ 检查 Flask API..."
FLASK_PID=$(pgrep -f "gunicorn.*sheet_sync_api" 2>/dev/null || echo "")

if [ -z "$FLASK_PID" ]; then
    echo "⚠️  Flask API 未运行，尝试启动..."
    nohup ./venv/bin/gunicorn \
        -w 4 \
        -b 0.0.0.0:5000 \
        --timeout 120 \
        --access-logfile /dev/null \
        --error-logfile /dev/null \
        sheet_sync_api:app > /tmp/flask_api.log 2>&1 &
    API_PID=$!
    
    if sleep 2 && pgrep -f "gunicorn.*sheet_sync_api" > /dev/null 2>&1; then
        echo "✅ Flask API 已启动 (PID: $API_PID)"
    else
        echo "⚠️  Flask API 启动失败，继续启动 BOT"
        cat /tmp/flask_api.log 2>/dev/null | tail -5
    fi
else
    echo "✅ Flask API 已在运行 (PID: $FLASK_PID)"
fi

# 6. 启动 BOT
echo "🤖 启动 Discord BOT..."
echo "=================================================="
python3 bot.py
BOT_EXIT_CODE=$?

# 如果到达这里，说明 BOT 已退出
echo ""
echo "⚠️  BOT 已停止 (代码: $BOT_EXIT_CODE)"

# 优雅关闭 Flask API（如果还在运行）
echo "🛑 检查是否需要清理 Flask API..."
REMAINING_FLASK=$(pgrep -f "gunicorn.*sheet_sync_api" 2>/dev/null || echo "")
if [ -n "$REMAINING_FLASK" ]; then
    echo "🔴 杀死 Flask API 进程: $REMAINING_FLASK"
    kill -9 $REMAINING_FLASK 2>/dev/null || true
fi

exit $BOT_EXIT_CODE
