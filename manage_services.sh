#!/bin/bash
# 統一的 Bot 和 API 管理腳本

set -e

COMMAND="${1:-status}"

case "$COMMAND" in
    start)
        echo "🚀 啟動所有服務..."
        sudo systemctl start bot.service shopbot.service uibot.service sheet_sync_api.service
        sleep 2
        echo "✅ 所有服務已啟動"
        $0 status
        ;;
    
    stop)
        echo "🛑 停止所有服務..."
        sudo systemctl stop bot.service shopbot.service uibot.service sheet_sync_api.service
        sleep 1
        echo "✅ 所有服務已停止"
        ;;
    
    restart)
        echo "🔄 重啟所有服務..."
        sudo systemctl restart bot.service shopbot.service uibot.service sheet_sync_api.service
        sleep 2
        echo "✅ 所有服務已重啟"
        $0 status
        ;;
    
    status)
        echo ""
        echo "📊 服務狀態："
        echo "================================"
        for service in bot.service shopbot.service uibot.service sheet_sync_api.service; do
            status=$(sudo systemctl is-active $service 2>/dev/null || echo "inactive")
            if [ "$status" = "active" ]; then
                echo "✅ $service: RUNNING"
            else
                echo "❌ $service: STOPPED"
            fi
        done
        echo "================================"
        echo ""
        ;;
    
    logs)
        SERVICE="${2:-bot.service}"
        echo "顯示 $SERVICE 的最近 30 行日誌:"
        echo ""
        sudo journalctl -u $SERVICE -n 30 --no-pager
        ;;
    
    *)
        echo "用法: $0 {start|stop|restart|status|logs [service]}"
        echo ""
        echo "範例:"
        echo "  $0 start                      # 啟動所有服務"
        echo "  $0 stop                       # 停止所有服務"
        echo "  $0 restart                    # 重啟所有服務"
        echo "  $0 status                     # 顯示所有服務狀態"
        echo "  $0 logs bot.service           # 顯示 bot 日誌"
        echo "  $0 logs sheet_sync_api.service # 顯示 API 日誌"
        exit 1
        ;;
esac
