# Webhook and Tunnel

## 流程

GitHub push -> Cloudflare tunnel -> Nginx -> Flask webhook -> git pull -> restart bots

## 已知事實

- GitHub UI 顯示交付警告時，不一定代表實際流程失敗
- 真正判斷要看 Flask 日誌、bot 狀態、交付記錄
- Cloudflare 臨時隧道若重啟，URL 可能變動

## 檢查點

- `sudo journalctl -u kkgroup-api.service | grep webhook`
- `sudo systemctl status bot.service | grep Active`
- `sudo journalctl -u cloudflared.service -n 50 --no-pager`

## 相關文檔

- [部署和維運指南](deployment-and-operations.md)
- [VM Operations](../entities/vm-operations.md)
- [Command Registry](../entities/command-registry.md)
- [Operational Sources](../sources/operational-sources.md)