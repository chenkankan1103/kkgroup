# 方案 B：Python API + Google Apps Script 混合方案

## 📋 架構概述

```
Google Sheets (前端)
    ↓ (Apps Script)
    ↓
Flask API (Python 後端，GCP 實例)
    ↓
SQLite 資料庫 (本地)
    ↓
Discord Bot
```

## ✅ 已完成的部分

- ✅ `sheet_sync_manager.py` - 核心同步邏輯（支援科學記號、虛擬帳號過濾）
- ✅ `sheet_sync_api.py` - Flask REST API 伺服器
- ✅ `SHEET_SYNC_APPS_SCRIPT.gs` - Google Apps Script 客戶端代碼
- ✅ `cleanup_virtual_accounts.py` - 虛擬帳號清理工具

## 🚀 部署步驟

### 第 1 步：本地測試（Windows 開發機）

1. 確認 Flask API 已啟動：
```bash
python sheet_sync_api.py
```

2. 在瀏覽器測試 API：
```
http://localhost:5000/api/health
```

應該看到：
```json
{
  "status": "ok",
  "message": "Sheet Sync API 運行中",
  "timestamp": "2026-02-05T..."
}
```

### 第 2 步：生產環境部署（GCP 實例）

1. 連接到 GCP 實例並拉取最新代碼：
```bash
cd /path/to/kkgroup
git pull
```

2. **建立虛擬環境**（因為系統 Python 受限）：
```bash
# 建立虛擬環境
python3 -m venv venv

# 啟用虛擬環境
source venv/bin/activate

# 升級 pip
pip install --upgrade pip

# 安裝依賴
pip install -r requirements.txt
pip install gunicorn
```

3. **啟動 Flask API**

**選項 A：測試運行（前台，用於調試）**
```bash
source venv/bin/activate
gunicorn -w 4 -b 0.0.0.0:5000 sheet_sync_api:app
```

**選項 B：使用 Supervisor（後台，生產推薦）**

編輯 `/etc/supervisor/conf.d/sheet-sync-api.conf`：
```bash
sudo nano /etc/supervisor/conf.d/sheet-sync-api.conf
```

複製下面的內容（**重要**：改 `/path/to/kkgroup` 為實際路徑，改 `ubuntu` 為你的用戶名）：
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

保存後啟動：
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start sheet-sync-api
```

4. 驗證 API 在生產環境運行：
```bash
curl http://localhost:5000/api/health
```

### 第 3 步：配置 Google Sheets

1. 打開你的 Google Sheets（「玩家資料」）
2. 選擇「擴充功能」→「Apps Script」
3. 複製 `SHEET_SYNC_APPS_SCRIPT.gs` 中的所有代碼到 Apps Script 編輯器
4. **重要**：找到這一行並改為你的伺服器 IP 地址或域名：
   ```javascript
   const API_ENDPOINT = "http://YOUR_SERVER_IP:5000";
   ```
   
   例如：
   ```javascript
   const API_ENDPOINT = "http://35.201.XXX.XXX:5000";  // GCP 公開 IP
   ```

5. 按「保存」並關閉編輯器

### 第 4 步：首次同步測試

1. 重新整理 Google Sheets（F5）
2. 頁面頂部應該出現「🔄 同步工具」功能表
3. 點選「🔄 同步工具」→「✅ 檢查 API 連接」
   - 如果顯示 ✅，表示連接成功
   - 如果顯示 ❌，檢查伺服器位址和防火牆設定

4. 如果連接成功，點選「📤 同步到資料庫」執行第一次同步

## 📊 使用說明

### 日常同步流程

1. **編輯 Google Sheets**
   - 在「玩家資料」SHEET 中編輯數據
   - 儲存更改

2. **執行同步**
   - 點選「🔄 同步工具」→「📤 同步到資料庫」
   - 等待完成提示

3. **查看結果**
   - 點選「📊 查看同步狀態」檢查統計
   - 真實玩家數、虛擬帳號數等

### 清理虛擬帳號

點選「🔄 同步工具」→「🧹 清理虛擬帳號」

該工具會：
- ✅ 自動偵測並列出所有 `Unknown_XXXX` 帳號
- ✅ 確認後刪除
- ✅ 返回刪除結果

## 🔧 故障排除

### 問題 1：「無法連接到 API」

**原因可能**：
- Flask 伺服器未啟動
- API 位址錯誤
- 防火牆阻止

**解決方案**：
```bash
# 檢查 Flask 是否運行
ps aux | grep sheet_sync_api

# 檢查 5000 端口
netstat -tulpn | grep 5000

# 從 GCP 實例測試本地連接
curl http://localhost:5000/api/health

# 從你的電腦遠端測試（用 GCP 公開 IP）
curl http://YOUR_SERVER_IP:5000/api/health
```

### 問題 2：API 回應 500 錯誤

檢查伺服器日誌：
```bash
# 如果用 Supervisor
tail -f /var/log/sheet-sync-api.err.log
tail -f /var/log/sheet-sync-api.out.log

# 如果用 Gunicorn，看終端輸出
```

常見原因：
- 表頭格式錯誤（有空欄、特殊字符）
- 資料行格式不符
- 資料庫鎖定

### 問題 3：同步後資料未出現在 DB

檢查虛擬帳號是否被過濾：
```bash
python cleanup_virtual_accounts.py
```

如果有 `Unknown_XXXX` 帳號，執行清理。

## 📈 監控

### 查看即時日誌

**本地開發**：
終端會直接顯示日誌

**生產環境（Supervisor）**：
```bash
tail -f /var/log/sheet-sync-api.out.log
```

**生產環境（Gunicorn）**：
```bash
tail -f /var/log/gunicorn.log
```

### API 統計

在 Apps Script 中點選「📊 查看同步狀態」會顯示：
- 真實玩家數
- 虛擬帳號數
- KKCoin 總計
- 欄位數量

## 🔒 安全建議

1. **保護 API 端口**
   - 在 GCP 防火牆設定中限制只允許特定 IP 存取
   - 考慮使用 VPN 或 SSH 隧道

2. **認證（可選）**
   - 在 Flask API 中新增簡單的 API Key 驗證
   - 在 Apps Script 中傳遞 API Key

3. **HTTPS（生產環境）**
   - 使用 SSL 證書（例如 Let's Encrypt）
   - 配置 Nginx 反向代理

## 📞 支援

如有問題：
1. 檢查伺服器日誌
2. 驗證 API 連接狀態
3. 檢查 SHEET 表頭格式
4. 查看 Apps Script 執行日誌（點選「執行日誌」）
