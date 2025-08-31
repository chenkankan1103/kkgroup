#!/bin/bash
# Discord Bot 系統安裝配置腳本

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BOT_DIR="/home/e193752468/kkgroup"
USER="e193752468"

echo -e "${BLUE}🚀 Discord Bot 系統配置助手${NC}"
echo "================================"

# 檢查是否為正確用戶
if [ "$(whoami)" != "$USER" ]; then
    echo -e "${RED}❌ 請使用用戶 $USER 執行此腳本${NC}"
    exit 1
fi

# 檢查目錄是否存在
if [ ! -d "$BOT_DIR" ]; then
    echo -e "${RED}❌ 找不到目錄: $BOT_DIR${NC}"
    exit 1
fi

cd "$BOT_DIR"

echo -e "${YELLOW}📋 安裝步驟:${NC}"
echo "1. 安裝 Python 依賴"
echo "2. 設定 systemd 服務"
echo "3. 配置權限"
echo "4. 建立管理工具"
echo "5. 設定定期檢查"
echo ""

# 步驟1: 安裝依賴
echo -e "${BLUE}📦 步驟1: 安裝 Python 依賴${NC}"
if [ ! -f "requirements.txt" ]; then
    echo "建立 requirements.txt..."
    cat > requirements.txt << 'EOF'
discord.py
python-dotenv
psutil
asyncio
datetime
EOF
fi

# 檢查是否有虛擬環境
if [ ! -d "venv" ]; then
    echo "建立虛擬環境..."
    python3 -m venv venv
fi

echo "安裝/更新依賴..."
source venv/bin/activate
pip install -r requirements.txt
deactivate

# 步驟2: 設定 systemd 服務
echo -e "${BLUE}🔧 步驟2: 設定 systemd 服務${NC}"

create_systemd_service() {
    local service_name=$1
    local script_name=$2
    local description=$3
    
    cat > "/tmp/${service_name}.service" << EOF
[Unit]
Description=${description}
After=network.target
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${USER}
Group=${USER}
WorkingDirectory=${BOT_DIR}
Environment=PATH=${BOT_DIR}/venv/bin
ExecStart=${BOT_DIR}/venv/bin/python ${script_name}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${service_name}

TimeoutStopSec=30
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF
    
    echo "建立服務: ${service_name}"
    sudo cp "/tmp/${service_name}.service" "/etc/systemd/system/"
    rm "/tmp/${service_name}.service"
}

# 建立服務檔案
if [ -f "bot.py" ]; then
    create_systemd_service "discord-bot" "bot.py" "Discord Main Bot"
fi

if [ -f "shopbot.py" ]; then
    create_systemd_service "discord-shopbot" "shopbot.py" "Discord Shop Bot"
fi

if [ -f "uibot.py" ]; then
    create_systemd_service "discord-uibot" "uibot.py" "Discord UI Bot"
fi

if [ -f "web.py" ]; then
    create_systemd_service "discord-web" "web.py" "Discord Web Interface"
fi

# 重新載入 systemd
echo "重新載入 systemd..."
sudo systemctl daemon-reload

# 步驟3: 設定權限和啟用服務
echo -e "${BLUE}🔑 步驟3: 設定權限${NC}"

services=("discord-bot" "discord-shopbot" "discord-uibot")
for service in "${services[@]}"; do
    if [ -f "/etc/systemd/system/${service}.service" ]; then
        echo "啟用服務: $service"
        sudo systemctl enable "$service"
    fi
done

# 步驟4: 建立管理工具
echo -e "${BLUE}🛠️ 步驟4: 建立管理工具${NC}"

# 建立符號連結到 PATH
if [ -f "bot_manager.sh" ]; then
    chmod +x bot_manager.sh
    sudo ln -sf "$BOT_DIR/bot_manager.sh" "/usr/local/bin/botctl"
    echo "管理工具已安裝: botctl"
fi

# 建立日誌目錄
mkdir -p /tmp/bot_logs

