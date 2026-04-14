# 專案重組部署指南

## 概述
項目已成功重組並推送到 GitHub 分支 `restructure-project-20260414`。本指南說明如何在 GCP VM 上部署這些變更。

## 🔄 GCP VM 部署步驟

### 1. SSH 連接到 GCP VM
```bash
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap
```

### 2. 進入專案目錄
```bash
cd /home/e193752468/kkgroup
```

### 3. 更新到重組分支
```bash
# 確保在 main 分支，先拉取最新代碼
git fetch origin
git checkout restructure-project-20260414

# 或直接從 main 拉取（如果已在 main）
git pull origin main
git checkout restructure-project-20260414
```

### 4. 驗證目錄結構
```bash
# 檢查新目錄是否已建立
ls -la bots/
ls -la shared/db/
ls -la shared/utils/
ls -la web/api/
ls -la cogs/
ls -la config/services/
```

### 5. 更新 systemd 服務檔案路徑

原本位置：`/home/e193752468/kkgroup/*.service`
新位置：`/home/e193752468/kkgroup/config/services/*.service`

#### 5.1 複製新的服務檔案到 systemd 目錄
```bash
sudo cp config/services/bot.service /etc/systemd/system/bot.service
sudo cp config/services/shopbot.service /etc/systemd/system/shopbot.service
sudo cp config/services/uibot.service /etc/systemd/system/uibot.service
sudo cp config/services/kkgroup-api.service /etc/systemd/system/kkgroup-api.service
```

#### 5.2 重新載入 systemd 配置
```bash
sudo systemctl daemon-reload
```

### 6. 驗證服務檔案內容（重要！）

檢查 `ExecStart` 是否需要更新。目前服務檔案應該已正確配置：

```bash
# 檢查 bot.service
sudo cat /etc/systemd/system/bot.service | grep ExecStart

# 應該顯示：
# ExecStart=/home/e193752468/kkgroup/venv/bin/python bots/bot.py
```

如果 `ExecStart` 仍然指向根目錄檔案（如 `python bot.py`），需要手動編輯：
```bash
sudo nano /etc/systemd/system/bot.service
# 找到 ExecStart 行並將其改為：
# ExecStart=/home/e193752468/kkgroup/venv/bin/python bots/bot.py
```

### 7. 重啟服務

```bash
# 逐個重啟確保沒有錯誤
sudo systemctl restart bot.service
sleep 2
sudo systemctl status bot.service

sudo systemctl restart shopbot.service
sleep 2
sudo systemctl status shopbot.service

sudo systemctl restart uibot.service
sleep 2
sudo systemctl status uibot.service

sudo systemctl restart kkgroup-api.service
sleep 2
sudo systemctl status kkgroup-api.service
```

### 8. 檢查日誌確認沒有錯誤

```bash
# 檢查 bot 日誌
sudo journalctl -u bot.service -n 50 --no-pager

# 檢查 shopbot 日誌
sudo journalctl -u shopbot.service -n 50 --no-pager

# 檢查 uibot 日誌
sudo journalctl -u uibot.service -n 50 --no-pager
```

### 9. 驗證 bot 狀態

執行你已設定的 GCP 任務來檢查 bot 狀態（如果有的話）。

## ⚠️ 常見問題排查

### 問題 1：ImportError: No module named 'shared'
**原因**：Python 路徑未正確設定
**解決**：確認 `ExecStart` 在正確的工作目錄 `/home/e193752468/kkgroup`

### 問題 2：ImportError: No module named 'cogs'
**原因**：Cog 載入路徑需要更新
**解決**：檢查 `bots/*.py` 中的 Cog 載入邏輯，確保路徑為 `cogs/common`, `cogs/shop`, `cogs/ui`

### 問題 3：database is locked
**原因**：多個進程同時存取 SQLite
**解決**：確保只有一個 bot 實例運行，或實施寫入隊列（已在計畫中）

## 📊 目錄結構對照

### 舊結構
```
/home/e193752468/kkgroup/
├── bot.py
├── shopbot.py
├── uibot.py
├── api_server.py
├── db_adapter.py
├── logger.py
├── bot_status.py
├── commands/
├── shop_commands/
├── uicommands/
├── blueprints/
└── ...
```

### 新結構
```
/home/e193752468/kkgroup/
├── bots/
│   ├── bot.py
│   ├── shopbot.py
│   └── uibot.py
├── shared/
│   ├── db/
│   │   ├── db_adapter.py
│   │   └── ...
│   └── utils/
│       ├── logger.py
│       ├── bot_status.py
│       └── ...
├── web/
│   └── api/
│       ├── api_server.py
│       ├── unified_api.py
│       └── game_api.py
├── cogs/
│   ├── common/    (commands/)
│   ├── shop/      (shop_commands/)
│   └── ui/        (uicommands/)
├── config/
│   ├── services/  (.service 檔案)
│   ├── nginx/
│   └── scripts/
├── docs/
├── archive/
├── db_adapter.py  (相容層)
└── ...
```

## 🔄 後續操作

### 合併到 main（如果驗證成功）
```bash
git checkout main
git pull origin main
git merge restructure-project-20260414
git push origin main
```

### 清理舊分支（可選）
```bash
git branch -d restructure-project-20260414
git push origin --delete restructure-project-20260414
```

## ✅ 驗證清單

- [ ] Git 分支已檢出
- [ ] 目錄結構確認無誤
- [ ] systemd 服務檔已複製
- [ ] systemd 已 reload
- [ ] 3 個 bot 服務都已重啟
- [ ] 日誌無重大錯誤
- [ ] Bot 在 Discord 上線

## 📞 聯繫

如有問題，請檢查：
1. `/tmp/bot-debug.log` 和 `/tmp/shopbot-debug.log` 的輸出
2. `sudo journalctl -u bot.service -f` 的實時日誌
3. 確認 `.env` 檔案在根目錄存在

---

**部署日期**：2026年4月14日
**分支名稱**：`restructure-project-20260414`
**狀態**：✅ 準備部署
