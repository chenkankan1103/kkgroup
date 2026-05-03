# KKGroup 開發任務清單 - 三層協作模式
**最後更新**: 2026-05-03 (角色區分已明確化)

---

# ████████████████████████████████████████████████████████████
# 👑 軍師區域 (戰略方向 & 核心想法)
# ████████████████████████████████████████████████████████████

## 核心策略
1. **自動化部署優先**: Webhook 驅動，減少手動操作
2. **零停機時間**: 監控系統健康狀態，及時告警
3. **代碼質量第一**: 移除脆弱的 Shell 腳本，改用 Python
4. **配置集中化**: `config/config.json` 作為全局真實來源

## 當前狀態快照
- ✅ 定期檢查系統（update_restart.py）已停用，改為 Webhook only
- ✅ 數據同步（sync_to_sheet.py）已停用，改為手動觸發
- ✅ 三個 Bot 服務（bot, shopbot, uibot）正常運行
- ⚠️ 自動 Webhook 監控機制脆弱（使用 curl），需重構

## 軍師發號施令
1. **優先級最高**: 修復自動更新機制（`auto_update_webhook.py`）
2. **優先級次高**: 項目文件結構整理（移除冗餘代碼）
3. **優先級低**: 代碼審查優化

---

# 🧠 Gemini 區域 (架構設計 & 技術分析)
# ════════════════════════════════════════════════════════════

## 🗺️ 系統架構地圖
```
GitHub Push Event
    ↓
Webhook (web/blueprints/webhook.py)
    ├─ 驗證簽名 (GITHUB_WEBHOOK_SECRET from .env)
    ├─ git pull origin/main
    ├─ systemctl restart bot.service ...
    └─ Discord 通知 (+ 失敗告警)
    
配置中心 (config/config.json)
    ├─ url: 隧道 URL (由 auto_update_webhook.py 管理)
    ├─ API_BASE: Flask API 基地址
    └─ imageURL: CDN 資源鏈接
```

## 問題診斷
**現象**: Webhook 可能斷連的根本原因
- `auto_update_webhook.py` 使用 `curl` 不穩定（依賴系統命令）
- 隧道 URL 過期時無法即時更新 GitHub webhook
- 錯誤日誌不詳細，難以追蹤問題

## 架構改進方案
1. **移除 curl，使用 Python requests**
   - 統一錯誤處理
   - 添加重試邏輯
   - 詳細日誌記錄

2. **強化 Webhook 安全性**
   - HMAC 簽名驗證必須優先
   - git pull 失敗時主動推送告警到 Discord
   - 增加請求審計日誌

3. **配置版本號管理**
   - `config.json` 添加 version 字段
   - 追蹤配置變更歷史

## 風險評估與建議
| 風險 | 影響程度 | 緩解策略 |
|------|--------|--------|
| 隧道 URL 過期 | 🔴 Critical | 實時監控 + Discord 告警 |
| .env 洩漏 | 🔴 Critical | 嚴格的 .gitignore 驗證 |
| 並發 git pull | 🟡 High | 添加文件鎖機制 |
| curl 不穩定 | 🟡 High | 改用 Python requests ✅ |

---

# 🔧 GPT 區域 (補齊細節 & 發號施令)
# ════════════════════════════════════════════════════════════

## 🛡️ 階段 0：環境恢復與確認 (Priority: High)

### GPT 對 Copilot 的指令
1. **驗證隧道狀態**:
   ```bash
   sudo journalctl -u cloudflared.service -n 5
   ```
   預期看到：`https://*.trycloudflare.com/` 新的隧道 URL

2. **驗證後端連通性**:
   ```bash
   curl -I https://[隧道URL]/webhook/health
   ```
   預期狀態碼：200 + JSON 響應

3. **核對 .env 配置**:
   - GITHUB_TOKEN 是否有效
   - GITHUB_WEBHOOK_SECRET 是否已設置
   - DISCORD_BOT_TOKEN 是否有效

---

## 🚀 階段 1：修復自動更新腳本 (Action Needed)

### GPT 發號施令給 Copilot
**目標**: 徹底移除脆弱的 `curl` 邏輯，改用 Python `requests` 庫

**具體步驟**:

#### 1️⃣ 重構 `scheduled_tasks/auto_update_webhook.py`

**需要完成的事項**:
- [ ] 移除所有 `subprocess.run(["curl", ...])` 調用
- [ ] 改為 `requests.get()` 獲取 webhook 列表
- [ ] 改為 `requests.patch()` 更新 webhook URL
- [ ] 添加詳細的 HTTP 狀態碼檢查
- [ ] 添加 3 次重試機制（失敗時）
- [ ] 所有路徑使用絕對路徑 `/home/e193752468/kkgroup/`
- [ ] 詳細日誌記錄每一步操作

**新代碼範例**:
```python
import requests
from dotenv import load_dotenv
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
WEBHOOK_URL = "https://api.github.com/repos/chenkankan1103/kkgroup/hooks"

def get_webhooks():
    """獲取 GitHub webhook 列表"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(WEBHOOK_URL, headers=headers, timeout=10)
    if response.status_code != 200:
        logger.error(f"❌ 獲取 webhook 列表失敗: {response.status_code} - {response.text}")
        return None
    return response.json()

def update_webhook(webhook_id, new_url):
    """更新 webhook URL"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    payload = {"config": {"url": new_url}}
    response = requests.patch(
        f"{WEBHOOK_URL}/{webhook_id}",
        json=payload,
        headers=headers,
        timeout=10
    )
    if response.status_code != 200:
        logger.error(f"❌ 更新 webhook 失敗: {response.status_code} - {response.text}")
        return False
    logger.info(f"✅ Webhook 已更新: {new_url}")
    return True
```

