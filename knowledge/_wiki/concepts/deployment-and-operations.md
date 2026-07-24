# 部署和維運指南

## 系統概述

KKGroup 採用 GCP VM (e2-micro, Ubuntu 20.04 LTS) 作為主要部署環境，使用 systemd 管理服務，透過 Git + GitHub Webhook + Cron 實現自動化部署和維運。

## GCP VM 架構

### 1. 服務部署（5 個核心服務）
| 服務名稱 | 說明 | Port | 依賴 |
|---------|------|------|------|
| `bot.service` | 主 Bot（核心指令、用戶管理） | — | network.target |
| `shopbot.service` | 商店 Bot（經濟、商店、大麻種植） | — | network.target |
| `uibot.service` | UI Bot（置物櫃、動漫追蹤、活動） | — | network.target |
| `kkgroup-api.service` | Flask API（Webhook、OAuth、知識庫） | 5000 | network-online.target, systemd-resolved.service |
| `cloudflared.service` | Cloudflare Tunnel（隧道入口） | — | network-online.target |

**服務配置位置**：`config/services/`（僅 VM 管理，**不上傳 Git**）

### 2. 系統資源
- **VM 規格**：e2-micro (2 vCPU, 1 GB RAM)
- **作業系統**：Ubuntu 20.04 LTS
- **儲存**：SSD 永久磁碟
- **網路**：靜態 IP + Cloudflare Tunnel

### 3. 記憶體優化（e2-micro 必須）
```bash
# 加 1G swap 緩衝
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 驗證
free -m
```

## 服務管理

### 1. systemd 服務配置範例

**主 Bot 服務** (`config/services/bot.service`)：
```ini
[Unit]
Description=KKGroup Bot Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kkgroup
Environment=PYTHONPATH=/home/ubuntu/kkgroup
Environment=PYTHONIOENCODING=utf-8
Environment=LANG=C.UTF-8
ExecStart=/home/ubuntu/.venv/bin/python bots/bot.py
Restart=on-failure
RestartSec=10
StartLimitBurst=10
StartLimitIntervalSec=600

[Install]
WantedBy=multi-user.target
```

**API 服務** (`config/services/kkgroup-api.service`)：
```ini
[Unit]
Description=KKGroup API Service
After=network-online.target systemd-resolved.service
Wants=network-online.target systemd-resolved.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kkgroup
Environment=FLASK_ENV=production
Environment=PYTHONIOENCODING=utf-8
Environment=LANG=C.UTF-8
ExecStart=/home/ubuntu/.venv/bin/python -m flask run --host=0.0.0.0 --port=5000
Restart=on-failure
RestartSec=10
StartLimitBurst=10
StartLimitIntervalSec=600

[Install]
WantedBy=multi-user.target
```

### 2. 服務操作指令
```bash
# 啟動服務
sudo systemctl start bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service

# 停止服務
sudo systemctl stop bot.service

# 重啟服務（核心三 Bot）
sudo systemctl restart bot.service shopbot.service uibot.service

# 重啟含基礎設施
sudo systemctl restart bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service

# 查看服務狀態
systemctl status bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service --no-pager

# 啟用開機自啟（必須執行）
sudo systemctl enable bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service

# 查看服務日誌
sudo journalctl -u bot.service -n 100 --no-pager
sudo journalctl -u kkgroup-api.service -n 100 --no-pager
sudo journalctl -u cloudflared.service -n 50 --no-pager

# 即時監控日誌
sudo journalctl -u bot.service -f

# 重新載入 systemd 配置
sudo systemctl daemon-reload
```

### 3. 常用檢查命令
```bash
# 記憶體/磁碟
free -m
df -h /

# 服務啟用狀態
systemctl is-enabled bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service

# 進程狀態
ps aux | grep -E 'bot\.py|shopbot\.py|uibot\.py|flask|cloudflared'

# 端口監聽
sudo netstat -tlnp | grep -E '5000|80|443'
```

## 自動化部署

### 1. GitHub Webhook 自動部署（主流程）

**觸發流程**：
```
Git Push (main/master) 
  → GitHub Webhook 
  → Cloudflare Tunnel (https://xxx.trycloudflare.com)
  → Nginx (port 80/443) 
  → Flask (port 5000, web/blueprints/webhook.py)
  → 驗證簽名 → git pull origin main
  → 重啟 bot.service shopbot.service uibot.service
  → 發送 Discord 通知
```

