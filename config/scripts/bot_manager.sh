#!/bin/bash

# Discord Bot 管理工具
# 提供各種便利的管理功能

SCRIPT_DIR="/home/e193752468/kkgroup"
LOG_DIR="/tmp/bot_logs"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 確保日誌目錄存在
mkdir -p "$LOG_DIR"

show_help() {
    echo "🤖 Discord Bot 管理工具"
    echo "用法: $0 [選項]"
    echo ""
    echo "選項:"
    echo "  status           - 顯示所有機器人狀態"
    echo "  status-detail    - 顯示詳細狀態並發送到Discord"
    echo "  logs [服務名]    - 查看指定服務的日誌"
    echo "  restart [服務名] - 重啟指定服務"
    echo "  stop [服務名]    - 停止指定服務"
    echo "  start [服務名]   - 啟動指定服務"
    echo "  update          - 檢查並執行更新"
    echo "  force-update    - 強制更新（不檢查git）"
    echo "  export-logs     - 匯出所有日誌到檔案"
    echo "  monitor         - 即時監控機器人狀態"
    echo "  help            - 顯示此說明"
    echo ""
    echo "服務名稱: discord-bot, discord-shopbot, discord-uibot"
    echo "如果不指定服務名，將對所有服務執行操作"
}

check_service_exists() {
    local service=$1
    if systemctl list-unit-files | grep -q "^$service.service"; then
        return 0
    else
        return 1
    fi
}

show_status() {
    echo -e "${BLUE}📊 系統狀態概覽${NC}"
    echo "================================"
    
    # 系統負載
    echo -e "${YELLOW}🖥️ 系統負載:${NC} $(uptime | awk '{print $10,$11,$12}')"
    
    # 記憶體使用
    echo -e "${YELLOW}🧠 記憶體使用:${NC}"
    free -h | grep "Mem:" | awk '{printf "   使用: %s / %s (%.1f%%)\n", $3, $2, ($3/$2)*100}'
    
    # 磁碟空間
    echo -e "${YELLOW}💾 磁碟空間:${NC}"
    df -h /home/e193752468 | tail -n 1 | awk '{printf "   使用: %s / %s (%s)\n", $3, $2, $5}'
    
    echo ""
    echo -e "${BLUE}🤖 機器人服務狀態${NC}"
    echo "================================"
    
    local services=("discord-bot" "discord-shopbot" "discord-uibot")
    
    for service in "${services[@]}"; do
        if check_service_exists "$service"; then
            local status=$(systemctl is-active "$service" 2>/dev/null)
            local enabled=$(systemctl is-enabled "$service" 2>/dev/null)
            
            case $status in
                "active")
                    echo -e "${GREEN}✅${NC} $service - 運行中 (啟用: $enabled)"
                    # 取得 PID 和記憶體使用
                    local pid=$(systemctl show "$service" --property=MainPID --value)
                    if [ "$pid" != "0" ] && [ -n "$pid" ]; then
                        local mem=$(ps -p "$pid" -o rss= 2>/dev/null | awk '{printf "%.1fMB", $1/1024}')
                        local uptime=$(ps -p "$pid" -o etime= 2>/dev/null | xargs)
                        echo "   PID: $pid, 記憶體: $mem, 運行時間: $uptime"
                    fi
                    ;;
                "inactive"|"failed")
                    echo -e "${RED}❌${NC} $service - 停止/失敗 (啟用: $enabled)"
                    ;;
                *)
                    echo -e "${YELLOW}❓${NC} $service - 狀態: $status (啟用: $enabled)"
                    ;;
            esac
        else
            echo -e "${YELLOW}❓${NC} $service - 服務不存在"
        fi
        echo ""
    done
}

show_logs() {
    local service=$1
    
    if [ -z "$service" ]; then
        echo -e "${YELLOW}請指定服務名稱。可用服務:${NC}"
        echo "  discord-bot, discord-shopbot, discord-uibot"
        return 1
    fi
    
    if ! check_service_exists "$service"; then
        echo -e "${RED}❌ 服務 $service 不存在${NC}"
        return 1
    fi
    
    echo -e "${BLUE}📋 $service 日誌 (最近50行):${NC}"
    echo "================================"
    journalctl -u "$service" -n 50 --no-pager -l
}

