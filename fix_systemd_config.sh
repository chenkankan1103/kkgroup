#!/bin/bash
# 修復 shopbot 和 uibot 的 Systemd 配置

echo "=================================================="
echo "🔧 修復 Systemd 配置問題"
echo "=================================================="
echo ""

# 1. 修復 shopbot.service
echo "[1/2] 修復 shopbot.service..."
cat > /tmp/shopbot.service << 'EOF'
[Unit]
Description=Discord Shop Bot
After=network.target
Wants=network-online.target
After=network-online.target
PartOf=bot-ecosystem.target

[Service]
Type=simple
User=e193752468
Group=e193752468
WorkingDirectory=/home/e193752468/kkgroup
Environment=PATH=/home/e193752468/kkgroup/venv/bin
Environment=PYTHONUNBUFFERED=1

ExecStart=/home/e193752468/kkgroup/venv/bin/python shopbot.py

Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=discord-shopbot

TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

[Install]
WantedBy=bot-ecosystem.target multi-user.target
EOF

sudo cp /tmp/shopbot.service /etc/systemd/system/shopbot.service
echo "✓ shopbot.service 已修復（移除有問題的 ExecStartPost）"

# 2. 修復 uibot.service
echo ""
echo "[2/2] 修復 uibot.service..."
cat > /tmp/uibot.service << 'EOF'
[Unit]
Description=Discord UI Bot
After=network.target
Wants=network-online.target
After=network-online.target
PartOf=bot-ecosystem.target

[Service]
Type=simple
User=e193752468
Group=e193752468
WorkingDirectory=/home/e193752468/kkgroup
Environment=PATH=/home/e193752468/kkgroup/venv/bin
Environment=PYTHONUNBUFFERED=1

ExecStart=/home/e193752468/kkgroup/venv/bin/python uibot.py

Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=discord-uibot

TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

[Install]
WantedBy=bot-ecosystem.target multi-user.target
EOF

sudo cp /tmp/uibot.service /etc/systemd/system/uibot.service
echo "✓ uibot.service 已修復（移除有問題的 ExecStartPost）"

# 3. 重新加載 systemd
echo ""
echo "[*] 重新加載 systemd..."
sudo systemctl daemon-reload
echo "✓ Systemd 已重新加載"

# 4. 重啟服務
echo ""
echo "[*] 重啟服務..."
sudo systemctl restart shopbot.service uibot.service
sleep 3

# 5. 驗證狀態
echo ""
echo "=================================================="
echo "✅ 修復完成！"
echo "=================================================="
echo ""
echo "服務狀態："
systemctl status shopbot.service uibot.service --no-pager | grep -E 'Active|loaded'
echo ""
echo "進程狀態："
ps aux | grep -E 'shopbot|uibot' | grep -v grep
echo ""
