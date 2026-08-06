# VM 實際配置狀況

## 系統基本資訊

### 主機規格
- **主機名稱**: `instance-20250501-142333`
- **區域**: `us-central1-a`
- **作業系統**: Debian 6.1.0-45-cloud-amd64
- **架構**: x86_64
- **使用者**: `e193752468`

### 系統資源狀況
```bash
# 磁碟使用情況
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        30G  9.4G   19G  34% /

# 記憶體狀況
Mem:           969Mi       562Mi       259Mi       168Ki       287Mi       407Mi
Swap:          1.0Gi       312Mi       711Mi
```

## 專案部署結構

### 專案路徑
- **主專案**: `/home/e193752468/kkgroup/`
- **虛擬環境**: `/home/e193752468/kkgroup/venv/`
- **知識庫**: `/home/e193752468/kkgroup/knowledge/`
- **備份**: `/home/e193752468/kkgroup/backups/`

### 額外專案
- **Web Portal**: `/home/e193752468/kkgroup-web-portal/`
- **完整備份**: `/home/e193752468/full_backup.tar.gz` (335MB)

## 服務運行狀況

### 目前運行的服務
```bash
# 主要服務進程
e193752+  381  /home/e193752468/kkgroup/venv/bin/python3 /home/e193752468/kkgroup/web/api/unified_api.py
e193752+  156850  /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/bots/bot.py
e193752+  156855  /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/bots/shopbot.py
e193752+  156859  /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/bots/uibot.py
```

### 服務配置檔案
位置：`/home/e193752468/kkgroup/config/services/`
- `bot.service` - 主 Bot 服務
- `shopbot.service` - 商店 Bot 服務
- `uibot.service` - UI Bot 服務
- `kkgroup-api.service` - API 服務
- `kkgroup-api.service.fixed` - API 服務修復版

## 網路配置

### 端口監聽狀況
```bash
# 網路端口
tcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN
tcp6       0      0 :::80                   :::*                    LISTEN
```

### 防火牆狀況
- **UFW**: 未安裝 (命令不存在)
- **iptables**: 使用預設 GCP 防火牆規則

## 自動化任務

### 自動化任務配置
```bash
# 主要部署方式：GitHub Webhook 即時觸發
# 當代碼 push 到 main 分支時自動部署
# 流程：Git Push → GitHub Webhook → VM Webhook 接收器 → Git Pull → 重啟服務

# Cron 排程（僅用於維護任務）
# m h  dom mon dow   command
0 3 * * 0 cd /home/e193752468/kkgroup && /home/e193752468/kkgroup/venv/bin/python3 scheduled_tasks/refresh_all_lockers_cron.py >> /var/log/kkgroup_locker_refresh.log 2>&1
0 3 * * 1 cd /home/e193752468/kkgroup && venv/bin/python weekly_backup.py >> /tmp/weekly_backup.log 2>&1
CRON_TZ=Asia/Taipei
0 18 * * * cd /home/e193752468/kkgroup && /home/e193752468/kkgroup/venv/bin/python3 scheduled_tasks/refresh_knowledge_base.py >> /home/e193752468/kkgroup/knowledge_refresh.log 2>&1
```

**部署機制說明**:
- **即時部署**: GitHub Webhook 觸發，無需等待定時任務
- **Webhook 接收器**: `/web/blueprints/webhook.py`
- **執行操作**: `git pull` + `systemctl restart` 所有服務
- **通知機制**: 部署結果發送到 Discord 系統頻道
- **AI 知識庫排程**: 每天台灣時間 18:00 掃描 VM 與 repo，更新中控室 NPC 的知識庫
- **2026-05-18 再驗證**: push 到 `main` 後，VM 已自動同步到最新 commit（實測 commit `d4094c3d`），證明 webhook 自動部署鏈正常。
- **Mutual Rescue 前置權限**: GitHub Actions 已補上 `github-actions-vm-repair@kkgroup.iam.gserviceaccount.com` -> `862486124810-compute@developer.gserviceaccount.com` 的 `roles/iam.serviceAccountUser`。目前 agent 已可透過 `gcloud compute ssh` 遠端修復 bot 服務。

### 環境變數設定
```bash
LANG=C.UTF-8
LC_ALL=C.UTF-8
PYTHONIOENCODING=utf-8
TZ=Asia/Taipei
```

### AI 知識庫通知
- `scheduled_tasks/refresh_knowledge_base.py` 會嘗試從 `.env` 讀取以下 webhook 設定：
	- `KNOWLEDGE_WEBHOOK_URL`
	- `DISCORD_WEBHOOK_URL`
	- `DISCORD_WEBHOOK`
	- `STARTUP_WEBHOOK_URL`
- VM 目前已設定 `KNOWLEDGE_WEBHOOK_URL`，供每日知識庫刷新排程回報 Discord 狀態

## 環境配置

