# Command Registry

## 角色

`scripts/commands_manager.py` 是專案的統一操作入口，負責把 SSH、systemd、日誌與診斷命令集中管理。

## 註冊來源

- 連線參數、服務操作、日誌類型、診斷命令、管理命令都在 `config/commands_registry.json`
- VS Code Tasks (`.vscode/tasks.json`) 也定義了常用 GCP SSH 指令

## 目前核心服務

- `bot.service` — 主 Discord Bot
- `shopbot.service` — 商店 Bot
- `uibot.service` — UI Bot
- `kkgroup-api.service` — Flask API (port 5000)
- `cloudflared.service` — Cloudflare Tunnel

## 高頻日誌檢查

| 指令 | 說明 |
|------|------|
| `logs bot recent_50` | bot 最近 50 筆 |
| `logs bot errors_50` | bot 錯誤 50 筆 |
| `logs bot errors_100` | bot 錯誤 100 筆 |
| `logs cloudflared recent_50` | cloudflared 最近 50 筆 |
| `logs cloudflared recent_100` | cloudflared 最近 100 筆 |
| `logs api recent_50` | API 最近 50 筆 |
| `logs api recent_100` | API 最近 100 筆 |

## 高頻診斷

| 指令 | 說明 |
|------|------|
| `diag tunnel_config` | 隧道配置檢查 |
| `diag tunnel_nginx` | 隧道 + Nginx 診斷 |
| `diag all_services` | 所有服務狀態 |
| `diag system_health` | 系統健康度 |

## 服務操作

| 指令 | 說明 |
|------|------|
| `run bot restart` | 重啟主 Bot |
| `run shopbot restart` | 重啟商店 Bot |
| `run uibot restart` | 重啟 UI Bot |
| `run api restart` | 重啟 Flask API |
| `run all restart` | 重啟所有服務 |

## 實務原則

- 優先用 commands manager，不要每次手打一長串 SSH 命令
- 新增常用維運指令時，先加進 registry，再補進這份 wiki
- 若指令已失效，先修 registry，再更新整理頁
- 本地開發用 `python scripts/commands_manager.py <service> <action>`
- GCP VM 上直接用 systemctl/journalctl

## 相關文檔

- [部署和維運指南](../concepts/deployment-and-operations.md)
- [Webhook and Tunnel](../concepts/webhook-and-tunnel.md)
- [VM Operations](vm-operations.md)
- [Operational Sources](../sources/operational-sources.md)
- [Bot Services](bot-services.md)