#### 2️⃣ 優化 `web/blueprints/webhook.py` 安全性

**需要完成的事項**:
- [ ] HMAC 簽名驗證在請求最開始
- [ ] git pull 失敗時推送完整錯誤到 Discord 系統頻道
- [ ] 記錄所有 webhook 觸發到 `config/webhook_audit.log`
- [ ] 添加請求速率限制（防止 DDoS）

#### 3️⃣ 配置統一化

**需要完成的事項**:
- [ ] `config/config.json` 添加 `version` 字段（格式: "1.0.0"）
- [ ] 添加 `last_updated_at` 時間戳
- [ ] 新增 `git_branch` 字段（當前監控分支）

---

## 💾 階段 2：項目文件結構整理 (Priority: Medium)

### 2.1 高優先級：清理冗餘文件

**GPT 指令**: Copilot 檢查並移除以下文件:

```
1. archive/ 中的一次性修復腳本
   ├── fix_*.py (所有 fix_XXX.py)
   ├── do_fix.py
   ├── final_*.py (所有 final_XXX.py)
   └── Action: 移除 (已完成的修復不需保留)

2. 根目錄重複文件檢查
   ├── db_adapter.py (根) 與 shared/db/db_adapter.py
   ├── Action: 確認版本，保留 shared/ 中的版本

3. 配置文件備份
   ├── config/services/kkgroup-api.service.fixed
   ├── config/services/kkgroup-api.service
   └── Action: 合併，移除 .fixed
```

**檢查清單**:
- [ ] 列出所有 `fix_*.py` 文件
- [ ] 確認 `db_adapter.py` 版本差異
- [ ] 移除備份文件（.fixed, .bak 等）

### 2.2 中優先級：統一目錄結構

**GPT 指令**: 執行以下移動操作

1. **根目錄腳本 → `scripts/`**
   ```
   start_game_api.bat → scripts/
   start_game_api_enhanced.bat → scripts/
   deploy_restructure.sh → scripts/
   generate_webhook_signature.py → scripts/
   ```

2. **JSON 配置 → `config/`**
   ```
   api_index.json → config/
   api_endpoints_index.json → config/
   commands_inventory.json → config/
   locker_refresh_urls.json → config/
   market_message_data.json → config/
   ```

3. **根目錄數據庫 → `data/`**
   ```
   user_data.db → data/
   user_data.db.local_backup → data/
   ```

---

# 💻 Copilot 區域 (實際執行)
# ════════════════════════════════════════════════════════════

## 當前任務隊列

### ✅ 已完成
- [x] 移除 update_restart.py 定期檢查（crontab 已刪除）
- [x] 移除 sync_to_sheet.py 定期同步（crontab 已刪除）
- [x] Webhook 系統已驗證正常運作

### ⏳ 進行中
- [ ] 修復 `auto_update_webhook.py` (GPT 發號施令中)
- [ ] 項目文件結構整理 (GPT 發號施令中)

### 📋 待執行

---

## 執行日誌
- **2026-05-03**: Copilot 開始修復 auto_update_webhook.py
  - [ ] 檢查現有 curl 調用位置
  - [ ] 編寫 requests 版本
  - [ ] 本地測試
  - [ ] 提交到 Git

---

# ════════════════════════════════════════════════════════════
# 📝 參考：舊內容存檔（Gemini 技術分析備份）
# ════════════════════════════════════════════════════════════

### 階段 0 核對項目補充
**已在 repo memory 記錄的已知事項：**
- ✅ 日誌亂碼問題已部署修復，但根本原因是 UTF-8 編碼轉換限制（影響顯示，不影響日誌功能）
- ✅ 三個 Bot 服務已配置編碼標準：`PYTHONIOENCODING=utf-8, LANG=C.UTF-8`
- ✅ systemd 輸出配置：`StandardOutput=journal`

**檢查清單補充：**
1. 確認 `config/config.json` 中的 `url` 字段是否為最新隧道 URL
2. 驗證 `scheduled_tasks/auto_update_webhook.py` 的執行日誌：`sudo tail -50 /var/log/webhook_auto_update.log`
3. 檢查 crontab 是否正確配置了 5 分鐘執行一次的監控

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

### 📁 建議的新目錄結構

```
kkgroup/
├── archive/                      # 只保留必要的歷史參考
│   ├── README.md                 # 說明這些是什麼
│   └── (其他一次性腳本/備份 → 移除或壓縮)
├── bots/                         # ✅ 良好
├── cogs/
│   ├── common/                   # 需整理 work_function/ 結構
│   ├── shop/                    # ✅ 良好
│   └── ui/                      # ✅ 結構最佳
├── config/                       # ✅ 良好 (JSON 應統一至此)
├── data/                         # 統一數據存放 (db, cache 等)
├── docs_and_tests/               # 可考慮重命名為 docs/ 或 tools/
├── scripts/                      # 統一腳本存放 (從根目錄移入)
├── shared/                       # ✅ 良好
├── utils/                        # ✅ 良好
├── web/                          # ✅ 良好
└── (根目錄只留必要文件: .env, .gitignore, requirements.txt 等)
```