### Discord Bot Tokens
```env
# 主要環境變數 (.env)
TEMP_VC_CATEGORY_ID=1371429517750566962
GUILD_ID=1133112693356773416
DISCORD_BOT_TOKEN=YOUR_MAIN_BOT_TOKEN_HERE
UI_DISCORD_BOT_TOKEN=YOUR_UI_BOT_TOKEN_HERE
SHOP_DISCORD_BOT_TOKEN=YOUR_SHOP_BOT_TOKEN_HERE
DISCORD_SYS_CHANNEL_ID=1275688788806467635
STAFF_ID_CHANNEL_ID=1133461443812020314
LOG_FORUM_CHANNEL_ID=1504438347974705152
DASHBOARD_FORUM_CHANNEL_ID=1504438347974705152
```

### Python 環境
- **虛擬環境路徑**: `/home/e193752468/kkgroup/venv/`
- **Python 版本**: Python 3.x
- **主要套件**: discord.py, Flask, SQLite3

## 資料庫狀況

### 資料庫檔案
```bash
# 主要資料庫
user_data.db (6.6MB) - 用戶資料庫
user_data.db.backup_2026-04-12 (6.3MB) - 4月備份
user_data.db.backup_female_restyle_20260429_075757 (6.5MB) - 女性重設備份

# 其他資料庫
kkgroup.db (0 bytes) - 空資料庫
user_data.db.before_restore_20260331 (32KB) - 3月恢復前備份
```

## 日誌檔案

### 重要日誌
```bash
# 系統日誌
sync_cron.log (4.7MB) - 同步排程日誌
update.log (1.7MB) - 更新日誌
game_sync.log (652KB) - 遊戲同步日誌

# 錯誤日誌
paperdoll_button_click.log (1KB) - 紙娃娃按鈕點擊日誌
paperdoll_button_error.log (2KB) - 紙娃娃按鈕錯誤日誌
button_interaction_init.log (121 bytes) - 按鈕互動初始化日誌
```

## Cloudflare 整合

### Cloudflare 設定
- **安裝位置**: `/home/e193752468/cloudflared-linux-amd64.deb` (19MB)
- **配置目錄**: `/home/e193752468/.cloudflared/` (空目錄)
- **狀態**: 已安裝但未配置隧道

## 服務管理

### Bot 服務配置範例
```ini
[Unit]
Description=Discord Main Bot
After=network-online.target systemd-resolved.service
Wants=network-online.target

[Service]
Type=simple
User=e193752468
Group=e193752468
WorkingDirectory=/home/e193752468/kkgroup
Environment=PATH=/home/e193752468/kkgroup/venv/bin
Environment=PYTHONPATH=/home/e193752468
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=LC_ALL=C.UTF-8
Environment=LANG=C.UTF-8
Environment=LANGUAGE=zh_TW.UTF-8
Environment=TZ=Asia/Taipei
ExecStart=/home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/bots/bot.py
Restart=on-failure
RestartSec=30
StartLimitBurst=3
StartLimitInterval=60
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bot
SyslogFacility=daemon
SyslogLevel=info
TimeoutStopSec=30
KillMode=mixed

[Install]
WantedBy=multi-user.target
```

## 效能監控

### 資源使用情況
- **CPU 使用率**: 正常
- **記憶體使用**: 562MB/969MB (58%)
- **磁碟使用**: 9.4GB/30GB (34%)
- **Swap 使用**: 312MB/1GB (31%)

### 服務穩定性
- **Bot 服務**: 運行中，最近重啟時間 17:56
- **API 服務**: 運行中，PID 381
- **自動重啟**: 配置為失敗時重啟，30秒延遲

## 備份策略

### 自動備份
- **每週備份**: 週一凌晨3點執行 `weekly_backup.py`
- **每日任務**: 週日凌晨3點執行 `refresh_all_lockers_cron.py`
- **手動備份**: `full_backup.tar.gz` (335MB)

### 備份位置
- **臨時備份**: `/tmp/weekly_backup.log`
- **系統日誌**: `/var/log/kkgroup_locker_refresh.log`
- **專案備份**: `/home/e193752468/kkgroup/backups/`

## 安全配置

### 權限設定
- **檔案權限**: 使用者 e193752468 擁有專案目錄
- **服務權限**: 以非 root 使用者運行
- **SSH 配置**: 基於金鑰認證

### 環境保護
- **.env 檔案**: 包含敏感資訊，權限 644
- **Git 忽略**: .env 已加入 .gitignore
- **Token 安全**: Discord Tokens 已配置

## 故障排除

### 常見問題解決方案
1. **服務無法啟動**: 檢查虛擬環境路徑和 Python 路徑
2. **記憶體不足**: 監控 Swap 使用情況，考慮增加記憶體
3. **磁碟空間**: 定期清理日誌檔案和舊備份
4. **網路連線**: 檢查端口 80 監聽狀況

### 維護建議
- 定期檢查日誌檔案大小
- 監控系統資源使用率
- 定期測試備份恢復程序
- 更新系統套件和 Python 依賴

## 相關文檔

- [VM 操作指南](vm-operations.md)
- [部署和維運指南](../concepts/deployment-and-operations.md)
- [專案架構總覽](../concepts/project-architecture.md)
- [Discord Bot 系統詳解](../concepts/discord-bot-system.md)
