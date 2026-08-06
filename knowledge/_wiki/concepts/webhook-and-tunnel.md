# Webhook and Tunnel

## 流程

```
GitHub push 
  → Cloudflare Tunnel (cloudflared) 
  → Nginx (reverse proxy, port 80/443 → 5000) 
  → Flask webhook (web/blueprints/webhook.py, port 5000) 
  → 驗證簽名 
  → git pull origin main 
  → 重啟三個 Bot 服務 (bot, shopbot, uibot) 
  → 發送 Discord 通知
```

## 關鍵組件

| 組件 | 位置 | 埠口 | 說明 |
|------|------|------|------|
| Cloudflare Tunnel | `cloudflared.service` | — | 臨時隧道，URL 可能變動 |
| Nginx | `/etc/nginx/sites-enabled/` | 80/443 | 反向代理到 Flask |
| Flask API | `kkgroup-api.service` | 5000 | `web/api/unified_api.py` 入口 |
| Webhook Blueprint | `web/blueprints/webhook.py` | — | 處理 GitHub push 事件 |

## 已知事實

- **GitHub UI 顯示 "We couldn't deliver this payload" 時，不一定代表實際流程失敗**
- 真正判斷要看：Flask 日誌、Bot 服務狀態、GitHub 交付記錄
- **原因**：隧道無法完整回傳 HTTP 200 給 GitHub，**不影響實際功能**
- Cloudflare 臨時隧道若重啟，URL 可能變動（需更新 GitHub Webhook 設定）

## 環境變數（Flask API 服務）

```ini
# kkgroup-api.service
Environment=PYTHONIOENCODING=utf-8
Environment=LANG=C.UTF-8
Environment=FLASK_ENV=production
```

## 依賴關係

```ini
# kkgroup-api.service
After=network-online.target systemd-resolved.service
Wants=network-online.target
```

## 檢查點

### 1. 驗證 Webhook 運作
```bash
# Flask 日誌
sudo journalctl -u kkgroup-api.service | grep webhook

# Bot 重啟狀態
sudo systemctl status bot.service | grep Active
sudo systemctl status shopbot.service | grep Active
sudo systemctl status uibot.service | grep Active

# GitHub 交付記錄
# GitHub > Settings > Webhooks > Deliveries
```

### 2. 隧道與 Nginx 診斷
```bash
# 隧道狀態
sudo systemctl status cloudflared --no-pager

# 隧道配置
sudo cat /etc/systemd/system/cloudflared.service | grep ExecStart
cat /root/.cloudflared/*.json 2>/dev/null | grep -o 'http.*' | head -5

# Nginx 存取日誌
sudo tail -50 /var/log/nginx/access.log
```

### 3. 完整診斷指令（commands_manager）
```bash
# 本地
python scripts/commands_manager.py diag tunnel_config
python scripts/commands_manager.py diag tunnel_nginx

# GCP VM (IAP SSH)
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-a --tunnel-through-iap --command "sudo journalctl -u kkgroup-api.service | grep webhook"
```

## Webhook 處理邏輯 (web/blueprints/webhook.py)

1. 接收 `POST /webhook` (GitHub push event)
2. 驗證 `X-Hub-Signature-256` 簽名（需 `WEBHOOK_SECRET` 環境變數）
3. 確認 `ref` 為 `refs/heads/main` 或 `refs/heads/master`
4. 執行 `git pull origin main`
5. 依序重啟：`bot.service` → `shopbot.service` → `uibot.service`（各等待 5 秒）
6. 發送 Discord 通知到指定頻道（需 `DISCORD_WEBHOOK_URL` 或 `STARTUP_WEBHOOK_URL`）

## 常見問題

| 現象 | 原因 | 解決 |
|------|------|------|
| GitHub UI 紅色警告 | 隧道無法回傳 200 | 忽略，功能正常 |
| Webhook 不觸發 | 隧道 URL 變更 | 更新 GitHub Webhook URL |
| 簽名驗證失敗 | `WEBHOOK_SECRET` 不匹配 | 檢查 `.env` 環境變數 |
| git pull 失敗 | 本地有未提交變更 | `git stash` 或強制重置 |
| Bot 未重啟 | systemd 權限/依賴問題 | 檢查 `journalctl -u bot.service` |

## 相關文檔

- [部署和維運指南](deployment-and-operations.md)
- [VM Operations](../entities/vm-operations.md)
- [Command Registry](../entities/command-registry.md)
- [Operational Sources](../sources/operational-sources.md)
- [Bot Services](../entities/bot-services.md)