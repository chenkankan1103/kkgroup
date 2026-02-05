# 資料庫與 SHEET 設定整理

## 📋 目前設定情況

### 1. SQLite 資料庫設定
| 項目 | 設定值 | 檔案 |
|------|--------|------|
| **資料庫檔案名稱** | `user_data.db` | sheet_driven_db.py (行34)、db_adapter.py、sheet_sync_api.py |
| **表名稱** | `users` | sheet_driven_db.py (行44) |
| **主鍵欄位** | `user_id` | sheet_driven_db.py |

### 2. Google Sheet 設定
| 項目 | 設定值 | 檔案 |
|------|--------|------|
| **SHEET_ID** | `1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM` | verify_user_id.py (行40)、sync_to_sheet.py (行628) |
| **工作頁名稱** | `玩家資料` | commands/google_sheets_sync.py (行23)、verify_user_id.py (行41) |
| **Sheet 結構** | Row 1 = 表頭（user_id, level, xp, ...）<br>Row 2+ = 資料 | 所有同步檔案 |

### 3. Flask API 設定
| 項目 | 設定值 | 檔案 |
|------|--------|------|
| **API 端點** | `http://35.209.101.28:5000` | SHEET_SYNC_APPS_SCRIPT_UPDATED.gs (行17) |
| **同步路由** | `/api/sync` | sheet_sync_api.py |
| **API 初始化 DB** | `user_data.db` | sheet_sync_api.py (行25) |

---

## ⚠️ 發現的對應問題

### 問題 1：Apps Script 工作頁指定不明確
**現狀：**
```javascript
// SHEET_SYNC_APPS_SCRIPT_UPDATED.gs
const sheet = SpreadsheetApp.getActiveSheet();  // 使用「目前打開」的工作頁
const allData = sheet.getDataRange().getValues();
```

**問題：**
- 如果 Google Sheet 中有多個工作頁，使用 `getActiveSheet()` 會讀取使用者目前打開的工作頁
- 如果使用者打開了錯誤的工作頁（不是「玩家資料」），同步會失敗或讀到錯誤資料

**應該改為：**
```javascript
const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
const sheet = spreadsheet.getSheetByName('玩家資料');  // ✅ 明確指定工作頁
const allData = sheet.getDataRange().getValues();
```

---

### 問題 2：資料庫檔案未被收入 Git
**現狀：**
- Python 代碼都使用 `user_data.db`
- GCP 上應該有 user_data.db 副本

**需要驗證：**
- [ ] `.gitignore` 是否排除了 `user_data.db`（應該排除，因為每個環境都有各自的資料）
- [ ] GCP 上是否成功創建了 `user_data.db`
- [ ] GCP user_data.db 與本地 user_data.db 是否需要同步

---

### 問題 3：Sheet 表頭結構清晰度
**設定：**
- Row 1 = 表頭（user_id, level, xp, kkcoin, ...）
- Row 2+ = 資料行

**確認點：**
- [x] Apps Script 正確讀取 Row 1 作表頭
- [x] Apps Script 正確讀取 Row 2+ 作資料
- [x] Flask API 正確接收並處理

---

## 🔧 建議的修復清單

### 即刻修復（關鍵）
1. **更新 Apps Script 代碼**
   - 使用 `getSheetByName('玩家資料')` 而不是 `getActiveSheet()`
   - 原因：確保總是同步到正確的工作頁

2. **驗證 GCP user_data.db**
   ```bash
   # SSH 進 GCP
   ls -lah /home/[username]/kkgroup/user_data.db
   sqlite3 /home/[username]/kkgroup/user_data.db ".tables"
   ```

3. **檢查 .gitignore**
   ```bash
   cat .gitignore | grep user_data.db
   ```

### 長期改進（選擇性）
1. 在專案文件中記錄所有 Sheet 設定（目前已完成）
2. 添加環境變數方案（.env 存儲 SHEET_ID 和工作頁名稱）

---

## 📊 同步流程圖

```
Google Sheet（玩家資料工作頁）
    ↓ 手動點擊「同步到資料庫」
Apps Script（SHEET_SYNC_APPS_SCRIPT_UPDATED.gs）
    ↓ POST /api/sync
Flask API（sheet_sync_api.py）
    ↓ 呼叫 sync_manager.sync_from_sheet()
SheetSyncManager & SheetDrivenDB
    ↓ INSERT/UPDATE
SQLite（user_data.db）
    ↑ 由 Python 命令（kcoin.py, jail.py 等）讀取/更新
Discord Bot
```

---

## 最終檢查清單

- [x] 資料庫名稱統一：`user_data.db`
- [x] 表名統一：`users`
- [x] Google Sheet ID 已設定：`1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM`
- [x] 工作頁名稱已設定：`玩家資料`
- [x] Flask API 端點已設定：`http://35.209.101.28:5000`
- [ ] **Apps Script 工作頁明確指定** → 待修復
- [ ] GCP user_data.db 驗證 → 待驗證
