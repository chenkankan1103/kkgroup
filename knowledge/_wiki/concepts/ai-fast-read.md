# AI Fast Read

## 專案一句話

KKGroup 是一個以 Discord 多 Bot 為核心、結合 Google Sheets/SQLite、Flask API、Webhook 自動部署與紙娃娃遊戲系統的混合專案。

## 先讀哪些地方

1. `knowledge/_wiki/concepts/ai-fast-read.md`
2. `knowledge/_wiki/entities/bot-services.md`
3. `knowledge/_wiki/entities/command-registry.md`
4. `knowledge/_wiki/concepts/webhook-and-tunnel.md`
5. 如果在查 KK 幣、商店、獎勵，先讀 `knowledge/_wiki/concepts/kk-park-economy-system.md`
6. 如果在查 AI 記憶、VM 掃描或 NPC 知識更新，讀 `knowledge/_wiki/concepts/ai-memory-and-vm-knowledge-pipeline.md`
6. 只有需要時才下鑽原始程式碼

## 專案分區

- `bots/`: 三個 Discord bot 入口
- `cogs/common/`: 共用功能與主 bot 常見功能
- `cogs/shop/`: 商店、紙娃娃、經濟相關
- `cogs/ui/`: UI 互動與 locker 類功能
- `shared/`: 共用 DB 與工具
- `web/`: Flask API、blueprints、portal
- `config/`: 設定、服務與腳本
- `scheduled_tasks/`: cron 任務
- `scripts/`: 本機操作與 GCP 輔助腳本

## 核心執行單位

- `bots/bot.py`: 主 bot
- `bots/shopbot.py`: 商店 bot
- `bots/uibot.py`: UI bot
- `web/api/unified_api.py`: Flask API 聚合入口

## 資料層模型

- 本地主要是 SQLite
- 結構上以 Google Sheets 驅動欄位與同步
- 穩定入口是 `shared/db/db_adapter.py`
- 核心引擎是 `shared/db/sheet_driven_db.py`
- 經濟系統要從 `cogs/common/kcoin.py`、`cogs/shop/`、`cogs/ui/` 一起看，不是只看商店

## 高頻維運入口

- SSH / 服務 / 日誌: `scripts/commands_manager.py`
- 指令定義: `config/commands_registry.json`
- 單次 SSH: `scripts/gcp-ssh.ps1`
- knowledge 同步: `scripts/sync-knowledge-to-vm.ps1`

## 最重要工作流

- 部署: git push -> webhook -> VM pull -> restart bots
- 排錯: 先看 journalctl，再看 cloudflared / nginx / webhook
- 紙娃娃: 診斷 -> 修復 -> 驗證 -> 部署 -> refresh lockers
- 新功能: 先找對應 bot/cog，再確認有沒有共用工具或 registry 要同步

## 必記規則

- `.env` 不上傳 Git
- systemd service 檔主要在 VM 管理
- 字型從 `cogs/common/` 指到根目錄要用 `../../fonts/`
- 紙娃娃造型不要硬編碼，走 `paperdoll_manager.get_random()`
- 永久視圖要 `timeout=None` 並註冊 `add_view()`

## 何時不要掃全 repo

- 只是找重啟命令
- 只是查 VM 日誌入口
- 只是確認 webhook/紙娃娃/字型規則
- 只是需要知道某功能大概在哪一層

這些情況先用 knowledge 頁，不要直接全域搜索整個 repo。

## 相關文檔

- [KK 園區系統地圖](kk-park-system-map.md)
- [專案架構總覽](project-architecture.md)
- [Discord Bot 系統詳解](discord-bot-system.md)
- [Command Registry](../entities/command-registry.md)