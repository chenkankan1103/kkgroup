# 🔄 SHEET 同步系統 - 完整設置指南

## ✅ 現況檢查清單

- [x] 代碼遷移：SQLite3 → Sheet-Driven DB，98% 完成
- [x] Flask API：所有核心功能已實現
- [x] Google Sheet 結構：已驗證並對齐
- [x] 錯誤診斷：詳細的錯誤追蹤系統
- [x] Apps Script：已提供改進版本

---

## 📋 模組狀態總結

### 核心模組 ✅

| 模組 | 文件 | 狀態 | 說明 |
|------|------|------|------|
| **Sheet-Driven DB** | sheet_driven_db.py | ✅ 正常 | 核心數據引擎 |
| **Flask API** | sheet_sync_api.py | ✅ 正常 | 同步 API 服務器 |
| **DB 適配層** | db_adapter.py | ✅ 正常 | 統一數據接口 |
| **命令系統** | commands/ | ✅ 正常 | 機器人命令，9/10 遷移完成 |
| **Google Apps Script** | SHEET_SYNC_APPS_SCRIPT_UPDATED.gs | ✅ 正常 | SHEET 同步腳本（已改進） |

### 已識別的待改進項 ⚠️

| 文件 | 問題 | 優先級 | 备註 |
|------|------|--------|------|
| shop_commands/HospitalMerchant.py | 3 個 sqlite3.connect() | 中 | 交易記錄表，非核心數據 |

---

## 🚀 快速部署步驟

### **🔴 Step 0：清理 SHEET 表頭污染（必做！）**

> ⚠️ **重要：如果你的 SHEET 表頭末尾有「第 1 欄、第 2 欄、第 3 欄」或有很多舊欄位（is_stunned, last_recovery 等），必須先清理！**

**症狀檢查：** 你的表頭是否包含以下？
- ❌ `第 1 欄`, `第 2 欄`, `第 3 欄`（中文預設欄位）
- ❌ `is_stunned`, `is_locked`, `thread_id`, `actions_used`（舊狀態字段）
- ❌ `last_recovery`, `injury_recovery_time`, `last_work_date`（舊時間戳）
- ❌ `face`, `hair`, `skin`, `top`, `bottom`, `shoes`（角色外觀，通常不需要）

**如果有以上任何一項，執行清理：**

1. 在 Google Sheet 中
2. 選擇「擴充功能」→「Apps Script」
3. 複製 `SHEET_CLEANUP_SCRIPT.gs` 中的代碼
4. 保存並執行菜單中的「🔧 SHEET 修復工具」→「一鍵清理污染欄位」
5. 等待確認訊息

**清理後的正確表頭應該是：**
```
user_id | nickname | level | xp | kkcoin | hp | stamina | gender | title | streak
```

詳見：[SHEET_HEADER_POLLUTION_DIAGNOSIS.md](SHEET_HEADER_POLLUTION_DIAGNOSIS.md)

---

### Step 1: 檢查 Flask API 運行狀態

```bash
# 在伺服器上執行
curl http://35.209.101.28:5000/api/health

# 預期回應
{
  "status": "ok",
  "message": "Flask API running",
  "timestamp": "2026-02-06T12:34:56"
}
```

如果 API 無回應，重新啟動：
```bash
bash start_bot_and_api.sh
```

### Step 2: 驗證 Google Sheet 結構

你的 Google Sheet 應該有以下結構：

**第 1 行（表頭）：** 必須包含以下欄位
```
user_id | nickname | level | kkcoin | xp | hp | stamina | vip_level | ...
```

**第 2+ 行（數據）：** 實際玩家數據
```
123456789 | Player1 | 5 | 100 | 500 | 100 | 100 | 0 | ...
987654321 | Player2 | 10 | 500 | 1000 | 100 | 100 | 1 | ...
```

**驗證方式：**
1. 打開 Google Sheet
2. 點選「🔄 同步工具」→「🔧 驗證 SHEET 結構」
3. 應顯示 ✅ user_id 欄位已存在

### Step 3: 更新 Google Apps Script（推薦改進版）

**選項 A：使用改進版本（推薦）**

1. 在 Google Sheet 中
2. 選擇「擴充功能」→「Apps Script」
3. 清空編輯器中的代碼
4. 複製 `SHEET_SYNC_APPS_SCRIPT_ENHANCED.gs` 中的全部內容
5. 按下 Ctrl+S 儲存
6. 切換回 Google Sheet，重新整理頁面

**選項 B：保持現有版本**
- 現有的 `SHEET_SYNC_APPS_SCRIPT_UPDATED.gs` 也可以正常使用
- 只是不含以下改進：
  - 自動重試機制
  - 詳細的數據驗證
  - 更完善的錯誤處理

### Step 4: 測試同步功能

#### 測試 1：新增一條記錄

1. 在 Google Sheet 中添加一行數據：
   ```
   A: 999888777 | B: TestUser | C: 5 | D: 100 | ...
   ```
2. 點選「🔄 同步工具」→「📤 同步到資料庫」
3. 預期結果：
   ```
   新增: 1 筆
   更新: 0 筆
   錯誤: 0 筆
   ```

#### 測試 2：更新現有記錄

1. 修改你剛才添加的記錄（例如改 level 為 10）
2. 再點一次「📤 同步到資料庫」
3. 預期結果：
   ```
   新增: 0 筆
   更新: 1 筆  ← 應該是「更新」而不是「新增」
   錯誤: 0 筆
   ```

#### 測試 3：檢查反向同步

1. 點選「🔄 同步工具」→「📥 從資料庫同步」
2. SHEET 應該自動更新，顯示所有資料庫中的數據
3. 該記錄應該出現在 SHEET 中

