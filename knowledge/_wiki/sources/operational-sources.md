# Operational Sources

## 主要來源

### `.github/copilot-instructions.md`

用途:

- 部署
- webhook
- VM 維運
- 字型路徑
- 紙娃娃規則

### `.copilot-instructions.md`

用途:

- 編碼規則
- Discord.py 2.0 注意事項
- 路徑與 async 基本原則

### `config/commands_registry.json`

用途:

- GCP 連線參數
- 服務重啟與狀態查詢
- 日誌類型
- 診斷與批量管理命令

### `scripts/commands_manager.py`

用途:

- 實際讀取 registry 並執行 SSH 命令
- 作為本地到 VM 的標準操作入口

## 使用原則

- 原始文件保留細節
- wiki 負責整理出高頻、穩定、可維護的結論
- 若原始文件更新，對應的 wiki 頁也要同步檢查

## 相關文檔

- [部署和維運指南](../concepts/deployment-and-operations.md)
- [Webhook and Tunnel](../concepts/webhook-and-tunnel.md)
- [Command Registry](../entities/command-registry.md)
- [Knowledge Maintenance Workflow](../concepts/knowledge-maintenance-workflow.md)