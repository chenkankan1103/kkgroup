# 快速 GCP 重啟步驟

## 如果你已經在 GCP VM 上（SSH 已連接）

```bash
# 1. 確認在正確目錄
cd /home/e193752468/kkgroup

# 2. 檢查分支（應該是 restructure-project-20260414）
git branch

# 3. 重新複製所有服務文件
sudo cp config/services/*.service /etc/systemd/system/

# 4. 重新加載 systemd
sudo systemctl daemon-reload

# 5. 重啟所有四個服務
sudo systemctl restart bot.service
sudo systemctl restart shopbot.service
sudo systemctl restart uibot.service
sudo systemctl restart kkgroup-api.service

# 6. 檢查服務狀態（應該看到 "active (running)"）
sudo systemctl status bot.service | head -5
sudo systemctl status shopbot.service | head -5
sudo systemctl status uibot.service | head -5
sudo systemctl status kkgroup-api.service | head -5

# 7. 檢查日誌是否有錯誤
sudo journalctl -u bot.service -n 20 --no-pager
```

## 如果你在本地（未連接 GCP）

```bash
# 執行此命令進入 GCP VM
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 然後執行上面「在 GCP VM 上」的所有命令
```

## 驗證部署成功

✅ **檢查點：**
1. 所有四個服務顯示 `active (running)`
2. 日誌中沒有 `ImportError` 或 `ModuleNotFoundError`
3. Discord 中的 Bot 上線

## 常見問題

**如果看到"ModuleNotFoundError: No module named 'bots'"**
→ 確認已經在 `/home/e193752468/kkgroup` 目錄中
→ 檢查 `sys.path` 是否包含當前目錄

**如果 service 無法啟動**
→ 檢查 `/etc/systemd/system/` 中的 `.service` 文件是否有正確的路徑
→ `ExecStart` 應該指向 `/home/e193752468/kkgroup/bots/bot.py` 等

**如果看到"Permission denied"**
→ 使用 `sudo` 執行命令
→ 檢查文件所有者：`ls -l /etc/systemd/system/bot.service`