**Webhook 端點**：`web/blueprints/webhook.py`
- 驗證 `X-Hub-Signature-256` 簽名
- 執行 `git pull` 
- `systemctl restart` 三個 Bot 服務
- 發送部署結果到 Discord Webhook

**Webhook 狀態**：✅ **完全正常運作**
- GitHub UI 可能顯示 "We couldn't deliver this payload"
- 原因：隧道無法完整回傳 HTTP 200 給 GitHub
- **不影響實際功能**，只影響 UI 記錄

**驗證 Webhook 運作**：
```bash
# 1. Flask 日誌
sudo journalctl -u kkgroup-api.service | grep webhook

# 2. Bot 重啟狀態
sudo systemctl status bot.service | grep Active

# 3. GitHub 交付記錄
# GitHub > Settings > Webhooks > Deliveries
```

### 2. Cron 排程任務（輔助維運）

| 排程 | 腳本 | 用途 |
|------|------|------|
| `*/5 * * * *` | `update_restart.py` | 定期 git pull + 重啟（備用） |
| `*/5 * * * *` | `sync_to_sheet.py` | Google Sheets 雙向同步 |
| `0 14 * * 3,6` | `refresh_all_lockers_cron.py` | 置物櫃批量更新（週三、六 14:00） |
| `0 3 * * 1` | `weekly_backup.py` | 每週備份（週一 03:00） |
| `0 18 * * *` | `refresh_knowledge_base.py` | 知識庫刷新（每天 18:00 台時間） |

**Cron 環境變數**（`crontab -e`）：
```bash
CRON_TZ=Asia/Taipei
PYTHONPATH=/home/ubuntu/kkgroup
PATH=/home/ubuntu/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

### 3. 統一維運入口
```bash
# 本地/VM 通用
python scripts/commands_manager.py <service> <action>

