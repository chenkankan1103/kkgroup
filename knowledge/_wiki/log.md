# Knowledge Log

## 2026-05-10

## 2026-05-15

- 建立 [AI 記憶與 VM 知識更新流程](concepts/ai-memory-and-vm-knowledge-pipeline.md)，把 VM 掃描、wiki 匯入、長期記憶與 AI prompt 串成單一管線。
- 新增 `scripts/scan_vm_state.py`、`scripts/ingest_knowledge.py`、`scheduled_tasks/refresh_knowledge_base.py`，可在 VM 上每 24 小時更新一次知識庫。
- 擴充 `shared/db/ai_memory.py`，讓知識條目保存來源路徑、metadata、related topics，供 AI 回答時引用。
- 更新 `cogs/common/AI.py`，讓中控室 NPC 回答時會帶入長期人格、相關知識與最近 VM 掃描摘要。
- 在 `config/commands_registry.json` 補上 `refresh_knowledge_base` 管理命令，方便從既有維運入口手動重建知識。
- 已在 VM crontab 設定每天台灣時間 18:00 執行 `scheduled_tasks/refresh_knowledge_base.py`，並讓排程支援 Discord webhook 成功/失敗通知。
- 已將知識庫排程專用 webhook 寫入 VM `.env` 的 `KNOWLEDGE_WEBHOOK_URL`，供每日刷新結果回報使用。

- 新增 [KK 園區經濟系統](concepts/kk-park-economy-system.md) 整理頁，將 KK 幣、商店、UI 獎勵、活動成本與 DB 入口串成單一閱讀節點。
- 在索引頁、AI Fast Read、專案架構與 Discord Bot 系統頁加入回鏈，讓經濟系統不再只靠資料夾樹狀定位。
- 新增 [KK 園區系統地圖](concepts/kk-park-system-map.md) 作為跨主題導航頁，將經濟、紙娃娃、訊息持久化、部署維運、AI Debug、Web/API、開發維護串成可跳轉入口。
- 新增 [Knowledge Link Audit](concepts/knowledge-link-audit.md) 稽核頁，記錄孤島頁與弱連結頁，並補強 index 與相關文檔連結。
- 將原本弱連結的 [開發工作流程](concepts/development-workflow.md)、[Discord 訊息 ID 持久化實踐](concepts/discord-message-id-persistence.md)、[LogMonitor 與 Auto AI Fix 流程總覽](concepts/log_monitor_pipeline.md)、[GitHub Actions AI 除錯系統](github-actions-ai-debugging.md) 掛回主知識網。
- 統一知識頁收尾格式：一般頁面固定以 `## 相關文檔` 收尾，移除舊式 `---` 與版本型頁尾，並把 entities、sources、ai-debug-system 一起納入同一套導覽格式。

- 建立 KKGroup 專案知識庫骨架，供本機用 Obsidian 開啟，並透過 Git 同步到 VM。
- 初始主題包含 bot 服務、VM 操作、Webhook/隧道、紙娃娃流程。
- 補充指引與指令註冊表的整理頁，新增編碼規則、指令註冊表、知識維護流程與來源頁。

## 2026-05-11

- 新增 AI 專用低 token 專案速讀頁，讓後續代理優先從條列摘要理解結構與高頻工作流。
- 在兩份 Copilot 指引補上優先閱讀順序，避免每次先重掃整個專案。

## 2026-05-11 (知識庫擴充)

- 建立完整的專案知識庫系統，包含5個核心概念文檔：
  - [專案架構總覽](concepts/project-architecture.md): 完整的系統架構說明，涵蓋所有目錄和組件
  - [Discord Bot 系統詳解](concepts/discord-bot-system.md): Bot 服務、Cogs 系統、按鈕視圖、指令系統等詳細說明
  - [Web API 和遊戲系統](concepts/web-api-and-game-system.md): Flask API、前端系統、遊戲架構等完整文檔
  - [部署和維運指南](concepts/deployment-and-operations.md): GCP VM 部署、服務管理、自動化、監控等運維知識
  - [開發工具和流程](concepts/development-tools-and-workflow.md): 開發環境、測試、程式碼品質、自動化工具等
- 更新知識庫索引，新增文檔到核心入口列表
- 所有文檔包含程式碼範例、配置檔案、最佳實踐和相關文檔連結
- 建立系統性的知識架構，未來可快速提取需要的技術細節而不需要掃描整個專案

## 2026-05-11 (VM 實際配置檢查)

- 連上 GCP VM (`instance-20250501-142333`) 檢查實際系統設置
- 記錄 VM 規格：Debian 6.1.0-45-cloud-amd64，30GB 磁碟，969MB 記憶體
- 檢查服務狀態：4個主要服務運行中（bot、shopbot、uibot、unified_api）
- 記錄系統資源使用：磁碟 34%，記憶體 58%，Swap 31%
- 檢查網路配置：端口 80 監聽中，未安裝 UFW 防火牆
- 記錄 Cron 排程：每週日和週一的凌晨3點自動任務
- 記錄環境變數和 Discord Tokens 配置
- 記錄資料庫狀況：多個備份檔案，總計約 20MB
- 記錄日誌檔案：同步日誌 4.7MB，更新日誌 1.7MB
- 記錄 Cloudflare 整合：已安裝但未配置隧道
- 建立完整的 [VM 實際配置狀況](entities/vm-actual-configuration.md) 文檔
- 更新知識庫索引，新增 VM 配置文檔到核心入口列表