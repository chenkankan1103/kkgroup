# 自動 AI Debug 系統設置指南

## 🎯 系統概述

這個系統能夠：
1. **自動檢測系統錯誤**：監控 Discord Bot 服務狀態
2. **觸發 GitHub Actions**：檢測到錯誤時自動觸發 AI 分析
3. **AI 分析和修復**：使用 NVIDIA AI 分析錯誤並生成修復代碼
4. **自動上傳修復**：將修復代碼自動提交到專案

## 📁 文件結構

```
kkgroup/
├── cogs/common/
│   └── auto_debug_system.py          # 自動錯誤檢測系統
├── scripts/
│   └── auto_ai_fix.py               # AI 修復代碼生成腳本
├── .github/workflows/
│   ├── ai-debug-monitor.yml           # 手動觸發的 debug 工作流程
│   └── auto-ai-fix.yml             # 自動觸發的修復工作流程
└── config/services/
    └── auto-debug.service            # systemd 服務配置
```

## 🔧 設置步驟

### 1. 設置 GitHub Secrets

在 GitHub Repository 的 Settings → Secrets and variables → Actions 中設置：

1. **NVIDIA_API_KEY** (必需)
   ```
   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
   ```

2. **DISCORD_WEBHOOK_URL** (必需)
   ```
   您的 Discord Webhook URL
   ```

3. **GITHUB_TOKEN** (必需)
   ```
   GitHub Personal Access Token (需要 repo 權限)
   ```

4. **GCP_SA_KEY** (可選)
   ```
   GCP Service Account JSON Key (用於真實 VM 連接)
   ```

### 2. 安裝自動 Debug 服務

在 GCP VM 上執行：

```bash
# 1. 複製服務文件
sudo cp config/services/auto-debug.service /etc/systemd/system/

# 2. 重新載入 systemd
sudo systemctl daemon-reload

# 3. 啟動服務
sudo systemctl start auto-debug.service

# 4. 設置開機自啟
sudo systemctl enable auto-debug.service

# 5. 檢查服務狀態
sudo systemctl status auto-debug.service
```

### 3. 設置環境變數

在 VM 上設置必要的環境變數：

```bash
# 編輯環境變數文件
sudo nano /etc/environment

# 添加以下內容
GITHUB_TOKEN=your_github_token_here
DISCORD_WEBHOOK_URL=your_discord_webhook_here
GITHUB_WEBHOOK_URL=optional_legacy_webhook_here

# 重新載入環境變數
source /etc/environment
```

## 🚀 使用方法

### 自動模式 (推薦)

系統會自動：
- 每 60 秒檢查一次服務狀態
- 檢測到錯誤時觸發 GitHub Actions
- AI 分析錯誤並生成修復代碼
- 自動提交修復代碼到專案
- 發送 Discord 通知

### 閉環關鍵要求

- repository_dispatch 必須送出 event_type 與 client_payload
- client_payload 至少要包含 timestamp、severity、source、error_logs
- GitHub Actions 若要讀取 GCP VM 日誌，必須先完成 gcloud 安裝與認證
### 手動觸發

1. **進入 GitHub Actions**
   - 網址：`https://github.com/chenkankan1103/kkgroup/actions`

2. **選擇工作流程**
   - `AI Debug Monitor`：手動 debug 分析
   - `Auto AI Fix`：由自動系統觸發

3. **配置參數**
   - Debug 類型：`auto`/`force`/`test`
   - 自定義日誌：可貼上特定錯誤日誌

## 📊 監控和日誌

### 查看自動 Debug 系統日誌

```bash
# 查看服務日誌
sudo journalctl -u auto-debug.service -f

# 查看最近的日誌
sudo journalctl -u auto-debug.service -n 50
```

### 查看 GitHub Actions 日誌

1. 進入 GitHub Actions 頁面
2. 點擊具體的工作流程執行
3. 查看各個步驟的詳細日誌

## 🔍 故障排除

### 常見問題

1. **服務無法啟動**
   ```bash
   # 檢查 Python 路徑
   which python3
   # 檢查模組路徑
   python3 -c "import sys; print(sys.path)"
   ```

2. **GitHub Actions 失敗**
   - 檢查 Secrets 是否正確設置
   - 確認 GITHUB_TOKEN 有足夠權限
   - 查看 NVIDIA API Key 是否有效

3. **AI 分析失敗**
   - 檢查 NVIDIA API 配額
   - 確認網路連接
   - 查看錯誤日誌格式

### 重啟服務

```bash
# 重啟自動 Debug 服務
sudo systemctl restart auto-debug.service

# 查看重啟後的狀態
sudo systemctl status auto-debug.service
```

## 📈 效能調整

### 調整檢查頻率

在 `auto_debug_system.py` 中修改：

```python
# 修改監控循環的等待時間
await asyncio.sleep(60)  # 改為 30 秒更頻繁檢查
```

### 調整錯誤閾值

```python
# 修改錯誤觸發閾值
error_threshold = 2  # 改為 1 更敏感
```

## 🎯 預期效果

設置完成後，系統將會：

1. **7x24 小時監控**：持續監控系統健康狀態
2. **智能錯誤分析**：AI 深度分析錯誤根本原因
3. **自動修復生成**：根據分析結果生成具體修復代碼
4. **即時通知**：Discord 即時收到錯誤和修復通知
5. **版本控制**：所有修復代碼自動記錄在 Git 歷史中

## 📞 技術支援

如果遇到問題：

1. 查看 GitHub Actions 執行日誌
2. 檢查自動 Debug 服務狀態
3. 確認環境變數設置正確
4. 驗證 NVIDIA API 連接

---

**注意**：這是一個自動化系統，建議先在測試環境中驗證功能正常後再部署到生產環境。