manage_service() {
    local action=$1
    local service=$2
    
    if [ -z "$service" ]; then
        # 如果沒指定服務，對所有服務執行操作
        local services=("discord-bot" "discord-shopbot" "discord-uibot")
        for svc in "${services[@]}"; do
            manage_service "$action" "$svc"
        done
        return
    fi
    
    if ! check_service_exists "$service"; then
        echo -e "${RED}❌ 服務 $service 不存在${NC}"
        return 1
    fi
    
    echo -e "${BLUE}🔄 ${action} $service...${NC}"
    
    case $action in
        "restart")
            sudo systemctl restart "$service"
            ;;
        "stop")
            sudo systemctl stop "$service"
            ;;
        "start")
            sudo systemctl start "$service"
            ;;
        *)
            echo -e "${RED}❌ 不支援的操作: $action${NC}"
            return 1
            ;;
    esac
    
    # 等待一下再檢查狀態
    sleep 2
    local status=$(systemctl is-active "$service")
    
    case $status in
        "active")
            echo -e "${GREEN}✅ $service $action 成功${NC}"
            ;;
        *)
            echo -e "${RED}❌ $service $action 可能失敗，狀態: $status${NC}"
            ;;
    esac
}

run_update() {
    echo -e "${BLUE}🔄 執行更新檢查...${NC}"
    cd "$SCRIPT_DIR"
    
    if [ -f "update_and_restart.py" ]; then
        python3 update_and_restart.py
    else
        echo -e "${RED}❌ 找不到更新腳本 update_and_restart.py${NC}"
        return 1
    fi
}

force_update() {
    echo -e "${YELLOW}⚠️ 強制更新模式${NC}"
    echo "這將直接拉取最新代碼並重啟所有服務"
    echo -n "確定要繼續嗎? (y/N): "
    read -r response
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}🔄 強制執行更新...${NC}"
        cd "$SCRIPT_DIR"
        
        # 拉取最新代碼
        echo "📥 拉取最新代碼..."
        git pull origin main
        
        # 重啟所有服務
        echo "🔄 重啟所有服務..."
        manage_service "restart"
        
        # 發送狀態報告
        if [ -f "bot_status_checker.py" ]; then
            echo "📢 發送狀態報告..."
            python3 bot_status_checker.py --detailed
        fi
        
        echo -e "${GREEN}✅ 強制更新完成${NC}"
    else
        echo "取消更新"
    fi
}

export_logs() {
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local export_file="$LOG_DIR/bot_logs_export_$timestamp.txt"
    
    echo -e "${BLUE}📄 匯出日誌到 $export_file${NC}"
    
    {
        echo "=" >> "$export_file"
        echo "Discord Bot 日誌匯出"
        echo "匯出時間: $(date)"
        echo "=" 
        echo ""
        
        local services=("discord-bot" "discord-shopbot" "discord-uibot")
        
        for service in "${services[@]}"; do
            if check_service_exists "$service"; then
                echo "--- $service 日誌 (最近100行) ---"
                journalctl -u "$service" -n 100 --no-pager -l
                echo ""
                echo ""
            fi
        done
        
        echo "--- 系統錯誤日誌 (最近24小時) ---"
        journalctl -p err --since "24 hours ago" --no-pager -l
        
        echo ""
        echo "--- 系統資源資訊 ---"
        echo "系統負載: $(uptime)"
        echo ""
        echo "記憶體使用:"
        free -h
        echo ""
        echo "磁碟空間:"
        df -h
        echo ""
        echo "進程資訊:"
        ps aux | grep python | grep -E "(bot|shop|ui)\.py"
        
    } >> "$export_file"
    
    echo -e "${GREEN}✅ 日誌已匯出到: $export_file${NC}"
    echo "檔案大小: $(du -h "$export_file" | cut -f1)"
}

monitor_bots() {
    echo -e "${BLUE}📊 即時監控模式 (按 Ctrl+C 停止)${NC}"
    echo "================================"
    
    while true; do
        clear
        show_status
        echo ""
        echo -e "${YELLOW}⏰ 最後更新: $(date)${NC}"
        echo -e "${YELLOW}📊 監控中... (每30秒更新一次)${NC}"
        sleep 30
    done
}

# 主要邏輯
case "$1" in
    "status")
        show_status
        ;;
    "status-detail")
        show_status
        echo ""
        echo -e "${BLUE}📢 發送詳細狀態到 Discord...${NC}"
        cd "$SCRIPT_DIR"
        if [ -f "bot_status_checker.py" ]; then
            python3 bot_status_checker.py --detailed
        else
            echo -e "${RED}❌ 找不到狀態檢查腳本${NC}"
        fi
        ;;
    "logs")
        show_logs "$2"
        ;;
    "restart")
        manage_service "restart" "$2"
        ;;
    "stop")
        manage_service "stop" "$2"
        ;;
    "start")
        manage_service "start" "$2"
        ;;
    "update")
        run_update
        ;;
    "force-update")
        force_update
        ;;
    "export-logs")
        export_logs
        ;;
    "monitor")
        monitor_bots
        ;;
    "help"|"")
        show_help
        ;;
    *)
        echo -e "${RED}❌ 未知選項: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
