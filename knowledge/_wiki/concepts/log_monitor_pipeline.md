## LogMonitor 與 Auto AI Fix 流程總覽

版本說明：記錄 2026-05-21 的架構現況（三層自癒：本地優先 → GitHub Agent 營運自癒 → AI 自動改碼）。

### 架構總覽（2026-05-21 現況）

整個自我修復系統現在分為 **三層防禦**，由近到遠：

```
第 1 層：VM 本地（auto_debug_system.py + mutual_rescue.py）
  ├─ auto_debug_system.py: 每 60 秒檢查 systemd 服務狀態
  │   └─ 優先本地 AI 分析（NVIDIA），再決定是否升級 GitHub
  └─ mutual_rescue.py: 每個 Bot 啟動 watchdog，互相監控同伴
      ├─ 本地重啟（local-heal）→ 成功就結束
      └─ 失敗 → dispatch GitHub（escalate）

第 2 層：GitHub Actions Agent 營運自癒（auto_ai_fix.py）
  └─ execute_operational_heal(): 透過 gcloud compute ssh 遠端重啟服務
      ├─ 判斷是否為可安全重啟的營運異常（非程式碼缺陷）
      └─ 成功 → 寫 ai-heal-result.json artifact → Discord 通知

第 3 層：GitHub Actions AI 自動改碼（auto_ai_fix.py）
  └─ analyze_and_fix() + create_fix_file():
      ├─ NVIDIA deepseek-v4-pro 分析 → 生成修復代碼
      ├─ 預設只產生 review artifact（不直接覆寫原始碼）
      └─ 若 AUTO_AI_DIRECT_WRITE=true 才直接寫入目標檔案
```

### 核心代碼入口

| 檔案 | 角色 | 位置 |
|------|------|------|
| `cogs/common/auto_debug_system.py` | VM 端自動偵測 + 本地 AI 分析 | VM |
| `shared/utils/mutual_rescue.py` | Bot 互救 watchdog | VM |
| `cogs/common/log_monitor.py` | journalctl 事件驅動 + Discord 面板 | VM |
| `scripts/auto_ai_fix.py` | GitHub Actions: 營運自癒 + AI 改碼 | GitHub |
| `.github/workflows/auto-ai-fix.yml` | 接收 `system_debug` / `error_analysis` dispatch | GitHub |
| `.github/workflows/ai-debug-monitor.yml` | 獨立 AI 分析 workflow | GitHub |

### 第 1 層：VM 本地自癒詳解

#### auto_debug_system.py（`cogs/common/auto_debug_system.py`）
- **觸發**: Bot 啟動時掛載，每 60 秒循環檢查
- **檢查對象**: `bot.service`, `shopbot.service`, `uibot.service`
- **流程**:
  1. `_collect_detection_result()` → 調用 `mutual_rescue._read_service_snapshot()` 檢查每個服務
  2. 若 `action == "local-heal"` → 嘗試 `_attempt_local_service_heal()` 本地重啟
  3. 若本地自癒成功 → Discord 通知「已完成本地自癒」
  4. 若失敗 → `analyze_locally()` 用 NVIDIA AI 本地分析
  5. `should_escalate_to_github()` 判斷是否升級（預設模式 `escalate`: 只有 severity=high 才升級）
  6. 升級時發 `repository_dispatch` (event_type=`system_debug`)
- **環境變數**:
  - `AUTO_DEBUG_GITHUB_MODE`: `off` / `escalate`（預設）/ `always`
  - `AUTO_DEBUG_ESCALATE_SEVERITY`: `high`（預設）
  - `AUTO_DEBUG_RUN_ONCE`: 設為 `1` 可單次執行（用於 cron probe）
- **本地 artifact**: 分析結果寫入 `archive/auto_debug_reports/`

#### mutual_rescue.py（`shared/utils/mutual_rescue.py`）
- **觸發**: 每個 Bot（bot/shopbot/uibot）啟動時透過 `ensure_mutual_rescue_monitor()` 掛載
- **檢查間隔**: `MUTUAL_RESCUE_INTERVAL_SEC`（預設 60 秒）
- **冷卻時間**: `MUTUAL_RESCUE_COOLDOWN_SEC`（預設 300 秒，避免重複派單）
- **決策邏輯** (`_decide_repair_action`):
  - `healthy`: 服務 active 且日誌無異常
  - `local-heal`: 服務異常但非程式碼缺陷 → 嘗試 `systemctl restart`
  - `escalate`: 偵測到程式碼缺陷訊號（Traceback/AttributeError 等）→ dispatch GitHub
- **dispatch**: 發送 `error_analysis` event_type，附帶 `requested_action: restart_service`

### 第 2 層：GitHub Actions Agent 營運自癒

#### execute_operational_heal()（`scripts/auto_ai_fix.py`）
- **觸發條件** (`should_attempt_operational_heal`):
  - severity 必須為 `high`
  - 必須能識別目標服務（從 `service_hint` 或日誌內容推斷）
  - 必須有可安全重啟的訊號（connection reset、timeout、websocket closed 等）
  - 若為純程式碼缺陷（SyntaxError/ImportError 等）且無營運訊號 → 跳過，走第 3 層
