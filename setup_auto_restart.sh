#!/bin/bash
# 設置 BOT 自動重啟定時任務

echo "========================================="
echo "設置 BOT 自動重啟任務"
echo "========================================="
echo ""

# 建立定時任務：每天上午 3:00 UTC （晚上 11:00 台灣時間）重啟 BOT
echo "[*] 創建 systemd timer..."

# 建立 service 單位
sudo tee /etc/systemd/system/bot-restart-daily.service > /dev/null << 'EOF'
[Unit]
Description=Daily BOT Restart Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=e193752468
Group=e193752468
ExecStart=/bin/bash -c 'systemctl restart bot.service shopbot.service uibot.service'
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 建立 timer 單位
sudo tee /etc/systemd/system/bot-restart-daily.timer > /dev/null << 'EOF'
[Unit]
Description=Daily BOT Restart Timer
Requires=bot-restart-daily.service
After=network-online.target

[Timer]
# 每天 03:00 UTC 執行一次
OnCalendar=daily
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 重新加載 systemd
sudo systemctl daemon-reload

# 啟用並啟動 timer
sudo systemctl enable --now bot-restart-daily.timer

echo "✓ Systemd timer 已設置"
echo ""
echo "驗證狀態："
systemctl status bot-restart-daily.timer --no-pager

echo ""
echo "========================================="
echo "✅ 完成！BOT 將在每天 03:00 UTC 自動重啟"
echo "========================================="
echo ""
echo "查看下次執行時間："
systemctl list-timers bot-restart-daily.timer
echo ""
echo "查看執行日誌："
echo "  sudo journalctl -u bot-restart-daily.service -n 20"
