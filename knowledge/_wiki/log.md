# Knowledge Log

## 2026-05-10

## 2026-05-15

## 2026-05-21

- 透過 `gcloud compute ssh` 實機檢查 VM 上的 auto-debug 架構現況，確認所有 4 個 systemd 服務正常運行。
- 發現 auto-debug 架構已從舊版（單一 log_monitor 事件驅動）演進為 **三層防禦**：
  1. VM 本地（`auto_debug_system.py` + `mutual_rescue.py`）：優先本地 AI 分析 + 本地重啟
  2. GitHub Actions Agent 營運自癒（`auto_ai_fix.py` `execute_operational_heal()`）：gcloud SSH 遠端重啟
  3. GitHub Actions AI 自動改碼（`auto_ai_fix.py` `analyze_and_fix()`）：NVIDIA AI 分析 + 產生修復提案
- 重點變化：
  - 新增 `cogs/common/auto_debug_system.py` 作為 VM 端獨立 auto debug 循環（每 60 秒）
  - GitHub Actions 現在是升級路徑（`AUTO_DEBUG_GITHUB_MODE=escalate`），不是主路徑
  - `auto_ai_fix.py` 新增 `execute_operational_heal()` 營運自癒功能
  - AI 改碼預設只產生 review artifact，不直接覆寫原始碼（`AUTO_AI_DIRECT_WRITE` 預設 false）
- VM 檢查結果：Git 版本 `9643c4e2`，4 個服務全部 active，近 2 小時 journal 無錯誤
- 已全面更新 [LogMonitor 與 Auto AI Fix 流程總覽](concepts/log_monitor_pipeline.md) 知識頁，反映最新三層架構

## 2026-05-26

- 實機重新檢查 VM 後，確認先前知識庫對 auto-debug 現況有誤：VM 上**沒有** `auto-debug.service`，`auto_error_detector.py` 與 `auto_ai_fix.py` 雖然存在，但當時都未被 systemd 或 crontab 啟動。
- 今日先修掉一個會持續刷錯的產品 bug：`shopbot` 更新 dashboard 日誌時，`status_dashboard.py` 的 embed description 超過 Discord 4096 字上限，導致 `400 Bad Request (50035)`；現已在送出前截斷。
- 將 `scripts/auto_error_detector.py` 簡化為「**先讀 systemd journal，再回退檔案日誌**」的模式，直接檢查 `bot.service`、`shopbot.service`、`uibot.service`，避免與 VM 實際觀測來源脫節。
- 新的常駐自我 debug 入口改回 `config/services/auto-debug.service`，但內容已更新為執行 `scripts/auto_error_detector.py`，並沿用 bot 服務相同的 venv / locale / timezone 環境。
- 此次修正後，知識庫已改為記錄「**auto-debug 需以 systemd 服務部署，不能只靠腳本存在**」的現況，舊版 `auto_debug_system.py` 常駐說法不再視為已驗證狀態。
- 進一步把自我 debug 主幹收斂成單一路徑：`auto_error_detector.py` 抓到錯誤後直接 dispatch GitHub workflow；`auto_ai_fix.py` 改為直接做 AI 分析、寫修復、commit、push，不再把營運自癒當成主流程。

## 2026-05-18

- 將 LogMonitor / Auto AI Fix 延伸為 mutual-rescue self-healing agent：`bot`、`shopbot`、`uibot` 都會啟動 watchdog，偵測同伴 `systemd` 服務異常後自動派送 `repository_dispatch` 修復請求。
- 實測確認 `git push -> webhook -> VM git pull -> restart bots` 仍正常，VM 已自動同步到 commit `d4094c3d`。
- 實機驗證 mutual rescue：手動停止 `uibot.service` 後，`bot` 與 `shopbot` 都成功偵測到 `inactive`，並觸發 `Auto AI Fix repository_dispatch` run 與 `ai-heal-result-*` artifact。
- 已補上 `github-actions-vm-repair@kkgroup.iam.gserviceaccount.com` 對 `862486124810-compute@developer.gserviceaccount.com` 的 `roles/iam.serviceAccountUser`，之後重跑驗證成功，`uibot.service` 在被停止後約 61 秒由 agent 自動拉回 `active`。
- 已修正 bot 端 mutual rescue 在 systemd 環境下找不到 `systemctl` / `journalctl` 的問題，改用 `shutil.which()` 與 `/usr/bin/*` 回退路徑。

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

## 2026-09-30 (排程與孤兒腳本清理)

- **更正**：本頁 `2026-05-15` 段落記載「已在 VM crontab 設定每天台灣時間 18:00 執行 `scheduled_tasks/refresh_knowledge_base.py`」——2026-09-30 以 `crontab -l` 實測，**該排程從未存在**，`/etc/cron.d`、systemd timer、repo 內 Python 呼叫端亦皆查無引用
- **退役刪除**三個從未被任何排程或程式引用的孤兒腳本：
  - `scheduled_tasks/refresh_knowledge_base.py`（連同 `config/commands_registry.json` 的 `refresh_knowledge_base` 管理命令）
  - `scheduled_tasks/update_restart.py`
  - `scheduled_tasks/sync_to_sheet.py` 與其位元組相同的重複副本 `web/blueprints/sync_to_sheet.py`
