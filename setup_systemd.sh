#!/bin/bash
# 為三個 Bot 創建 systemd 服務

echo "📝 創建 systemd 服務文件..."

# 1. 主 Bot 服務
cat > /tmp/kkgroup-bot.service << 'EOF'
[Unit]
Description=KKGroup Discord Bot
After=network.target

[Service]
Type=simple
User=e193752468
WorkingDirectory=/home/e193752468/kkgroup
Environment="PATH=/home/e193752468/kkgroup/venv/bin"
ExecStart=/home/e193752468/kkgroup/venv/bin/python3 bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 2. ShopBot 服務
cat > /tmp/kkgroup-shopbot.service << 'EOF'
[Unit]
Description=KKGroup ShopBot
After=network.target

[Service]
Type=simple
User=e193752468
WorkingDirectory=/home/e193752468/kkgroup
Environment="PATH=/home/e193752468/kkgroup/venv/bin"
ExecStart=/home/e193752468/kkgroup/venv/bin/python3 shopbot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 3. UIBot 服務
cat > /tmp/kkgroup-uibot.service << 'EOF'
[Unit]
Description=KKGroup UIBot
After=network.target

[Service]
Type=simple
User=e193752468
WorkingDirectory=/home/e193752468/kkgroup
Environment="PATH=/home/e193752468/kkgroup/venv/bin"
ExecStart=/home/e193752468/kkgroup/venv/bin/python3 uibot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "✅ 服務文件已創建在 /tmp"
echo ""
echo "📝 要點："
echo "- Restart=always 會在 Bot 崩潰時自動重啟"
echo "- RestartSec=10 設定重啟等待時間 10 秒"
echo "- StandardOutput/Error 使用 journal 便於調試"
echo ""
echo "✏️ 若要安裝，請執行："
echo "  sudo cp /tmp/kkgroup-*.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now kkgroup-bot kkgroup-shopbot kkgroup-uibot"
echo "  sudo systemctl status kkgroup-bot kkgroup-shopbot kkgroup-uibot"
