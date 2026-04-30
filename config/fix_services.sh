#!/bin/bash
# 修復 kkgroup-api.service 和 crontab 配置

echo "=== 1. 備份原始配置 ==="
sudo cp /etc/systemd/system/kkgroup-api.service /etc/systemd/system/kkgroup-api.service.bak

echo "=== 2. 修改 kkgroup-api.service ==="
# 修改 After 依賴
sudo sed -i 's/^After=network\.target/After=network-online.target systemd-resolved.service/' /etc/systemd/system/kkgroup-api.service

# 在 FLASK_DEBUG 前添加編碼設置
sudo sed -i '/Environment="FLASK_DEBUG=/i\Environment="PYTHONIOENCODING=utf-8"\nEnvironment="LANG=C.UTF-8"\nEnvironment="LC_ALL=C.UTF-8"' /etc/systemd/system/kkgroup-api.service

# 改進重啟策略
sudo sed -i 's/RestartSec=10/RestartSec=30/' /etc/systemd/system/kkgroup-api.service

# 重新加載 systemd
sudo systemctl daemon-reload

echo "=== 3. 更新 crontab ==="
# 更新 crontab - 使用虛擬環境的 python3
sudo crontab -u e193752468 -l | sed 's|/usr/bin/python3 scheduled_tasks/|/home/e193752468/kkgroup/venv/bin/python3 scheduled_tasks/|g' | sudo crontab -u e193752468 -

# 添加編碼設置到 crontab
(sudo crontab -u e193752468 -l | grep -v "^PYTHONIOENCODING"; echo "LANG=C.UTF-8"; echo "LC_ALL=C.UTF-8"; echo "PYTHONIOENCODING=utf-8"; echo "TZ=Asia/Taipei") | sudo crontab -u e193752468 -

echo "✅ 所有配置已修改"
echo ""
echo "=== 驗證配置 ==="
sudo systemctl cat kkgroup-api.service | grep -E "After|Restart|PYTHONIOENCODING"
