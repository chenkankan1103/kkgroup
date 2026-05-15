# Bot Services

## 服務列表

- `bot.service`
- `shopbot.service`
- `uibot.service`

## 常用操作

- 重啟: `sudo systemctl restart bot.service shopbot.service uibot.service`
- 查看狀態: `systemctl status bot.service shopbot.service uibot.service`
- 查看最近日誌: `sudo journalctl -u bot.service -n 50 --no-pager`

## 專案內相關入口

- `scripts/commands_manager.py`
- `config/commands_registry.json`
- `.github/copilot-instructions.md`

## 備註

- 這三個 bot 是 VM 開機後需要自動啟動的核心服務。
- 若只更新單一 bot，也要確認其餘服務沒有被連帶影響。

## 相關文檔

- [Discord Bot 系統詳解](../concepts/discord-bot-system.md)
- [部署和維運指南](../concepts/deployment-and-operations.md)
- [VM Operations](vm-operations.md)
- [Command Registry](command-registry.md)