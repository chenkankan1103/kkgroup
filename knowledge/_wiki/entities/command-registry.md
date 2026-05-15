# Command Registry

## 角色

`scripts/commands_manager.py` 是專案的統一操作入口，負責把 SSH、systemd、日誌與診斷命令集中管理。

## 註冊來源

- 連線參數在 `config/commands_registry.json`
- 服務操作、日誌類型、診斷命令、管理命令也都在同一份 JSON

## 目前核心服務

- `bot.service`
- `shopbot.service`
- `uibot.service`
- `kkgroup-api.service`
- `cloudflared.service`

## 高頻日誌檢查

- bot 最近 50 筆
- bot 錯誤 50 或 100 筆
- cloudflared 最近 50 或 100 筆
- API 最近 50 或 100 筆

## 高頻診斷

- `tunnel_config`
- `tunnel_nginx`
- `all_services`
- `system_health`

## 實務原則

- 優先用 commands manager，不要每次手打一長串 SSH 命令
- 新增常用維運指令時，先加進 registry，再補進這份 wiki
- 若指令已失效，先修 registry，再更新整理頁

## 相關文檔

- [部署和維運指南](../concepts/deployment-and-operations.md)
- [Webhook and Tunnel](../concepts/webhook-and-tunnel.md)
- [VM Operations](vm-operations.md)
- [Operational Sources](../sources/operational-sources.md)