# 範例
python scripts/commands_manager.py bot restart
python scripts/commands_manager.py bot logs recent_50
python scripts/commands_manager.py diag tunnel_nginx
python scripts/commands_manager.py diag all_services
```

**指令註冊表**：`config/commands_registry.json`

## 網路和隧道

### 1. Cloudflare Tunnel
- **類型**：TryCloudflare 臨時隧道（免費、URL 可能變動）
- **配置**：`/root/.cloudflared/*.json` + `systemd` service
- **流量**：GitHub → Tunnel → Nginx → Flask:5000
- **注意**：隧道重啟 URL 會變，需更新 GitHub Webhook URL

### 2. Nginx 反向代理
**配置位置**：`config/nginx/nginx_default.conf` → `/etc/nginx/sites-enabled/default`

```nginx
server {
    listen 80;
    server_name _;
    
    # API 服務代理
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Webhook 端點
    location /webhook/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 靜態檔案
    location /static/ {
        alias /home/ubuntu/kkgroup/web/portal/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # 主要頁面
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. 隧道診斷
```bash
# 隧道進程狀態
sudo systemctl status cloudflared --no-pager

# 隧道配置
cat /root/.cloudflared/*.json 2>/dev/null | grep -o 'http.*' | head -5

# 隧道聆聽地址
sudo netstat -tlnp 2>/dev/null | grep cloudflare

# Nginx 存取日誌
sudo tail -50 /var/log/nginx/access.log
```

## 監控和日誌

### 1. 關鍵日誌查看
```bash
# Bot 錯誤/失敗（近 50/100 筆）
sudo journalctl -u bot.service -n 50 --no-pager | grep -iE 'error|fail|failed|critical'
sudo journalctl -u bot.service -n 100 --no-pager | grep -iE 'error|fail|failed|critical'

# API/Webhook 日誌
sudo journalctl -u kkgroup-api.service | grep webhook

# 隧道日誌
sudo journalctl -u cloudflared.service -n 50 --no-pager

# Nginx 錯誤日誌
sudo tail -50 /var/log/nginx/error.log
```

### 2. 狀態儀表板
- `status_dashboard.py`：系統資源、服務狀態監控
- Discord 通知：部署結果、錯誤告警、知識庫刷新結果

### 3. 知識庫自動刷新
- **排程**：每天 18:00（台灣時間）
- **腳本**：`scheduled_tasks/refresh_knowledge_base.py`
- **流程**：`scan_vm_state.py` → `ingest_knowledge.py` → 更新 `ai_memory.py` 知識庫
- **通知**：Discord Webhook（`KNOWLEDGE_WEBHOOK_URL` 或 `DISCORD_WEBHOOK_URL`）

## 備份和恢復

### 1. 資料庫備份原則
- **VM 為主，本地驗證後複製**
- **改資料庫前必備份**
- SQLite 檔案：`user_data.db`、`kkgroup.db`、`ruvector.db`

### 2. 自動備份（`weekly_backup.py`）
- 每週一 03:00 執行
- 打包專案目錄 + 資料庫
- 保留 30 天

### 3. 手動備份/恢復流程
```bash
# 本地驗證 → 複製到 VM → 重啟服務
gcloud compute scp user_data.db e193752468@instance-20250501-142333:/home/e193752468/kkgroup/ --zone=us-central1-c --tunnel-through-iap
ssh 到 VM → sudo systemctl restart bot.service shopbot.service uibot.service
```

## GCP SSH 連線（IAP）
```bash
# 標準連線
gcloud compute ssh e193752468@instance-20250501-142333 --zone=us-central1-c --tunnel-through-iap

# 執行單一指令
gcloud compute ssh e193752468@instance-20250501-142333 --zone=us-central1-c --tunnel-through-iap --command="sudo journalctl -u bot.service -n 50 --no-pager"
```

## 常見問題排查

| 現象 | 可能原因 | 解決方案 |
|------|----------|----------|
| Webhook GitHub UI 顯示失敗 | 隧道無法回傳 200 | 忽略，實際功能正常；檢查 Flask 日誌確認 |
| Bot 服務頻繁重啟 | 記憶體不足 (OOM) | 加 swap、檢查記憶體洩漏、調整 Restart 策略 |
| 隧道 URL 失效 | cloudflared 重啟 | 更新 GitHub Webhook URL、重啟 cloudflared.service |
| Nginx 502 Bad Gateway | Flask 未啟動 | `sudo systemctl restart kkgroup-api.service` |
| 紙娃娃修復不生效 | VM 未同步資料庫/代碼 | 1) `/admin_refresh_all_lockers` 2) 複製 DB 到 VM 3) 重啟服務 |
| 推播重複/遺漏 | anime_check_history 表問題 | 檢查 `scheduled_tasks/refresh_knowledge_base.py` 邏輯 |

## 相關文檔

- [Discord Bot 系統詳解](../concepts/discord-bot-system.md)
- [KK 園區經濟系統](kk-park-economy-system.md)
- [VM 操作指南](../entities/vm-operations.md)
- [Webhook 和隧道設定](webhook-and-tunnel.md)
- [編碼規則和路徑](coding-rules-and-paths.md)
- [指令註冊表](../entities/command-registry.md)
- [Bot Services](../entities/bot-services.md)
```python
#!/usr/bin/env python3
import subprocess
import os
import time

def update_and_restart():
    # 切換到專案目錄
    os.chdir('/home/ubuntu/kkgroup')
    
    # Git 拉取最新程式碼
    subprocess.run(['git', 'pull', 'origin', 'main'], check=True)
    
    # 重啟所有服務
    services = ['bot.service', 'shopbot.service', 'kkgroup-api.service']
    for service in services:
        subprocess.run(['sudo', 'systemctl', 'restart', service], check=True)
        time.sleep(5)  # 等待服務啟動
    
    print("部署完成")

if __name__ == "__main__":
    update_and_restart()
```

### 2. 自動部署機制
**GitHub Webhook 部署**:
```bash
# 主要部署方式：GitHub Webhook 即時觸發
# 當代碼 push 到 main 分支時自動部署
# 流程：Git Push → GitHub Webhook → VM Webhook 接收器 → Git Pull → 重啟服務

# 備用 Cron 任務（僅用於監控和維護）
*/5 * * * * /home/ubuntu/kkgroup/.venv/bin/python /home/ubuntu/kkgroup/scheduled_tasks/sync_to_sheet.py

# 置物櫃批量更新（每周三、六下午2點）
0 14 * * 3,6 /home/ubuntu/kkgroup/.venv/bin/python /home/ubuntu/kkgroup/scheduled_tasks/refresh_all_lockers_cron.py

# 每週一凌晨3點備份
0 3 * * 1 /home/ubuntu/kkgroup/.venv/bin/python /home/ubuntu/kkgroup/scheduled_tasks/weekly_backup.py
```

**Webhook 部署詳情**:
- **觸發條件**: Push 到 main/master 分支
- **執行位置**: `/web/blueprints/webhook.py`
- **操作流程**: Git Pull → 重啟所有服務
- **服務列表**: `bot.service`, `shopbot.service`, `uibot.service`
- **通知機制**: 部署結果發送到 Discord 頻道

### 3. 部署腳本
**自動部署腳本** (`config/scripts/deploy_gcp.sh`):
```bash
#!/bin/bash
# GCP 自動部署腳本

