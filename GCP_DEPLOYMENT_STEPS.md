# GCP 實例上的部署步驟（完整指南）

## 🔐 連接到 GCP 實例

```bash
gcloud compute ssh instance-20250501-142333
```

## 📥 步驟 1：拉取最新代碼

```bash
cd /path/to/kkgroup
git pull origin main
```

## 🐍 步驟 2：建立和配置虛擬環境

```bash
# 建立虛擬環境
python3 -m venv venv

# 啟用虛擬環境
source venv/bin/activate

# 升級 pip、setuptools、wheel
pip install --upgrade pip setuptools wheel

# 安裝依賴
pip install -r requirements.txt

# 安裝 Gunicorn
pip install gunicorn

# 驗證安裝
python3 -c "from sheet_sync_api import app; print('✅ Flask 應用載入成功')"
```

## 🧪 步驟 3：測試 Flask API（前台運行）

```bash
# 確保虛擬環境已激活
source venv/bin/activate

# 啟動 Gunicorn（前台，用於測試）
gunicorn -w 4 -b 0.0.0.0:5000 sheet_sync_api:app
```

**預期輸出：**
```
[2026-02-05 XX:XX:XX +0000] [PID] [INFO] Starting gunicorn X.X.X
[2026-02-05 XX:XX:XX +0000] [PID] [INFO] Listening at: http://0.0.0.0:5000 (PID)
[2026-02-05 XX:XX:XX +0000] [PID] [INFO] Using worker: sync
[2026-02-05 XX:XX:XX +0000] [PID] [INFO] Worker spawned (pid: PID)
```

按 `Ctrl+C` 停止測試。

## ✅ 步驟 4：驗證 API 連接

在另一個終端中：

```bash
# 測試健康檢查端點
curl http://localhost:5000/api/health

# 應該看到：
# {"status":"ok","message":"Sheet Sync API 運行中","timestamp":"2026-02-05T..."}

# 測試統計端點
curl http://localhost:5000/api/stats

# 應該看到資料庫統計資訊
```

## 🎯 步驟 5：配置 Supervisor（生產環境後台運行）

### A. 安裝 Supervisor

```bash
sudo apt-get update
sudo apt-get install -y supervisor
```

### B. 建立配置檔案

```bash
sudo nano /etc/supervisor/conf.d/sheet-sync-api.conf
```

複製下面內容（**重要**：改 `PATH_TO_PROJECT` 和 `USERNAME`）：

```ini
[program:sheet-sync-api]
directory=/path/to/kkgroup
command=/path/to/kkgroup/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 sheet_sync_api:app
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/sheet-sync-api.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
user=ubuntu
environment=PATH="/path/to/kkgroup/venv/bin",PYTHONUNBUFFERED=1
startsecs=10
stopwaitsecs=10
```

保存（Ctrl+X，按 Y，按 Enter）

### C. 啟動 Supervisor 服務

```bash
# 讀取新配置
sudo supervisorctl reread

# 更新 Supervisor
sudo supervisorctl update

# 啟動服務
sudo supervisorctl start sheet-sync-api

# 檢查狀態
sudo supervisorctl status sheet-sync-api
```

**預期輸出：**
```
sheet-sync-api                   RUNNING   pid 1234, uptime 0:00:10
```

### D. 查看即時日誌

```bash
# 查看最後 50 行日誌
tail -f /var/log/sheet-sync-api.log

# 或查看 Supervisor 日誌
sudo tail -f /var/log/supervisor/supervisord.log
```

## 🔧 常用命令

```bash
# 啟動服務
sudo supervisorctl start sheet-sync-api

# 停止服務
sudo supervisorctl stop sheet-sync-api

# 重啟服務
sudo supervisorctl restart sheet-sync-api

# 檢查狀態
sudo supervisorctl status

# 查看即時日誌
sudo tail -f /var/log/sheet-sync-api.log

# 遠端測試連接（用 GCP 公開 IP）
curl http://YOUR_PUBLIC_IP:5000/api/health
```

## 🌐 步驟 6：設定防火牆規則（GCP 控制台）

1. 進入 [GCP 控制台](https://console.cloud.google.com)
2. 進入「計算引擎」→「防火牆」
3. 建立新規則，允許 TCP 5000 端口：
   - **名稱**：allow-sheet-sync-api
   - **目標**：你的實例
   - **來源 IP 範圍**：`0.0.0.0/0` 或你的 IP
   - **通訊協定**：TCP
   - **連接埠**：5000

## 🔌 步驟 7：更新 Google Sheets Apps Script

1. 打開 [Google Sheets](https://sheets.google.com) → 你的「玩家資料」
2. 「擴充功能」→「Apps Script」
3. 打開編輯器
4. 找到這一行並改為你的 **GCP 公開 IP**：
   ```javascript
   const API_ENDPOINT = "http://YOUR_PUBLIC_IP:5000";
   ```
   
   例如：
   ```javascript
   const API_ENDPOINT = "http://35.201.123.45:5000";
   ```

5. 按「保存」

## 🧪 步驟 8：首次同步測試

1. 重新整理 Google Sheets（F5）
2. 應該看到頁面頂部有「🔄 同步工具」功能表
3. 點選「✅ 檢查 API 連接」
   - ✅ 成功 → 進行下一步
   - ❌ 失敗 → 檢查 IP 地址、防火牆設定、Supervisor 狀態

4. 點選「📤 同步到資料庫」執行首次同步
5. 檢查結果（應該看到更新/新增的記錄數）

## 📊 監控和維護

### 檢查服務健康狀態

```bash
# 檢查進程是否運行
ps aux | grep gunicorn

# 檢查 5000 端口
netstat -tulpn | grep 5000

# 檢查 Supervisor 狀態
sudo supervisorctl status
```

### 如果服務停止

```bash
# 查看錯誤原因
sudo cat /var/log/sheet-sync-api.log

# 重啟服務
sudo supervisorctl restart sheet-sync-api
```

## 🎓 故障排除

### 問題 1：「permission denied」

確保虛擬環境路徑正確，檢查文件權限：
```bash
ls -la /path/to/kkgroup/venv/bin/gunicorn
```

### 問題 2：「無法連接到 API」

```bash
# 檢查 5000 端口是否開放
sudo lsof -i :5000

# 檢查防火牆
sudo iptables -L -n

# 從實例內部測試
curl http://localhost:5000/api/health
```

### 問題 3：「資料庫鎖定錯誤」

```bash
# 重啟服務會自動解鎖
sudo supervisorctl restart sheet-sync-api
```

## ✅ 部署完成檢查清單

- [ ] Git pull 成功
- [ ] 虛擬環境建立並激活
- [ ] 依賴安裝完成
- [ ] Flask 應用測試通過
- [ ] Gunicorn 前台測試成功
- [ ] API 健康檢查通過
- [ ] Supervisor 配置完成
- [ ] 防火牆規則設定
- [ ] Google Sheets Apps Script 配置
- [ ] 首次同步測試成功

---

完成上述步驟後，SHEET ↔ DB 同步系統就運行在生產環境中了！🎉
