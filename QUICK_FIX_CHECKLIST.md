# ⚡ 快速修復清單 - SHEET 同步問題

## 🎯 問題
- ❌ 點擊 Apps Script「同步」沒有效果
- ❌ 舊的 Discord Bot 自動同步還在運行
- ❌ 表頭被識別為「第 1 欄」、「第 2 欄」
- ❌ 同步日誌顯示「無法轉換: user_id」

---

## ✅ 已完成的修復

### 修復 1️⃣: 停用 Discord Bot 舊循環
**文件**: `commands/google_sheets_sync.py` - 第 33-36 行
```
[已修改] 註釋掉 auto_sync_loop.start() 和 auto_export_loop.start()
```

### 修復 2️⃣: 改進 Apps Script 過濾
**文件**: `SHEET_SYNC_APPS_SCRIPT.gs` - syncToDatabase() 函數
```
[已修改] 重寫表頭和數據行過濾邏輯，加強日誌輸出
```

### 修復 3️⃣: 強化 Python API 防護
**文件**: `sheet_sync_manager.py` - _to_int() 方法
```
[已驗證] 確認字段名過濾邏輯存在 (isalpha() 和 '_' 檢查)
```

---

## 🚀 立即執行的 5 個步驟

### Step 1: 更新 GCP 代碼 (5 分鐘)
```bash
cd /path/to/kkgroup
git pull origin main
# 或手動上傳：commands/google_sheets_sync.py, sheet_sync_manager.py, sheet_sync_api.py
```

### Step 2: 重啟 Flask API (2 分鐘)
```bash
sudo supervisorctl restart sheet-sync-api
# 驗證
curl http://localhost:5000/api/health
```

### Step 3: 更新 Google Sheets Apps Script (10 分鐘)
1. 打開「玩家資料」Google Sheets
2. 「擴充功能」→ 「Apps Script」
3. 複製 `SHEET_SYNC_APPS_SCRIPT.gs` 全部內容
4. 修改 `API_ENDPOINT = "http://YOUR_GCP_IP:5000"`
5. 保存 (Ctrl+S)
6. 刷新 Sheets 頁面 (F5)

### Step 4: 驗證連接 (2 分鐘)
1. 在 Sheets 中點擊「🔄 同步工具」→「✅ 檢查 API 連接」
2. 應看到: `✅ API 連接正常`

### Step 5: 測試同步 (3 分鐘)
1. 在 SHEET 中編輯一筆玩家數據
2. 點擊「📤 同步到資料庫」
3. 檢查日誌：按 Ctrl+Enter 查看 Apps Script 執行日誌
4. 驗證: 表頭應該是 `user_id, nickname, ...` 而非「第 1 欄」

---

## 🔍 驗證清單

執行後檢查 ✅:

| 項目 | 檢查方法 | 期望結果 |
|------|---------|---------|
| **API 狀態** | `curl http://localhost:5000/api/health` | `{"status": "ok"}` |
| **Apps Script 更新** | 點「檢查 API 連接」 | ✅ API 連接正常 |
| **表頭識別** | 執行日誌中的「表頭已識別」 | `user_id, nickname, level...` |
| **數據驗證** | 執行日誌中的「第 1 筆資料」 | 第 1 列是數字 |
| **同步成功** | 執行日誌中的「同步完成」 | 更新/新增數 > 0 |

---

## ⚠️ 常見問題速解

### Q: API 顯示「連接失敗」
```
原因: GCP IP 錯誤或防火牆關閉
解決: 
1. 確認 API_ENDPOINT 是否是正確的 GCP 外部 IP
2. 檢查防火牆: gcloud compute firewall-rules list
3. 重啟 Flask: sudo supervisorctl restart sheet-sync-api
```

### Q: 日誌顯示「無法轉換: user_id」
```
原因: 表頭還是被當作第一筆數據
解決:
1. 確認 SHEET 結構: Row 1=分組, Row 2=表頭, Row 3+=資料
2. 重新複製最新的 SHEET_SYNC_APPS_SCRIPT.gs
3. 檢查日誌中「第 1 筆資料的第 1 列值」是否是數字
```

### Q: 同步返回成功但數據未更新
```
原因: 數據格式或驗證問題
解決:
1. 檢查 Flask API 日誌: tail -f /var/log/sheet-sync-api.log
2. 驗證數據庫: sqlite3 user_data.db "SELECT * FROM users LIMIT 1"
3. 檢查 user_id 是否有效（應該是 16+ 位數字）
```

---

## 📱 完成後的預期行為

✅ **新的流程** (不再依賴 Bot 自動同步):

1. 用戶在 Google Sheets 編輯玩家數據
2. 點擊「🔄 同步工具」→「📤 同步到資料庫」
3. Apps Script 驗證數據、呼叫 Flask API
4. Flask API 接收數據、驗證、插入/更新數據庫
5. Sheets 上顯示同步結果: 更新 X 筆, 新增 Y 筆

---

## 🎓 理解修復內容

**為什麼要停用 Bot 的自動循環?**
- Bot 每 1 分鐘查詢一次 SHEET，容易引發競合條件
- 新的 Apps Script 可以立即同步，更高效
- 單一責任: Bot 專注於遊戲邏輯，API 專注於數據同步

**為什麼要改進過濾邏輯?**
- Google Sheets API 返回的數據包含列標題（「第 1 欄」等）
- 需要正確識別 Row 1=分組, Row 2=真實表頭, Row 3+=數據
- Apps Script 層過濾，Python 層雙重檢查

**為什麼要添加字段名檢查?**
- 防禦性編程: 即使 Apps Script 漏過了，Python 也能檢出
- `_to_int("user_id")` 返回 0 而不是崩潰
- 使同步系統更穩健

---

## 📞 遇到問題?

檢查這些日誌:

1. **Google Apps Script 執行日誌** (Ctrl+Enter):
   ```
   查看表頭、數據行數量、第 1 筆數據的實際內容
   ```

2. **Flask API 日誌** (GCP 實例):
   ```bash
   tail -f /var/log/sheet-sync-api.log
   # 或查看完整輸出
   python sheet_sync_api.py
   ```

3. **SQLite 數據庫驗證** (GCP 實例):
   ```bash
   sqlite3 user_data.db
   SELECT user_id, nickname, updated_at FROM users ORDER BY updated_at DESC LIMIT 5;
   ```

---

✨ **修復完成! 開始使用新的同步系統吧!** ✨

