# 系統部署指南

## 概述

本指南詳細說明如何在不同環境中部署自動 AI Debug 系統，包括開發環境、測試環境和生產環境。

## 部署環境

### 開發環境 (Development)

**用途**：功能開發和測試
**特點**：詳細日誌、快速重啟、模擬數據

**系統要求**：
- Ubuntu 20.04+ 或 macOS 10.15+
- Python 3.11+
- Git 2.25+
- 至少 2GB RAM
- 5GB 可用硬碟空間

### 測試環境 (Testing)

**用途**：集成測試和性能驗證
**特點**：真實數據、監控指標、自動化測試

**系統要求**：
- Ubuntu 22.04 LTS
- Python 3.11+
- Docker 20.10+
- 4GB RAM
- 20GB 可用硬碟空間

### 生產環境 (Production)

**用途**：正式運行和服務
**特點**：高可用性、自動恢復、監控告警

**系統要求**：
- GCP e2-micro 或同級
- Ubuntu 22.04 LTS
- Python 3.11+
- 1GB RAM + 4GB swap
- 30GB 可用硬碟空間

## 部署步驟

### 1. 環境準備

#### 基礎環境設置

```bash
# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝必要套件
sudo apt install -y python3 python3-pip python3-venv git curl wget

# 安裝 Python 依賴
pip3 install --user python-dotenv requests aiohttp pytz

# 驗證安裝
python3 --version
pip3 --version
```

#### Git 配置

```bash
# 配置 Git 用戶
git config --global user.name "AI Auto Fix Bot"
git config --global user.email "ai-fix@kkgroup.local"

# 配置 SSH 密鑰（如需要）
ssh-keygen -t rsa -b 4096 -C "ai-fix@kkgroup.local"

# 添加到 GitHub（手動操作）
cat ~/.ssh/id_rsa.pub
```

### 2. 專案設置

#### 克隆專案

```bash
# 克隆專案
git clone https://github.com/chenkankan1103/kkgroup.git
cd kkgroup

# 檢查分支
git branch -a
git checkout main
```

#### 環境變數設置

```bash
# 創建環境變數文件
cp .env.example .env

# 編輯環境變數
nano .env
```

**`.env` 文件內容**：
```bash
# NVIDIA AI 配置
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro

# GitHub 配置
GITHUB_TOKEN=your-github-token
GITHUB_REPO_OWNER=chenkankan1103
GITHUB_REPO_NAME=kkgroup

# Discord 配置
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-webhook

# GCP 配置（可選）
GCP_PROJECT=kkgroup
GCP_ZONE=us-central1-a
GCP_INSTANCE=instance-20250501-142333

# 系統配置
LOG_LEVEL=INFO
DEBUG_MODE=false
```

### 3. 自動 Debug 系統部署

#### Systemd 服務部署

```bash
# 複製服務文件
sudo cp config/services/auto-debug.service /etc/systemd/system/

# 設置服務權限
sudo chmod 644 /etc/systemd/system/auto-debug.service

# 重新載入 systemd
sudo systemctl daemon-reload

# 啟動服務
sudo systemctl start auto-debug.service

# 設置開機自啟
sudo systemctl enable auto-debug.service

# 檢查服務狀態
sudo systemctl status auto-debug.service
```

補充：2026-05-26 起，`auto-debug.service` 的實際執行入口為 `scripts/auto_error_detector.py`，不是舊版文件提到的 `cogs.common.auto_debug_system`。部署時應一併同步最新的 [config/services/auto-debug.service](../../../config/services/auto-debug.service) 與 [scripts/auto_error_detector.py](../../../scripts/auto_error_detector.py)。

#### 服務配置驗證

```bash
# 檢查服務配置
sudo systemctl cat auto-debug.service

# 檢查服務依賴
sudo systemctl list-dependencies auto-debug.service

# 檢查服務日誌配置
sudo journalctl --unit=auto-debug.service --show-cursor
```

### 4. GitHub Actions 配置

#### Secrets 設置

1. **進入 GitHub Repository**
   - 網址：`https://github.com/chenkankan1103/kkgroup`
   - 點擊：Settings → Secrets and variables → Actions

