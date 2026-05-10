# Knowledge Log

## 2026-05-10

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