# 步驟5: 設定定期檢查
echo -e "${BLUE}⏰ 步驟5: 設定定期檢查${NC}"

# 詢問是否設定自動檢查
echo -n "是否要設定每10分鐘自動檢查更新? (y/N): "
read -r auto_update

if [[ "$auto_update" =~ ^[Yy]$ ]]; then
    # 添加到 crontab
    (crontab -l 2>/dev/null; echo "*/10 * * * * cd $BOT_DIR && python3 update_and_restart.py >/dev/null 2>&1") | crontab -
    echo "✅ 已設定自動檢查更新"
fi

echo -n "是否要設定每小時發送狀態報告? (y/N): "
read -r status_report

if [[ "$status_report" =~ ^[Yy]$ ]]; then
    # 添加狀態報告到 crontab
    (crontab -l 2>/dev/null; echo "0 * * * * cd $BOT_DIR && python3 bot_status_checker.py >/dev/null 2>&1") | crontab -
    echo "✅ 已設定每小時狀態報告"
fi

# 建立備份腳本
echo -e "${BLUE}💾 建立備份腳本${NC}"
cat > backup.sh << 'EOF'
#!/bin/bash
# 簡單備份腳本

BACKUP_DIR="/tmp/bot_backup_$(date +%Y%m%d_%H%M%S)"
SOURCE_DIR="/home/e193752468/kkgroup"

mkdir -p "$BACKUP_DIR"

# 備份代碼和配置
cp -r "$SOURCE_DIR"/*.py "$BACKUP_DIR/" 2>/dev/null
cp -r "$SOURCE_DIR"/.env "$BACKUP_DIR/" 2>/dev/null
cp -r "$SOURCE_DIR"/requirements.txt "$BACKUP_DIR/" 2>/dev/null

# 備份 systemd 服務
sudo cp /etc/systemd/system/discord-*.service "$BACKUP_DIR/" 2>/dev/null

# 建立壓縮檔
tar -czf "${BACKUP_DIR}.tar.gz" -C "$(dirname "$BACKUP_DIR")" "$(basename "$BACKUP_DIR")"
rm -rf "$BACKUP_DIR"

echo "✅ 備份完成: ${BACKUP_DIR}.tar.gz"
EOF

chmod +x backup.sh

# 完成設定
echo ""
echo -e "${GREEN}🎉 設定完成！${NC}"
echo "================================"
echo ""
echo -e "${YELLOW}📋 可用命令:${NC}"
echo "  botctl status          - 查看狀態"
echo "  botctl restart         - 重啟所有服務"
echo "  botctl logs [服務名]   - 查看日誌"
echo "  botctl update          - 檢查更新"
echo "  botctl monitor         - 即時監控"
echo "  botctl help           - 查看完整說明"
echo ""
echo -e "${YELLOW}📂 重要檔案位置:${NC}"
echo "  腳本目錄: $BOT_DIR"
echo "  日誌目錄: /tmp/bot_logs"
echo "  服務配置: /etc/systemd/system/discord-*.service"
echo ""
echo -e "${YELLOW}🚀 接下來的步驟:${NC}"
echo "1. 確認 .env 檔案包含正確的 Discord Token"
echo "2. 執行: botctl start (啟動所有服務)"
echo "3. 執行: botctl status (檢查狀態)"
echo "4. 執行: botctl status-detail (發送狀態到 Discord)"
echo ""

# 詢問是否立即啟動服務
echo -n "是否要立即啟動所有服務? (y/N): "
read -r start_services

if [[ "$start_services" =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🚀 啟動所有服務...${NC}"
    
    for service in "${services[@]}"; do
        if [ -f "/etc/systemd/system/${service}.service" ]; then
            sudo systemctl start "$service"
            echo "啟動 $service..."
            sleep 2
        fi
    done
    
    echo ""
    echo "等待服務啟動..."
    sleep 5
    
    # 顯示狀態
    ./bot_manager.sh status
fi

echo ""
echo -e "${GREEN}✨ 享受你的 Discord Bot！${NC}"