2. **添加 Repository Secrets**
   
   **必需 Secrets**：
   ```yaml
   NVIDIA_API_KEY: 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
   DISCORD_WEBHOOK_URL: https://discord.com/api/webhooks/your-webhook-url
   GITHUB_TOKEN: github_pat_your-token-here
   ```

   **可選 Secrets**：
   ```yaml
   GCP_SA_KEY: {"type": "service_account", ...}  # GCP Service Account JSON
   ```

3. **驗證 Secrets**
   - 檢查所有必需的 Secrets 是否已設置
   - 測試工作流程是否能正常讀取 Secrets

#### 工作流程驗證

```bash
# 測試手動觸發
# 進入 GitHub → Actions → "AI Debug Monitor"
# 點擊 "Run workflow" 進行測試

# 測試自動觸發
# 修改系統日誌觸發錯誤檢測
```

### 5. 網路和安全配置

#### 防火牆設置

```bash
# 開放必要端口（如果需要）
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8080/tcp  # 可能的 API 端口

# 啟用防火牆
sudo ufw enable

# 檢查防火牆狀態
sudo ufw status
```

#### SSL/TLS 配置

```bash
# 安裝 certbot（如需要）
sudo apt install -y certbot python3-certbot-nginx

# 申請 SSL 證書
sudo certbot --nginx -d your-domain.com

# 設置自動續期
sudo crontab -e
# 添加：0 12 * * * /usr/bin/certbot renew --quiet
```

## 環境特定配置

### 開發環境

#### 調試配置

```python
# auto_debug_system.py 開發配置
DEBUG_MODE = True
LOG_LEVEL = "DEBUG"
MOCK_ERRORS = True  # 模擬錯誤進行測試

# 開發模式特點
- 詳細的日誌輸出
- 模擬錯誤生成
- 快速重啟週期
- 本地測試數據
```

#### 測試數據

```python
# 測試用錯誤日誌
TEST_ERROR_LOGS = """
[ERROR] 2024-05-12 20:15:00 - Test error for debugging
Traceback (most recent call last):
  File "/test/bot.py", line 100, in test_function
    raise ValueError("Test error")
ValueError: Test error
"""
```

### 測試環境

#### 監控配置

```python
# 測試環境監控配置
MONITORING_INTERVAL = 30  # 30 秒檢查一次
ERROR_THRESHOLD = 2      # 2 個錯誤觸發
ALERT_COOLDOWN = 300    # 5 分鐘冷卻時間

# 測試環境特點
- 真實數據處理
- 性能指標收集
- 自動化測試執行
- 集成測試報告
```

#### 性能測試

```bash
# 執行性能測試
python3 -m pytest tests/performance/

# 負載測試
python3 scripts/load_test.py

# 記憶使用監控
python3 scripts/memory_monitor.py
```

### 生產環境

#### 高可用性配置

```python
# 生產環境配置
DEBUG_MODE = False
LOG_LEVEL = "INFO"
ERROR_THRESHOLD = 3      # 3 個錯誤觸發
ALERT_COOLDOWN = 600    # 10 分鐘冷卻時間

# 生產環境特點
- 最小日誌輸出
- 錯誤過濾
- 自動恢復機制
- 監控告警集成
```

#### 備份策略

```bash
# 每日備份腳本
#!/bin/bash
BACKUP_DIR="/backup/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 備份配置文件
cp -r /home/e193752468/kkgroup/config $BACKUP_DIR/

# 備份日誌
cp -r /var/log/auto-debug $BACKUP_DIR/

# 備份資料庫（如果適用）
# pg_dump kkgroup_db > $BACKUP_DIR/database.sql

# 清理舊備份（保留 7 天）
find /backup -type d -mtime +7 -exec rm -rf {} \;
```

## 監控和維護

### 系統監控

#### 服務狀態檢查

```bash
# 檢查所有相關服務
services=("auto-debug" "bot" "shopbot" "uibot")

for service in "${services[@]}"; do
    status=$(systemctl is-active $service)
    echo "$service: $status"
    
    if [ "$status" != "active" ]; then
        # 發送告警
        curl -X POST "$DISCORD_WEBHOOK_URL" \
             -H "Content-Type: application/json" \
             -d "{\"content\": \"🚨 服務 $service 異常: $status\"}"
    fi
done
```

#### 資源使用監控