#### 測試 4：API 連接檢查

1. 點選「🔄 同步工具」→「✅ 檢查 API 連接」
2. 應該顯示：
   ```
   ✅ API 連接正常
   延遲: <100ms
   狀態: ok
   ```

---

## 🔍 故障排除指南

### 問題 1：同步時顯示「❌ 新增」但應該「更新」

**症狀：** 同一條記錄修改後再同步，顯示新增而不是更新

**修復步驟：**
1. 檢查表頭中是否有「user_id」（大小寫不敏感）
2. 確認該欄位的數據都是整數（不是文本）
3. 檢查沒有重複的 user_id

**驗證方式：**
```bash
# 在服務器上執行
sqlite3 user_data.db "SELECT COUNT(*), user_id FROM users GROUP BY user_id HAVING COUNT(*) > 1;"

# 如果有輸出，表示有重複的 user_id（應該沒有）
```

### 問題 2：同步時顯示 26 個錯誤

**症狀：** 使用 `/api/sync` 時有大量錯誤

**調試步驟：**
1. 點選「🔄 同步工具」→「📤 同步到資料庫」
2. 查看「🔍 錯誤詳情」中的前 5 個錯誤
3. 根據錯誤內容判斷：
   - `Invalid value type`：數據格式不符（例如文本在數值欄位）
   - `Column not found`：SHEET 中有 DB 中沒有的欄位
   - `Constraint error`：違反數據庫約束

**修復方案：**
- 檢查發生錯誤的行，修正數據格式
- 確認所有欄位名稱與 SHEET 表頭一致
- 重新同步

### 問題 3：API 連接超時

**症狀：** 點選同步後長時間無回應

**修復步驟：**
1. 檢查伺服器是否運行：
   ```bash
   curl http://35.209.101.28:5000/api/health
   ```

2. 檢查防火牆設置（端口 5000 是否開放）

3. 重新啟動 API：
   ```bash
   bash start_bot_and_api.sh
   ```

### 問題 4：SHEET 無法連接到 Google Apps Script

**症狀：** 點選「🔄 同步工具」時沒有菜單出現

**修復步驟：**
1. 確認已更新 Apps Script（擴充功能 → Apps Script）
2. 檢查是否執行了 onOpen() 函數
3. 在 Google Sheet 中清除快取：
   - 按 F5 重新整理頁面
   - 或重新打開

---

## 📊 API 文檔

### /api/sync - 同步到數據庫

**請求：**
```json
{
  "headers": ["user_id", "nickname", "level", "kkcoin"],
  "rows": [
    [123456789, "Player1", 5, 100],
    [987654321, "Player2", 10, 500]
  ]
}
```

**回應：**
```json
{
  "status": "success",
  "stats": {
    "inserted": 1,
    "updated": 1,
    "duplicates": 0,
    "errors": 0
  },
  "error_details": []
}
```

### /api/export - 從數據庫導出

**請求：**
```bash
GET /api/export
```

**回應：**
```json
{
  "status": "success",
  "headers": ["user_id", "nickname", "level", "kkcoin"],
  "rows": [
    [123456789, "Player1", 5, 100],
    [987654321, "Player2", 10, 500]
  ]
}
```

### /api/stats - 數據庫統計

**請求：**
```bash
GET /api/stats
```

**回應：**
```json
{
  "status": "ok",
  "stats": {
    "total_users": 2,
    "real_users": 2,
    "virtual_accounts": 0,
    "total_kkcoin": 600,
    "total_columns": 8
  }
}
```

---

## 🔓 常見問題 (FAQ)

**Q: SHEET 中添加新欄位後，DB 會自動添加嗎？**

A: 是的。當你添加新欄位到 SHEET 表頭並同步時，系統會自動在 DB 中創建該欄位。數據類型會根據內容自動推斷（整數/文本/JSON）。

---

**Q: 可以刪除 SHEET 中的欄位嗎？**

A: 可以，但不會自動刪除 DB 中的欄位。建議保留關鍵欄位（user_id, nickname, level, kkcoin）。

---

**Q: 如果同步時出現錯誤怎麼辦？**

A: 檢查「🔍 錯誤詳情」，根據具體原因修正：
- 檢查數據類型（例如 level 應該是數字）
- 確保 user_id 非空且為整數
- 檢查是否有重複的 user_id

---

**Q: 可以撤銷同步嗎？**

A: 目前沒有撤銷功能。建議備份 SHEET 和 DB 後再進行批量同步。

---

## 📌 重要提醒

1. **定期備份：** 同步前備份 Google Sheet 和 user_data.db
2. **測試環境：** 先在測試 SHEET 上測試，確認沒問題後再同步生產數據
3. **監控日誌：** 監控 Flask API 日誌，確保沒有隱藏的錯誤

---

## 🎯 後續工作

### 可選的優化項目

1. **修復 HospitalMerchant.py**
   - 將交易記錄遷移到統一 DB
   - 預計工作量：1 小時

2. **自動同步裝置**
   - 使用 Apps Script 時間觸發器自動同步
   - 預計工作量：30 分鐘

3. **同步衝突處理**
   - 當本地和遠程數據有衝突時的策略
   - 預計工作量：2 小時

---

## 📞 支援

如有問題，請：
1. 查看上面的「故障排除指南」
2. 檢查 Flask API 日誌：`tail -f /path/to/flask.log`
3. 檢查 Google Apps Script 日誌：擴充功能 → Apps Script → 執行紀錄

---

**最後更新：** 2026-02-06  
**狀態：** ✅ 生產就緒（除 HospitalMerchant.py 外）