- **執行**: 透過 `gcloud compute ssh` → `sudo systemctl restart <service>`
- **驗證**: 重啟後檢查 `systemctl is-active` + 擷取 `journalctl -n 30`
- **結果**: 寫入 `ai-heal-result.json` → 上傳為 GitHub Actions artifact
- **Dry run**: 設 `AUTO_HEAL_DRY_RUN=true` 可模擬而不實際執行

### 第 3 層：AI 自動改碼

#### analyze_and_fix() + create_fix_file()（`scripts/auto_ai_fix.py`）
- **觸發條件** (`should_attempt_code_fix`):
  - severity 為 `high`
  - 日誌含有程式碼錯誤訊號（Traceback/AttributeError/TypeError 等）
  - 非外部/基礎設施異常（503、nginx、cloudflared 等）
- **AI 引擎**: NVIDIA deepseek-v4-pro（首選），Gemini（僅 high severity 備援）
- **輸出**: 預設只產生 review artifact（`archive/ai_fixes/`），不直接覆寫原始碼
- **直接寫入**: 需設 `AUTO_AI_DIRECT_WRITE=true` + 目標檔案必須已存在於 repo
- **保護機制**:
  - 禁止 `manual_test*` 來源觸發提交
  - 拒絕絕對路徑與 `../` 不安全路徑
  - 目標檔案不存在時拒絕直接寫入
  - 若 staged changes 無實際差異則跳過 commit

### 2026-05-21 VM 實機檢查結果

| 檢查項目 | 狀態 |
|----------|------|
| bot.service | ✅ active (running)，PID 329390，記憶體 198.8M |
| shopbot.service | ✅ active (running)，PID 329394，記憶體 59.9M |
| uibot.service | ✅ active (running)，PID 329398，記憶體 88.4M |
| kkgroup-api.service | ✅ active (running)，PID 382，記憶體 5.2M（已運行 1 週 3 天） |
| Git 版本 | `9643c4e2` - fix: align local-first auto debug flow |
| GITHUB_TOKEN | ✅ 已設定於 `.env` |
| crontab 知識庫刷新 | 每天 UTC 10:00（台灣 18:00） |
| journal 錯誤 | 近 2 小時無明顯錯誤 |

### 與舊版知識庫的主要差異

1. **新增 `auto_debug_system.py`**：VM 端現在有獨立的 auto debug 循環，不再只依賴 log_monitor.py 的事件驅動。這是「本地優先」策略的核心。
2. **GitHub Actions 現在是升級路徑，不是主路徑**：`auto_debug_system.py` 的 `github_mode` 預設為 `escalate`，只有 severity=high 才升級到 GitHub。
3. **三層防禦明確分離**：本地自癒 → Agent 營運自癒 → AI 改碼，每層有獨立的 gate 判斷。
4. **auto_ai_fix.py 新增營運自癒**：`execute_operational_heal()` 可透過 gcloud SSH 遠端重啟服務，不需要 AI 分析代碼。
5. **AI 改碼預設不直接寫入**：`AUTO_AI_DIRECT_WRITE` 預設為 false，只產生 review artifact。
6. **crontab 知識庫刷新時間**：從 UTC 18:00 改為 UTC 10:00（台灣時間仍為 18:00，因為 crontab 有 `CRON_TZ=Asia/Taipei` 但實際寫的是 UTC 時間）。

### 維運／排查指引（快速命令）

- 檢查所有服務狀態（VM）：
```bash
systemctl status bot.service shopbot.service uibot.service kkgroup-api.service --no-pager
```
- 檢查 LogMonitor 狀態（VM）：
```bash
sudo journalctl -u bot.service -n 200 --no-pager | grep -iE 'error|traceback|fail'
```
- 檢查 auto_debug 本地 artifact：
```bash
ls -la /home/e193752468/kkgroup/archive/auto_debug_reports/
```
- SSH 到 VM：
```bash
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap
```
- 手動觸發 GitHub dispatch（測試用）：
```powershell
$body = @{ event_type='error_analysis'; client_payload=@{ severity='高'; log_text='Traceback ...' } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/chenkankan1103/kkgroup/dispatches' -Headers @{ Authorization='token xxxxx' } -Body $body -ContentType 'application/json'
```

### 回滾與注意事項
- 若發現 AI 自動提交需回滾：
  - `git revert <commit>` 或 `git reset --hard <sha>`
  - 檢查 GitHub Actions run logs 確認 `scripts/auto_ai_fix.py` 的輸出
- 若想完全關閉 GitHub 升級：在 VM `.env` 設 `AUTO_DEBUG_GITHUB_MODE=off`
- 若想測試營運自癒但不實際重啟：在 GitHub Actions 設 `AUTO_HEAL_DRY_RUN=true`

## 相關文檔

- [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)
- [部署和維運指南](deployment-and-operations.md)
- [開發工具和流程](development-tools-and-workflow.md)
- [KK 園區系統地圖](kk-park-system-map.md)
