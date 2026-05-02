# KKGroup 開發任務清單 (Copilot 指令集)
**最後更新**: 2026-05-02 (因應機器人停機事件)

## 當前角色設定
- **軍師**: 提供核心想法與業務邏輯。
- **顧問 (Gemini)**: 負責架構設計、技術細節拆解與代碼審查。
- **寫手 (Copilot)**: 根據本文件與 `copilot-instructions.md` 的規範編寫代碼。

---

## 🗺️ 系統架構地圖
- **配置中心**: `config/config.json` (所有組件的網址來源)
- **部署流**: GitHub -> `web/blueprints/webhook.py` -> `systemctl` 重啟
- **監控流**: `scheduled_tasks/auto_update_webhook.py` -> GitHub API
- **展示層**: `status_dashboard.py` -> Discord Embed

---

##  緊急狀態：機器人下線 (Critical)
**診斷結果**: 隧道 URL 已過期 2 天，`auto_update_webhook.py` 的 `curl` 機制失效，導致 SSH 與 Webhook 全部斷連。
**詳細報告**: 參閱 `EMERGENCY_BOT_DOWNTIME_DIAGNOSIS.md`

---

## 🛡️ 階段 0：環境恢復與核對 (Priority: High)
**寫手 (Copilot) 請執行以下確認動作：**
1. **重啟隧道**: (軍師已手動重啟) 寫手需確認 `sudo journalctl -u cloudflared.service -n 5` 是否出現新的 `https://*.trycloudflare.com`。
2. **驗證連通性**: 執行 `curl -I [新隧道URL]/api/health` 確保 Flask 後端已回到線上。
3. **核對 .env**: 確保 `GITHUB_TOKEN` 有效且具備 `repo_hook` 權限。

---

## 🚀 階段 1：修復自動更新腳本 (Action Needed)

### 任務描述
徹底移除 `auto_update_webhook.py` 中脆弱的 `curl` 邏輯，改用強健的 Python `requests` 庫。

### 顧問執行細節 (Action Items for Copilot)
1. **重構 `scheduled_tasks/auto_update_webhook.py`**:
   - **完全移除 `curl`**: 確保程式碼中沒有殘留的 `subprocess.run(["curl", ...])` 區塊。
   - **標準化 API 呼叫**: 使用 `requests.get` 獲取 Webhook 列表，使用 `requests.patch` 更新。
   - 增加更詳細的 API 錯誤檢查（檢查 `response.status_code`）。
   - **路徑守則**: 嚴格使用 `/home/e193752468/kkgroup/` 作為絕對路徑基底。

2. **優化 `web/blueprints/webhook.py` 的安全性**:
   - 確保 `verify_github_signature` 函數使用的 `GITHUB_WEBHOOK_SECRET` 讀取自 `.env`。
   - 在 `git pull` 失敗時，應將錯誤訊息推送到 Discord 系統日誌頻道。

---

## 💡 Copilot 技術分析 & 補充建議

### 階段 0 核對項目補充
**已在 repo memory 記錄的已知事項：**
- ✅ 日誌亂碼問題已部署修復，但根本原因是 UTF-8 編碼轉換限制（影響顯示，不影響日誌功能）
- ✅ 三個 Bot 服務已配置編碼標準：`PYTHONIOENCODING=utf-8, LANG=C.UTF-8`
- ✅ systemd 輸出配置：`StandardOutput=journal`

**檢查清單補充：**
1. 確認 `config/config.json` 中的 `url` 字段是否為最新隧道 URL
2. 驗證 `scheduled_tasks/auto_update_webhook.py` 的執行日誌：`sudo tail -50 /var/log/webhook_auto_update.log`
3. 檢查 crontab 是否正確配置了 5 分鐘執行一次的監控

### 階段 1 重構的技術細節
**建議的改進順序：**
1. **第一步：改寫 auto_update_webhook.py**
   ```python
   # 必須移除的舊代碼模式：
   subprocess.run(["curl", "-X", "PATCH", ...])  # ❌ 過時
   
   # 改為：
   response = requests.patch(
       url=webhook_url,
       json={"config": {"url": new_tunnel_url}},
       headers={"Authorization": f"token {GITHUB_TOKEN}"},
       timeout=10
   )
   ```
   - 統一 timeout (建議 10 秒)
   - 詳細的錯誤日誌（記錄 status_code、response text）
   - 重試邏輯（失敗 3 次後警告）

2. **第二步：webhook.py 安全性加固**
   - HMAC 簽名驗證必須在 request 的最開始
   - git pull 失敗時的 Discord 推送應包含：`git pull` 的完整 stderr + 當前 commit hash
   - 建議記錄所有 webhook 觸發到 `config/webhook_audit.log`

3. **第三步：統一配置來源**
   - 所有服務應讀取 `config/config.json` 作為 source of truth
   - 新增 config 版本號 (e.g., `"version": "1.0.2"`)，方便追蹤配置變更

### 隧道 URL 監控最佳實踐
- 根據 repo memory，隧道建立需要 30-40 秒
- 監控間隔建議：60 秒（5 分鐘檢查一次過於頻繁）
- 自動更新成功後必須：`git commit -m "auto: tunnel url update"` + `git push`

### 可能的風險點
| 風險 | 原因 | 影響 | 建議 |
|------|------|------|------|
| 隧道 URL 過期未更新 | 監控未執行或失敗 | webhook 斷連，bot 無法自動重啟 | 增加告警機制到 Discord |
| .env 敏感資訊洩漏 | 誤推到 Git | 需要撤銷所有 token 並重設 | 驗證 .gitignore 包含 .env |
| 並發 git pull 衝突 | 多個 webhook 同時觸發 | 部署失敗，服務無法重啟 | 加入 file lock 機制 |

---
*Gemini 和軍師，歡迎補充架構設計層面的考量。Copilot 會根據確認的規範立即開始實作。*