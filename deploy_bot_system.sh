#!/bin/bash

# Discord BOT 系統整合部署腳本
# 功能：
# 1. 備份舊的 systemd 配置
# 2. 部署新的 systemd 配置
# 3. 停止舊的 start_bot_and_api.sh 進程
# 4. 啟動新的 systemd 服務
# 5. 驗證部署成功

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Discord BOT 系統整合部署                                  ║"
echo "║  功能：                                                    ║"
echo "║  1. Flask API with Systemd                                ║"
echo "║  2. 三個 BOT 同生態系統管理                                ║"
echo "║  3. 自動檢測和復原機制                                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

WORK_DIR="/home/e193752468/kkgroup"
SYSTEMD_DIR="/etc/systemd/system"
BACKUP_DIR="$WORK_DIR/systemd-backup-$(date +%Y%m%d-%H%M%S)"

# ============ 步驟 1: 備份舊配置 ============
echo -e "${BLUE}[1/7] 備份舊的 systemd 配置...${NC}"

mkdir -p "$BACKUP_DIR"

for service in bot.service shopbot.service uibot.service; do
    if [ -f "$SYSTEMD_DIR/$service" ]; then
        cp "$SYSTEMD_DIR/$service" "$BACKUP_DIR/"
        echo -e "${GREEN}  ✅ 已備份 $service${NC}"
    fi
done

echo -e "${GREEN}✓ 備份完成: $BACKUP_DIR${NC}"
echo ""

# ============ 步驟 2: 停止舊進程 ============
echo -e "${BLUE}[2/7] 停止舊的進程...${NC}"

echo "  🛑 停止舊的 start_bot_and_api.sh..."
pkill -f "start_bot_and_api.sh" || true
sleep 2

echo "  🛑 停止所有 BOT..."
systemctl stop bot.service shopbot.service uibot.service 2>/dev/null || true
sleep 2

echo "  🛑 停止 gunicorn (如果在運行)..."
pkill -f "gunicorn" || true
sleep 2

echo -e "${GREEN}✓ 舊進程已停止${NC}"
echo ""

# ============ 步驟 3: 禁用舊的啟動腳本 ============
echo -e "${BLUE}[3/7] 禁用舊的啟動腳本...${NC}"

if [ -f "$WORK_DIR/start_bot_and_api.sh" ]; then
    chmod -x "$WORK_DIR/start_bot_and_api.sh"
    echo -e "${GREEN}  ✅ 已禁用 start_bot_and_api.sh${NC}"
fi

echo ""

# ============ 步驟 4: 部署新的 systemd 配置 ============
echo -e "${BLUE}[4/7] 部署新的 systemd 配置...${NC}"

cp "$WORK_DIR/systemd-configs/flask-api.service" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 flask-api.service${NC}"

cp "$WORK_DIR/systemd-configs/bot.service" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 bot.service${NC}"

cp "$WORK_DIR/systemd-configs/shopbot.service" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 shopbot.service${NC}"

cp "$WORK_DIR/systemd-configs/uibot.service" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 uibot.service${NC}"

cp "$WORK_DIR/systemd-configs/bot-ecosystem.target" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 bot-ecosystem.target${NC}"

cp "$WORK_DIR/systemd-configs/bot-monitoring.service" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 bot-monitoring.service${NC}"

cp "$WORK_DIR/systemd-configs/bot-monitoring.timer" "$SYSTEMD_DIR/"
echo -e "${GREEN}  ✅ 已部署 bot-monitoring.timer${NC}"

echo ""

# ============ 步驟 5: 重新加載 systemd 配置 ============
echo -e "${BLUE}[5/7] 重新加載 systemd 配置...${NC}"

systemctl daemon-reload
echo -e "${GREEN}  ✅ systemd daemon 已重新加載${NC}"

echo ""

# ============ 步驟 6: 啟動新的服務 ============
echo -e "${BLUE}[6/7] 啟動新的服務...${NC}"

echo "  🚀 啟動 Flask API..."
systemctl start flask-api.service
sleep 5

echo "  🚀 啟動 BOT 生態系統..."
systemctl start bot-ecosystem.target
sleep 10

echo "  🚀 啟動監控計時器..."
systemctl enable bot-monitoring.timer
systemctl start bot-monitoring.timer

echo -e "${GREEN}✓ 所有服務已啟動${NC}"
echo ""

# ============ 步驟 7: 驗證部署 ============
echo -e "${BLUE}[7/7] 驗證部署...${NC}"
echo ""

echo "📋 服務狀態:"
systemctl status flask-api.service --no-pager | head -3
echo ""
systemctl status bot.service --no-pager | head -3
echo ""
systemctl status shopbot.service --no-pager | head -3
echo ""
systemctl status uibot.service --no-pager | head -3
echo ""

echo "📊 進程檢查:"
echo "  Flask API (gunicorn):"
pgrep -f "gunicorn" > /dev/null && echo -e "  ${GREEN}✅ 運行中${NC}" || echo -e "  ${RED}❌ 未運行${NC}"

echo "  BOT 進程:"
pgrep -f "python.*bot.py" > /dev/null && echo -e "  ${GREEN}✅ 運行中${NC}" || echo -e "  ${RED}❌ 未運行${NC}"
pgrep -f "python.*shopbot.py" > /dev/null && echo -e "  ${GREEN}✅ 運行中${NC}" || echo -e "  ${RED}❌ 未運行${NC}"
pgrep -f "python.*uibot.py" > /dev/null && echo -e "  ${GREEN}✅ 運行中${NC}" || echo -e "  ${RED}❌ 未運行${NC}"

echo ""
echo "🔌 端口檢查:"
netstat -tuln 2>/dev/null | grep 5000 > /dev/null && echo -e "  ${GREEN}✅ 端口 5000 開放${NC}" || echo -e "  ${RED}❌ 端口 5000 未開放${NC}"

echo ""
echo "⏱️  定時器狀態:"
systemctl list-timers bot-monitoring.timer --no-pager | tail -2

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

echo "📝 後續步驟："
echo "  1. 監控 Flask API: journalctl -u flask-api.service -f"
echo "  2. 監控 BOT: journalctl -u bot.service -f"
echo "  3. 檢查監控: systemctl status bot-monitoring.timer"
echo "  4. 查看監控日誌: cat /tmp/bot-monitoring/monitoring.log"
echo ""

echo "🔧 常用命令："
echo "  # 啟動/停止整個生態系統"
echo "  systemctl start bot-ecosystem.target"
echo "  systemctl stop bot-ecosystem.target"
echo ""
echo "  # 查看所有相關服務"
echo "  systemctl status bot-ecosystem.target"
echo ""
echo "  # 檢查監控日誌"
echo "  journalctl -u bot-monitoring.service -f"
echo ""
