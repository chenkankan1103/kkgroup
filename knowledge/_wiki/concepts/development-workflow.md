# 開發工作流程

## 概述

本文檔說明 KKGroup 專案的標準開發流程，包含修改、測試和部署的完整步驟。

## 開發流程

### 1. 本地開發
```bash
# 1. 創建功能分支
git checkout -b feature/新功能名稱

# 2. 進行開發修改
# 編輯相關檔案...

# 3. 本地測試
python -m pytest  # 如果有測試
python bots/bot.py  # 手動測試
```

### 2. 提交代碼
```bash
# 1. 添加修改的檔案
git add .

# 2. 提交代碼（使用有意義的提交訊息）
git commit -m "feat: 新增功能描述
- 詳細說明修改內容
- 影響的模組或檔案
- 相關的 issue 編號"

# 3. 推送到遠端
git push origin feature/新功能名稱
```

### 3. 合併到主分支
```bash
# 1. 切換到主分支
git checkout main

# 2. 拉取最新代碼
git pull origin main

# 3. 合併功能分支
git merge feature/新功能名稱

# 4. 推送到主分支
git push origin main
```

## 自動部署機制

### GitHub Webhook 部署
- **觸發條件**: Push 到 `main` 或 `master` 分支
- **執行流程**: 
  1. GitHub 發送 webhook 到 VM
  2. VM 接收器執行 `git pull`
  3. 自動重啟所有服務
  4. 發送部署結果到 Discord

### 服務列表
- `bot.service` - 主 Discord Bot
- `shopbot.service` - 商店 Bot  
- `uibot.service` - UI Bot
- `kkgroup-api.service` - Web API 服務

## 重要提醒

### ⚠️ 每次修改後務必上傳 GitHub

**為什麼需要上傳？**
1. **自動部署**: Push 後系統會自動部署到生產環境
2. **版本控制**: 確保修改不會遺失
3. **團隊協作**: 讓其他成員了解最新變更
4. **備份機制**: GitHub 作為程式碼備份

**標準流程：**
```
修改代碼 → 本地測試 → git add → git commit → git push → 自動部署
```

### 提交訊息規範
使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```bash
# 功能新增
git commit -m "feat: 新增用戶認證功能"

# 錯誤修復
git commit -m "fix: 修復置物櫃更新失敗問題"

# 文檔更新
git commit -m "docs: 更新部署說明文檔"

# 樣式調整
git commit -m "style: 調整 UI 按鈕樣式"

# 重構代碼
git commit -m "refactor: 重構資料庫查詢邏輯"

# 效能優化
git commit -m "perf: 優化 API 回應速度"

# 測試相關
git commit -m "test: 新增用戶註冊測試案例"
```

## 緊急修復流程

### 快速修復
```bash
# 1. 直接在 main 分支修改
git checkout main

# 2. 快速修復問題
# 編輯檔案...

# 3. 立即提交和推送
git add .
git commit -m "fix: 緊急修復 - [問題描述]"
git push origin main

# 系統會自動部署，無需手動操作
```

### 回滾操作
```bash
# 1. 查看提交歷史
git log --oneline -10

# 2. 回滾到指定版本
git reset --hard <commit-hash>

# 3. 強制推送
git push origin main --force
```

## 部署監控

### 部署狀態檢查
1. **Discord 通知**: 系統會發送部署結果到系統頻道
2. **GitHub Actions**: 查看 Actions 頁面的執行狀態
3. **服務狀態**: 使用指令檢查服務是否正常運行

### 故障排除
```bash
# 檢查服務狀態
sudo systemctl status bot.service --no-pager

# 查看服務日誌
sudo journalctl -u bot.service -n 50 --no-pager

# 手動重啟服務
sudo systemctl restart bot.service
```

## 開發環境設定

### 本地環境需求
- Python 3.11+
- Git
- 編輯器 (VS Code 推薦)

### 環境變數
```bash
# 複製範例檔案
cp .env.example .env

# 編輯環境變數
vim .env
```

### 虛擬環境
```bash
# 創建虛擬環境
python -m venv .venv

# 啟動虛擬環境
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 安裝依賴
pip install -r requirements.txt
```

## 最佳實踐

### 開發建議
1. **小步驟提交**: 每個功能或修復單獨提交
2. **有意義的提交訊息**: 清楚描述修改內容和原因
3. **本地測試**: 推送前確保代碼正常運行
4. **文檔同步**: 修改功能時同步更新相關文檔

### 安全注意
1. **敏感資料**: 確保 `.env` 不會被提交
2. **權限控制**: 使用最小權限原則
3. **定期備份**: 重要修改前先備份

### 效能考量
1. **避免阻塞**: 非同步操作避免阻塞主線程
2. **資源管理**: 適當釋放資源，避免記憶體洩漏
3. **錯誤處理**: 完善的異常處理機制

## 相關文檔

- [開發工具和流程](development-tools-and-workflow.md)
- [部署和維運指南](deployment-and-operations.md)
- [VM 實際配置](../entities/vm-actual-configuration.md)
- [專案架構總覽](project-architecture.md)
- [Discord Bot 系統詳解](discord-bot-system.md)
- [KK 園區系統地圖](kk-park-system-map.md)