```bash
# CPU 使用率
cpu_usage=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)% id.*/\1/" | cut -d. -f1)

# 記憶使用率
memory_usage=$(free | grep Mem | awk '{printf("%.2f", $3/$2 * 100.0)}')

# 硬碟使用率
disk_usage=$(df -h / | awk 'NR==2 {print $5}')

# 發送監控報告
curl -X POST "$DISCORD_WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d "{\"content\": \"📊 系統資源使用率\\nCPU: ${cpu_usage}%\\n記憶體: ${memory_usage}%\\n硬碟: ${disk_usage}\"}"
```

### 日誌管理

#### 日誌輪轉

```bash
# 配置 logrotate
sudo nano /etc/logrotate.d/auto-debug

# 內容：
/var/log/auto-debug/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 e193752468 e193752468
    postrotate
        systemctl reload auto-debug.service
}
```

#### 日誌分析

```bash
# 分析錯誤日誌
sudo journalctl -u auto-debug.service --since "1 hour ago" | grep ERROR

# 統計錯誤類型
sudo journalctl -u auto-debug.service --since "24 hours" | \
    awk '/ERROR/ {error_count++} END {print "24小時內錯誤數:", error_count}'

# 生成報告
python3 scripts/generate_error_report.py
```

## 故障排除

### 常見部署問題

#### 1. 服務啟動失敗

**症狀**：
```
Failed to start auto-debug.service: Unit auto-debug.service is masked.
```

**解決方案**：
```bash
# 檢查服務是否被遮罩
sudo systemctl status auto-debug.service

# 取消遮罩
sudo systemctl unmask auto-debug.service

# 重新啟動
sudo systemctl start auto-debug.service
```

#### 2. 環境變數未設置

**症狀**：
```
❌ NVIDIA_API_KEY 未設置，請先設置環境變數
```

**解決方案**：
```bash
# 檢查環境變數
echo $NVIDIA_API_KEY

# 重新載入環境變數
source /etc/environment

# 檢查 .env 文件
cat .env | grep NVIDIA_API_KEY
```

#### 3. GitHub Actions 權限問題

**症狀**：
```
Error: Permission denied: could not read from repository
```

**解決方案**：
```yaml
# 更新工作流程權限
permissions:
  contents: write
  issues: write
  pull-requests: write
  id-token: write
```

#### 4. 網路連接問題

**症狀**：
```
❌ NVIDIA API 調用失敗: Connection timeout
```

**解決方案**：
```bash
# 檢查網路連接
curl -I https://integrate.api.nvidia.com/v1

# 檢查 DNS 解析
nslookup integrate.api.nvidia.com

# 設置代理（如果需要）
export https_proxy=http://proxy.example.com:8080
export http_proxy=http://proxy.example.com:8080
```

## 維護和更新

### 系統更新

```bash
# 更新專案代碼
cd /home/e193752468/kkgroup
git pull origin main

# 重啟服務
sudo systemctl restart auto-debug.service

# 檢查更新後狀態
sudo systemctl status auto-debug.service
```

### 配置更新

```bash
# 更新環境變數
sudo nano /etc/environment
source /etc/environment

# 重載服務配置
sudo systemctl daemon-reload
sudo systemctl restart auto-debug.service
```

## 安全最佳實踐

### 1. 訪問控制

```bash
# 限制 SSH 訪問
sudo nano /etc/ssh/sshd_config

# 添加：
AllowUsers e193752468
PasswordAuthentication no
PubkeyAuthentication yes
```

### 2. 資料保護

```bash
# 設置文件權限
chmod 600 .env
chmod 700 /home/e193752468/.ssh/

# 加密敏感資料
gpg --symmetric --cipher-algo AES256 sensitive_data.txt
```

### 3. 監控和審計

```bash
# 啟用審計日誌
sudo auditctl -e

# 監控系統訪問
sudo ausearch -k recent,success -ts recent

# 定期審查日誌
sudo journalctl -u auto-debug.service --since "1 week" | audit
```

## 相關文檔

- [自動 AI Debug 系統](automatic-ai-debug-system.md)
- [NVIDIA AI 集成](nvidia-ai-integration.md)
- [GitHub Actions 工作流程](github-actions-workflows.md)
- [故障排除手冊](../troubleshooting/system-troubleshooting.md)
