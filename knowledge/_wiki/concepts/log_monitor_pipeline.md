## LogMonitor 與 Auto AI Fix 流程總覽

版本說明：2026-05-26 再次收斂後的架構現況。自我 debug 主幹以「分析問題 -> debug -> push」為核心；不再把本地摘要分析與遠端營運自癒視為主流程。

### 架構總覽（2026-05-26 現況）

整個自我 debug 主流程目前收斂為 **單一路徑**：

```
第 1 步：VM 本地 auto_error_detector.py
  └─ 常駐掃描 bot.service / shopbot.service / uibot.service 的 journal

第 2 步：發送 repository_dispatch -> Auto AI Fix workflow
  └─ 只傳遞錯誤內容與 service hint，不再先做本地摘要分析 gate

第 3 步：GitHub Actions auto_ai_fix.py
  └─ AI 分析錯誤 -> 產生修復 -> 直接寫入目標檔案 -> commit -> push
```

### 核心代碼入口

| 檔案 | 角色 | 位置 |
|------|------|------|
| `scripts/auto_error_detector.py` | VM 端常駐錯誤檢測 + dispatch | VM |
| `config/services/auto-debug.service` | `auto_error_detector.py` 的 systemd 常駐入口 | VM |
| `scripts/auto_ai_fix.py` | GitHub Actions: AI 分析 / 修復 / push | GitHub |
| `.github/workflows/auto-ai-fix.yml` | 接收 `system_debug` dispatch，直接執行修復 | GitHub |
| `.github/workflows/ai-debug-monitor.yml` | 獨立 AI 分析 workflow | GitHub |

### 第 1 層：VM 本地自癒詳解

#### auto_error_detector.py（`scripts/auto_error_detector.py`）
- **觸發**: 由 `auto-debug.service` 常駐執行；預設循環每 2 分鐘檢查一次
- **檢查對象**: `bot.service`, `shopbot.service`, `uibot.service` 的 systemd journal
- **流程**:
  1. `_read_journal_lines()` 直接抓取三個 bot service 的最新 journal
  2. `_collect_errors_from_lines()` 比對 `Traceback`、`HTTPException`、`ImportError` 等模式
  3. 抓到錯誤就直接發 `repository_dispatch` (event_type=`system_debug`)
  4. Discord 僅回報「已送交 GitHub 分析 / debug / push」
- **環境變數**:
  - `AUTO_ERROR_DETECTOR_RUN_ONCE`: 設為 `1` 可單次執行
  - `AUTO_DEBUG_JOURNAL_LINES`: 控制每輪掃描的 journal 行數（預設 200）
  - `AUTO_DEBUG_MAX_LOG_AGE_SECONDS`: 忽略過舊 journal，避免把歷史錯誤重複 dispatch

### GitHub Actions：AI 自動改碼

#### analyze_and_fix() + create_fix_file()（`scripts/auto_ai_fix.py`）
- **觸發條件** (`should_attempt_code_fix`):
  - severity 為 `high`
  - 日誌含有程式碼錯誤訊號（Traceback/AttributeError/TypeError 等）
  - 非外部/基礎設施異常（503、nginx、cloudflared 等）
- **AI 引擎**: NVIDIA deepseek-v4-pro（首選），Gemini（僅 high severity 備援）
- **輸出**: 以直接寫入目標檔案並 commit / push 為主；同時保留修復提案 artifact
- **直接寫入**: workflow 已設 `AUTO_AI_DIRECT_WRITE=true`，目標檔案必須已存在於 repo
- **保護機制**:
  - 禁止 `manual_test*` 來源觸發提交
  - 拒絕絕對路徑與 `../` 不安全路徑
  - 目標檔案不存在時拒絕直接寫入
  - 若 staged changes 無實際差異則跳過 commit

### 2026-05-26 VM 實機檢查結果

| 檢查項目 | 狀態 |
|----------|------|
| auto-debug.service | 已部署至 VM，並確認由 systemd 執行 `scripts/auto_error_detector.py` |
| bot.service / shopbot.service / uibot.service | 仍為 systemd 主服務來源，auto debug 現在直接讀它們的 journal |
| 今日明確錯誤 | `status_dashboard.py` 更新 embed description 超過 4096 字，導致 Discord 400 失敗 |
| 今日結論 | 腳本存在不等於自動化存在；`auto_error_detector.py` 必須透過 systemd 常駐才算生效 |

### 與舊版知識庫的主要差異

1. **主流程收斂為單一路徑**：抓錯誤後直接 dispatch 到 GitHub，不再先做本地分析 gate。
2. **GitHub 端移除營運自癒主路徑**：收到事件後直接進 AI 分析 / 修復 / push。
3. **workflow 改為直接寫入**：`AUTO_AI_DIRECT_WRITE=true`，不再只停在 proposal artifact。
4. **systemd journal 仍是唯一可靠錯誤來源**：VM 偵測面保持簡單，只做掃描與派送。

### 維運／排查指引（快速命令）

- 檢查所有服務狀態（VM）：
```bash
systemctl status bot.service shopbot.service uibot.service kkgroup-api.service --no-pager
```
- 檢查 LogMonitor 狀態（VM）：
```bash
sudo journalctl -u bot.service -n 200 --no-pager | grep -iE 'error|traceback|fail'
```
- SSH 到 VM：
```bash
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-a --tunnel-through-iap
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
- 若想暫時停止自我 debug：停用 `auto-debug.service` 或移除 VM `.env` 的 `GITHUB_TOKEN`

## 相關文檔

- [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)
- [部署和維運指南](deployment-and-operations.md)
- [開發工具和流程](development-tools-and-workflow.md)
- [KK 園區系統地圖](kk-park-system-map.md)
