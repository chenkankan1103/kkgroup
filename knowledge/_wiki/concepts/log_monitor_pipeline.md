## LogMonitor 與 Auto AI Fix 流程總覽

版本說明：記錄 2026-05-13 的重構與保護策略（單則面板、訊息復用、GitHub dispatch、Auto AI Fix 保護）。

### 概要
- LogMonitor：在 VM 上使用 `journalctl -u bot.service -u shopbot.service -u uibot.service -f` 事件驅動偵測錯誤日誌，debounce 後交給 LLM（NVIDIA 首選，Gemini 備援）分析。
- Discord：將結果顯示在單一持久化的 Embed（流程面板），不再無限新增訊息；面板會持續編輯（使用 `LOGMONITOR_MESSAGE_ID` 存於 `.env`）。
- GitHub：當判定為高危或包含 traceback/Exception 等程式錯誤時，會發送 `repository_dispatch`（`event_type=error_analysis`）到 GitHub，觸發 `AI Debug Monitor` 與 `Auto AI Fix` 工作流程。
- 閉環：`AI Debug Monitor` 會輸出帶 `incident_signature` 的分析 artifact，`LogMonitor` 會自動拉回結果並寫入 `data/logmonitor_known_debugs.json`，之後相同簽名錯誤可直接命中既有案例，不必每次重送 GitHub。
- Auto AI Fix：只對高危且明確為程式碼錯誤的事件執行自動修復產生並提交；加入多重保護避免誤提交。
- Mutual Rescue：`bot`、`shopbot`、`uibot` 啟動後都會掛上 `shared/utils/mutual_rescue.py` 的 watchdog，定期檢查另外兩個 `systemd` 服務；若同伴非 `active`，會送出 `repository_dispatch` 讓 `Auto AI Fix` agent 嘗試遠端重啟與驗證。

### 重要設計與保護（要點）
1. 單則流程面板（`cogs/common/log_monitor.py`）：
   - 固定編輯同一則 Embed（恢復訊息引用並儲存 `LOGMONITOR_MESSAGE_ID`）。
   - 將 GitHub dispatch 與 workflow 狀態整合在面板上（dispatch 狀態、debug run、auto-fix run、main commit）。
2. Auto AI Fix 保護（`scripts/auto_ai_fix.py`）：
   - `should_attempt_code_fix()`：只有 `severity` 為高且日誌含有程式錯誤指標（Traceback/AttributeError 等）才允許自動改碼。
   - 若 `severity` 缺失或格式不正確，會從日誌內容回推嚴重度（fallback）。
   - 禁止 `manual_test*` 類型的事件觸發提交（避免測試污染 main）。
   - 要求 `file_path` 必須已存在於 repo，禁止憑空建立新檔案與不安全路徑（abs 或 ../）。
3. Workflow：
   - `.github/workflows/ai-debug-monitor.yml`：負責分析並可發 `repository_dispatch`。
   - `.github/workflows/auto-ai-fix.yml`：現在接受 `error_analysis` 與 `system_debug`，但腳本內 gate 控制實際是否提交。

### 已修改檔案（參考）
- `cogs/common/log_monitor.py` — refactor: unify log monitor into single pipeline dashboard (commit 9950bc50)
- `scripts/auto_ai_fix.py` — infer severity fallback; disallow manual_test commits; require target file exists (commits 9bd3369e, 2360a2a4, 010bb177)
- `.github/workflows/auto-ai-fix.yml` — accept `error_analysis` repository_dispatch (commit 010bb177)

### 流程步驟（簡述）
1. LogMonitor 偵測到匹配的錯誤行 → 累積 debounce window → LLM 分析。
2. 組成 embed 並 upsert 到 Discord（使用已記錄的 message id）；面板內顯示簡述、AI 分析、dispatch 與 sync 狀態。
3. 若符合觸發條件（高危或有 traceback 等），發 `repository_dispatch` (event_type=error_analysis) 到 GitHub。
4. GitHub `Auto AI Fix` workflow 被觸發，但 `scripts/auto_ai_fix.py` 會先判定是否允許提交（高危 + 程式錯誤指標且非 manual_test，且目標檔案存在）。
5. `AI Debug Monitor` 會將分析結果輸出為 artifact；Bot 端背景輪詢後自動回寫本地 known debug。
6. 若下次出現同 `incident_signature` 的錯誤，面板會顯示「已命中已知案例」，沿用歷史分析，不再自動重送 GitHub。
7. 若允許，AI 生成修復代碼、產生修復檔並提交；否則只在面板註記為「已分析／跳過自動改碼」。

### 2026-05-18 實機驗證
- 已再次驗證部署鏈：`git push` 到 `main` 後，VM 會透過 webhook 自動 `git pull` 到最新 commit，無需手動 SSH 同步。
- 已用實機測試驗證 mutual rescue 的前半段：手動停止 `uibot.service` 後，`bot` 與 `shopbot` 都在 60 秒內偵測到 `uibot.service = inactive`，並成功送出 `repository_dispatch`。
- `Auto AI Fix` 的 `repository_dispatch` run 也已成功啟動並產出 `ai-heal-result-*` artifact，表示 agent 真的有接手修復，而不是只有分析。
- 當前阻塞點不在 bot 端，而在 GitHub Actions 的 GCP 權限：`github-actions-vm-repair@kkgroup.iam.gserviceaccount.com` 目前缺少對 `862486124810-compute@developer.gserviceaccount.com` 的 `roles/iam.serviceAccountUser`，導致 `gcloud compute ssh` 無法寫入 SSH metadata，遠端重啟因此失敗。
- 結論：目前 mutual rescue 已經做到「同伴偵測 -> 派單 -> agent 接手」，但尚未達成「agent 真正重啟 VM 上服務」；要完成最後一段，需先補足上述 IAM 權限。

### 維運／排查指引（快速命令）
- 檢查 LogMonitor 狀態（VM）：
```bash
sudo journalctl -u bot.service -n 200 --no-pager | grep -iE 'error|traceback|fail'
sudo systemctl status bot.service
``` 
- 觸發人工測試（Discord cog）：使用 `/logmonitor test` 指令（管理員限定）。
- 手動觸發 GitHub dispatch（測試用）：
```powershell
$body = @{ event_type='error_analysis'; client_payload=@{ severity='高'; log_text='Traceback ...' } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/OWNER/REPO/dispatches' -Headers @{ Authorization='token xxxxx' } -Body $body -ContentType 'application/json'
```

### 回滾與注意事項
- 若發現 AI 自動提交需回滾：
  - `git revert <commit>` 或 `git reset --hard <sha>`（視情況而定，注意協作影響）。
  - 檢查 `AUTO AI FIX` 的 Run logs 並確認 `scripts/auto_ai_fix.py` 的輸出內容。Logs 可從 GitHub Actions 下載。

### 為什麼記錄在知識庫
- 方便未來維運快速理解自動修復的 guard rails，避免重複引入測試污染。
- 提供回溯路徑（檔案與 commit）以利安全變更與審查。
- 記錄 mutual rescue 的實機驗證結果與前置權限，避免再次誤判為 bot 邏輯失效。

檔案位置：`knowledge/_wiki/concepts/log_monitor_pipeline.md`
如需我將此檔案同時存進 Agent 記憶（/memories/repo/）請告知，我會嘗試建立 repository-scoped memory 條目（若系統允許）。

## 相關文檔

- [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)
- [部署和維運指南](deployment-and-operations.md)
- [開發工具和流程](development-tools-and-workflow.md)
- [KK 園區系統地圖](kk-park-system-map.md)