- **刪除** `docs/ARCHITECTURE.md`：內容為已取消的 Agent 專案架構設計（`core/agent`、`core/tools`、`infra/*`、PostgreSQL/Redis 等），與實際架構不符且全 repo 零引用；實際架構以 [專案架構總覽](concepts/project-architecture.md) 為準
- **修正** `knowledge/_wiki/github-actions-ai-debugging.md` 的 AI 供應商清單：原文列出 `claude-3-5-sonnet` / `gpt-4-turbo` 等虛構項目，改為與 `cogs/common/AI.py` 實際降級鏈一致（NVIDIA 主要、Gemini 工具/備援、Groq 最終降級）
- **修正** `deployment-and-operations.md` 等多份文件的路徑：`/home/ubuntu` → `/home/e193752468/kkgroup`、`.venv` → `venv`
- ⚠️ **待確認**：文件記載的 `0 3 * * 1` 備份排程為 `venv/bin/python weekly_backup.py`（repo 根目錄），但該檔案實際位於 `scheduled_tasks/weekly_backup.py`——此排程可能一直靜默失敗

## 2026-10-02 (Google Sheets 系統退役)

- **確認**：Google Sheets 系統已無人使用，整套移除
- **刪除 5 個檔案**：
  - `cogs/common/google_sheets_sync.py`（全 repo 唯一 import `gspread` 的檔案）
  - `shared/db/sheet_sync_manager.py`
  - `web/blueprints/sheets.py`、`web/blueprints/sheet_sync_manager.py`、`web/blueprints/sheet_driven_db.py`
- **解除註冊**：`web/api/unified_api.py` 移除 `sheets_bp` 的 import 與 `register_blueprint`；註冊數 6 → 5。`/api/user/<user_id>` 由 `unified_api.py` 自身提供，admin 入口不受影響
- **移除 `weekly_backup.py` 的 Sheets 備份**：`backup_to_sheets()` 整段刪除（該函式已因服務帳號金鑰被 Google 自動停用而失效），只留本機備份
- **移除 `sync_from_sheet`**：`config/discord_commands_registry.json` 的指令定義、分類、maintenance 清單；同分類的 `export_to_sheet` / `list_members` / `sync_status` 也一併清掉（三個都查無實作）
- ⚠️ **保留**：`shared/db/sheet_driven_db.py` **不能刪**——檔名雖有 sheet，實際是純 SQLite 引擎（`import sqlite3`，無 `gspread`），由 `db_adapter.py`、`unified_api.py`、`cannabis_unified.py` 匯入
- **更正文件**：`project-architecture.md`、`ai-fast-read.md`、`web-api-and-game-system.md`、`kk-park-economy-system.md` 的 Sheets 描述；並在多處標註 `sheet_driven_db.py` 的檔名是舊稱

## 2026-10-02 (GitHub Actions 修復)

- **根因**：VM `instance-20250501-142333` 已於 2026-08-06 遷移到 `us-central1-a`，但三個 workflow 仍硬寫舊的 `us-central1-c`，導致每次 push 都紅燈
- **修復 `ci.yml` 的依賴鏈**（兩個 commit）：
  - `requirements-test.txt` 的 `discord-ext-test` 是**不存在的 PyPI 套件名**，正解是 `dpytest`（發行名 `dpytest`、import 路徑 `discord.ext.test`）
  - 補上測試會實際 import 的三個套件：`aiosqlite`（`shared/db/async_db.py`）、`watchdog`（`bots/uibot.py`）、`pytz`（`shared/utils/encoding_handler.py`）
  - 補套件的方式是先用本地 `.venv` 實跑整份測試（42 passed）反推依賴，不是一個一個撞 CI
- **修復 `auto-deploy-uibot.yml`**：`GCP_ZONE` 改 `us-central1-a`；並在 job `env:` 補上 `DISCORD_WEBHOOK_URL`——原本兩個通知步驟的 `if: ... && env.DISCORD_WEBHOOK_URL != ''` 引用了從未宣告的 `env` key（宣告 `secrets.X` **不會**讓 `env.X` 有值），所以通知永遠不觸發
- **修復 `auto-error-detector.yml`**：zone 改 `us-central1-a`；`python3 - <<'PY'` 的 heredoc 內容原本縮排 10 格，quoted heredoc 不做 dedent，直接 `IndentationError`——已把整段貼齊
- **修復 `ai-debug-monitor.yml`**：兩處 `gcloud compute ssh` 補上 `--zone=us-central1-a` 與 `--tunnel-through-iap`（原本缺 IAP flag）
- ⚠️ **已知未處理**：`ai-debug-monitor.yml` 把 SSH 例外吞掉（`except Exception` → print → `error_logs` 空 → `sys.exit(0)`），zone 修好前它一直「綠燈但什麼都沒做」。行為改動較大，待使用者決定是否收緊
- ✅ **驗證**：CI run `36918745826`（`863c728d`）`conclusion: success`，所有步驟 ✓
- ✅ **副作用確認**：`secrets.GCP_SA_KEY` 有效且在線（`Auto Deploy UIBot` 認證成功、一路打到 compute API 才因舊 zone 報錯），所以兩把 2026-04-02 的 enabled SA key 必須保留
