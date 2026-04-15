# 🔄 VM Cron 排程更新指南

## 文件遷移
自動執行的腳本已集中於 `scheduled_tasks/` 資料夾（根目錄）

## ⚡ 快速更新

在 VM 上無需更新 crontab - 檔案已從根目錄移至 `scheduled_tasks/`
使用 git pull 自動同步後，應改為：
```bash
crontab -e
```

將舊路徑：
- `/home/e193752468/kkgroup/update_restart.py`
- `/home/e193752468/kkgroup/sync_to_sheet.py`
- `/home/e193752468/kkgroup/weekly_backup.py`

改為新路徑：
- `/home/e193752468/kkgroup/scheduled_tasks/update_restart.py`
- `/home/e193752468/kkgroup/scheduled_tasks/sync_to_sheet.py`
- `/home/e193752468/kkgroup/scheduled_tasks/weekly_backup.py`

## 📋 已配置的 Cron 任務
```
*/5 * * * * /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/scheduled_tasks/sync_to_sheet.py >> /home/e193752468/kkgroup/sync_cron.log 2>&1
*/5 * * * * /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/scheduled_tasks/update_restart.py >> /home/e193752468/kkgroup/update.log 2>&1
0 3 * * 1 cd /home/e193752468/kkgroup && venv/bin/python scheduled_tasks/weekly_backup.py >> /tmp/weekly_backup.log 2>&1
```

## 📚 腳本說明
- **update_restart.py**: 每 5 分鐘檢查 git 更新並重啟服務
- **sync_to_sheet.py**: 每 5 分鐘同步遊戲數據到 Google Sheets
- **weekly_backup.py**: 每週一 3:00 AM 執行資料庫備份
