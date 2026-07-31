#!/bin/bash
# 事件驅動版本：cloudflared 啟動完成後自動更新隧道 URL
# 臨時隧道註冊需時間，等待 1 分鐘確保隧道完全就緒

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/var/log/webhook_auto_update.log"

# 確保日誌目錄存在
mkdir -p "$(dirname "$LOG_FILE")"

# 等待隧道完全建立（臨時隧道需要 ~60 秒註冊）
WAIT_TIME=60

# 執行 webhook 更新
{
    echo "============================================================"
    echo "[$(date)] 🚀 cloudflared 事件觸發 - 等待隧道建立..."
    echo "============================================================"
    echo "等待 $WAIT_TIME 秒讓隧道完全註冊..."
    
    sleep $WAIT_TIME
    
    echo "[$(date)] ⏱️  隧道應該已就緒，現在提取 URL..."
    echo "============================================================"
    
    cd "$REPO_DIR"
    /home/e193752468/kkgroup/venv/bin/python3 \
        scheduled_tasks/auto_update_webhook_v2.py
    
    echo "[$(date)] ✅ 隧道 URL 更新完成"
    echo "============================================================"
} >> "$LOG_FILE" 2>&1

exit 0