set -e

echo "開始部署 KKGroup 到 GCP..."

# 1. 更新系統套件
sudo apt update && sudo apt upgrade -y

# 2. 安裝 Python 依賴
/home/ubuntu/.venv/bin/pip install -r requirements.txt

# 3. 設定檔案權限
sudo chown -R ubuntu:ubuntu /home/ubuntu/kkgroup
chmod +x /home/ubuntu/kkgroup/scheduled_tasks/*.py

# 4. 重新載入 systemd 配置
sudo systemctl daemon-reload

# 5. 啟動所有服務
sudo systemctl start bot.service
sudo systemctl start shopbot.service
sudo systemctl start kkgroup-api.service

# 6. 檢查服務狀態
sudo systemctl status bot.service --no-pager
sudo systemctl status shopbot.service --no-pager
sudo systemctl status kkgroup-api.service --no-pager

echo "部署完成！"
```

## 網路和隧道

### 1. Cloudflare Tunnel 配置
**隧道管理**:
```python
# 更新隧道 URL 腳本
import requests
import json
import os

def update_tunnel_url():
    # 獲取當前隧道 URL
    tunnel_url = "https://xxxx.trycloudflare.com"
    
    # 更新本地配置
    with open('locker_refresh_urls.json', 'w') as f:
        json.dump({"tunnel_url": tunnel_url}, f)
    
    # 通知 Discord
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if webhook_url:
        requests.post(webhook_url, json={
            "content": f"🔄 隧道 URL 已更新: {tunnel_url}"
        })

if __name__ == "__main__":
    update_tunnel_url()
```

### 2. Nginx 反向代理
**Nginx 配置** (`config/nginx/nginx_default.conf`):
```nginx
server {
    listen 80;
    server_name localhost;
    
    # API 服務代理
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 靜態檔案服務
    location /static/ {
        alias /home/ubuntu/kkgroup/web/portal/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # 主要頁面
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 監控和日誌

### 1. 系統監控
**狀態儀表板** (`status_dashboard.py`):
```python
import psutil
import discord
from datetime import datetime

class SystemMonitor:
    def get_system_stats(self):
        return {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'uptime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def get_service_status(self):
        services = ['bot.service', 'shopbot.service', 'kkgroup-api.service']
        status = {}
        for service in services:
            # 檢查服務狀態
            result = subprocess.run(['systemctl', 'is-active', service], 
                                  capture_output=True, text=True)
            status[service] = result.stdout.strip()
        return status
```

### 2. 日誌管理
**日誌輪轉配置** (`/etc/logrotate.d/kkgroup`):
```
/home/ubuntu/kkgroup/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 ubuntu ubuntu
    postrotate
        systemctl reload rsyslog
    endscript
}
```

### 3. 錯誤通知
**Webhook 通知系統**:
```python
import requests
import traceback

def send_error_notification(error_msg: str, context: str = ""):
    webhook_url = os.getenv('ERROR_WEBHOOK_URL')
    if not webhook_url:
        return
    
    embed = {
        "title": "🚨 KKGroup 錯誤通知",
        "description": f"**錯誤:** {error_msg}\n**上下文:** {context}",
        "color": 0xFF0000,
        "timestamp": datetime.now().isoformat()
    }
    
    requests.post(webhook_url, json={"embeds": [embed]})

# 使用範例
try:
    # 可能出錯的程式碼
    pass
except Exception as e:
    send_error_notification(str(e), "服務啟動")
```

## 備份和恢復

### 1. 自動備份
**每週備份腳本** (`scheduled_tasks/weekly_backup.py`):
```python
#!/usr/bin/env python3
import subprocess
import os
import datetime
import tarfile

def create_backup():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/home/ubuntu/backups/{timestamp}"
    
    # 建立備份目錄
    os.makedirs(backup_dir, exist_ok=True)
    
    # 備份專案檔案
    subprocess.run([
        'tar', '-czf', f'{backup_dir}/kkgroup.tar.gz',
        '-C', '/home/ubuntu', 'kkgroup'
    ], check=True)
    
    # 備份資料庫
    subprocess.run([
        'cp', '/home/ubuntu/kkgroup/data/database.db',
        f'{backup_dir}/database.db'
    ], check=True)
    
    # 清理舊備份 (保留30天)
    subprocess.run([
        'find', '/home/ubuntu/backups', '-type', 'd',
        '-mtime', '+30', '-exec', 'rm', '-rf', '{}', ';'
    ], check=True)
    
    print(f"備份完成: {backup_dir}")

if __name__ == "__main__":
    create_backup()
```

### 2. 恢復程序
**恢復腳本** (`config/scripts/restore_backup.sh`):
```bash
#!/bin/bash
# 備份恢復腳本

BACKUP_DIR=$1
if [ -z "$BACKUP_DIR" ]; then
    echo "用法: $0 <備份目錄>"
    exit 1
fi

echo "開始恢復備份: $BACKUP_DIR"

# 1. 停止所有服務
sudo systemctl stop bot.service
sudo systemctl stop shopbot.service
sudo systemctl stop kkgroup-api.service

# 2. 備份當前狀態
sudo cp -r /home/ubuntu/kkgroup /home/ubuntu/kkgroup.backup.$(date +%Y%m%d_%H%M%S)

# 3. 恢復專案檔案
sudo tar -xzf $BACKUP_DIR/kkgroup.tar.gz -C /home/ubuntu/

# 4. 恢復資料庫
sudo cp $BACKUP_DIR/database.db /home/ubuntu/kkgroup/data/

# 5. 重新設定權限
sudo chown -R ubuntu:ubuntu /home/ubuntu/kkgroup

# 6. 重啟服務
sudo systemctl start bot.service
sudo systemctl start shopbot.service
sudo systemctl start kkgroup-api.service

echo "恢復完成！"
```

## 安全配置

### 1. 防火牆設定
```bash
# UFW 防火牆配置
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 5000  # API 服務端口
```

### 2. SSH 安全
**SSH 配置** (`/etc/ssh/sshd_config`):
```
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
```

### 3. 環境變數保護
**.env 檔案保護**:
```bash
# 設定檔案權限
chmod 600 /home/ubuntu/kkgroup/.env
chown ubuntu:ubuntu /home/ubuntu/kkgroup/.env

# 確保不會被提交到 Git
echo ".env" >> /home/ubuntu/kkgroup/.gitignore
```

## 效能優化

### 1. 系統資源監控
```python
import psutil
import time

def monitor_resources():
    while True:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        if cpu > 80:
            send_alert(f"CPU 使用率過高: {cpu}%")
        if memory > 80:
            send_alert(f"記憶體使用率過高: {memory}%")
        if disk > 80:
            send_alert(f"磁碟使用率過高: {disk}%")
        
        time.sleep(60)  # 每分鐘檢查一次
```

### 2. 服務自動重啟
**健康檢查腳本**:
```python
import subprocess
import requests
import time

def health_check():
    services = {
        'bot.service': 'http://localhost:8080/health',
        'kkgroup-api.service': 'http://localhost:5000/api/health'
    }
    
    for service, health_url in services.items():
        try:
            response = requests.get(health_url, timeout=10)
            if response.status_code != 200:
                restart_service(service)
        except requests.RequestException:
            restart_service(service)

def restart_service(service):
    print(f"重啟服務: {service}")
    subprocess.run(['sudo', 'systemctl', 'restart', service], check=True)
```

## 故障排除

### 1. 常見問題
**服務無法啟動**:
```bash
# 檢查服務狀態
sudo systemctl status bot.service

# 查看詳細錯誤
sudo journalctl -u bot.service -n 50 --no-pager

# 檢查配置檔案
python -m py_compile bots/bot.py
```

**網路連線問題**:
```bash
# 檢查端口監聽
sudo netstat -tlnp | grep :5000

# 檢查防火牆
sudo ufw status

# 測試連線
curl -I http://localhost:5000
```

### 2. 緊急恢復程序
```bash
# 1. 快速重啟所有服務
sudo systemctl restart bot.service shopbot.service kkgroup-api.service

# 2. 檢查系統資源
free -h
df -h
top

# 3. 查看最近的日誌
sudo journalctl -n 100 --no-pager

# 4. 如果必要，回滾到上一個版本
git log --oneline -5
git reset --hard HEAD~1
```

## 相關文檔

- [專案架構總覽](project-architecture.md)
- [VM 操作指南](../entities/vm-operations.md)
- [Webhook 和隧道設定](webhook-and-tunnel.md)
- [Discord Bot 系統詳解](discord-bot-system.md)
- [LogMonitor 與 Auto AI Fix 流程總覽](log_monitor_pipeline.md)
- [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)
