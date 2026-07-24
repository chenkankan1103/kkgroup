# Bot Services

## 服務列表

### 核心 Bot 服務（3 個）
- `bot.service` — 主 Bot（核心指令、用戶管理、基礎互動）
- `shopbot.service` — 商店 Bot（商店、經濟、大麻種植、商家系統）
- `uibot.service` — UI Bot（置物櫃、動漫追蹤、活動、UI 互動）

### 基礎設施服務（2 個）
- `kkgroup-api.service` — Flask API 服務（port 5000，Webhook 接收、Discord OAuth、知識庫 API）
- `cloudflared.service` — Cloudflare Tunnel（隧道服務，GitHub → VM 連線）

## 常用操作

```bash
# 重啟所有核心 Bot
sudo systemctl restart bot.service shopbot.service uibot.service

# 重啟含基礎設施
sudo systemctl restart bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service

# 查看狀態
systemctl status bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service

# 查看最近日誌
sudo journalctl -u bot.service -n 50 --no-pager
sudo journalctl -u kkgroup-api.service -n 50 --no-pager
sudo journalctl -u cloudflared.service -n 50 --no-pager

# 啟用開機自啟（必須執行）
sudo systemctl enable bot.service shopbot.service uibot.service kkgroup-api.service cloudflared.service
```

## 專案內相關入口

- `scripts/commands_manager.py` — 統一維運 CLI
- `config/commands_registry.json` — 指令註冊表
- `config/services/` — systemd service 檔（僅 VM 管理，**不上傳 Git**）
- `.github/copilot-instructions.md` — Copilot 指引

## 服務配置位置（VM 上）
```
/etc/systemd/system/bot.service
/etc/systemd/system/shopbot.service
/etc/systemd/system/uibot.service
/etc/systemd/system/kkgroup-api.service
/etc/systemd/system/cloudflared.service
```

## 建議重啟策略（service 檔建議加入）
```ini
Restart=on-failure
RestartSec=10
StartLimitBurst=10
StartLimitIntervalSec=600
```

## e2-micro 記憶體優化（必須）
```bash
# 加 1G swap 緩衝
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 備註

- 這 5 個服務是 VM 開機後需要自動啟動的核心服務。
- 若只更新單一 bot，也要確認其餘服務沒有被連帶影響。
- `kkgroup-api.service` 負責接收 GitHub Webhook 觸發自動部署。
- `cloudflared.service` 提供隧道，GitHub push 經由隧道 → Nginx → Flask。

## 相關文檔

- [Discord Bot 系統詳解](../concepts/discord-bot-system.md)
- [部署和維運指南](../concepts/deployment-and-operations.md)
- [VM Operations](vm-operations.md)
- [Command Registry](command-registry.md)
- [Webhook and Tunnel](../concepts/webhook-and-tunnel.md)