#!/bin/bash
# BOT 斷線原因診斷腳本

echo "========================================="
echo "🔍 BOT 斷線問題診斷"
echo "========================================="
echo ""

# 1. 檢查登錄腳本
echo "[1] 檢查 SSH 登錄腳本..."
echo "~/.bashrc:"
if [ -f ~/.bashrc ]; then
    grep -v '^#' ~/.bashrc | grep -v '^$' | head -10
else
    echo "  (無此文件)"
fi

echo ""
echo "~/.bash_profile:"
if [ -f ~/.bash_profile ]; then
    grep -v '^#' ~/.bash_profile | grep -v '^$' | head -10
else
    echo "  (無此文件)"
fi

echo ""
echo "~/.profile:"
if [ -f ~/.profile ]; then
    grep -v '^#' ~/.profile | grep -v '^$' | head -10
else
    echo "  (無此文件)"
fi

echo ""
echo "---"

# 2. 檢查 systemd 服務依賴
echo ""
echo "[2] 檢查 systemd 服務依賴..."
echo "bot.service 依賴:"
systemctl list-dependencies bot.service 2>/dev/null || echo "  (無法查詢)"

echo ""
echo "shopbot.service 依賴:"
systemctl list-dependencies shopbot.service 2>/dev/null || echo "  (無法查詢)"

echo ""
echo "---"

# 3. 檢查 OOM killer 事件
echo ""
echo "[3] 檢查是否發生 OOM killer..."
if dmesg | grep -q "oom-kill"; then
    echo "⚠️  檢測到 OOM killer 事件！"
    dmesg | grep "oom-kill" | tail -5
else
    echo "✓ 沒有 OOM killer 事件"
fi

echo ""
echo "---"

# 4. 檢查 systemd 日誌中的錯誤
echo ""
echo "[4] 最近的 systemd 錯誤訊息（過去 30 分鐘）..."
journalctl --since "30 min ago" -u bot.service -u shopbot.service -u uibot.service \
    | grep -E 'error|Error|ERROR|fail|Fail|FAIL|killed|Killed' \
    | tail -20

echo ""
echo "---"

# 5. 檢查當前系統負載
echo ""
echo "[5] 當前系統資源狀態..."
echo "記憶體使用:"
free -h | tail -2

echo ""
echo "系統負載:"
uptime

echo ""
echo "進程狀態:"
ps aux | grep -E 'bot|gunicorn' | grep -v grep

echo ""
echo "========================================="
echo "✅ 診斷完成"
echo "========================================="
