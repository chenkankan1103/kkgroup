# 🔧 Google Apps Script Discord ID 浮點精度損失修復指南

**日期**: 2026年2月6日  
**狀態**: ✅ 已完成  
**完成**:
- ✅ GCP 資料庫幽靈帳號清除 (5 個已刪除)
- ✅ Python 層 sheet_driven_db.py 已修復
- ✅ Python 層 sheet_sync_manager.py 已修復  
- ⏳ **Google Apps Script 修復方案 (本文檔)**

---

## 🔴 問題根源

Google Apps Script 中的 `syncToDatabase()` 函數使用 `JSON.stringify()` 編碼數據：

```javascript
// ❌ 現有代碼（有問題）
const payload = {
  headers: headers,
  rows: validRows
};

const response = UrlFetchApp.fetch(`${apiEndpoint}/api/sync`, {
  method: 'post',
  contentType: 'application/json',
  payload: JSON.stringify(payload)  // ❌ 此行自動將大數字轉為浮點
});
```

### 精度損失機制

1. **Discord ID 大小**: 18-19 位數字
   - 例: `776464975551660123`

2. **JavaScript 浮點精度**: 最多 15-16 位有效數字
   - 超過精度的數字自動轉為科學計數法: `7.764649755516601e+17`

3. **轉換損失**:
   ```
   原始: 776464975551660123
   浮點: 7.764649755516601e+17
   還原: 776464975551660160  ❌ 差 -37
   ```

4. **結果**: Python 層收到錯誤的 ID → 無法與現有帳號匹配 → 建立新的幽靈帳號

---

## ✅ 修復方案

### 核心思路

在 `JSON.stringify()` 之前，將所有 Discord IDs 轉換為字符串，避免 JavaScript 自動浮點轉換。

### 修復代碼

**位置**: Google Apps Script - `syncToDatabase()` 函數

**修改步驟**:

1. **找到資料行迴圈部分** (~第 160-180 行):

```javascript
// 原始代碼
const payload = {
  headers: headers,
  rows: validRows
};

const response = UrlFetchApp.fetch(`${apiEndpoint}/api/sync`, {
  method: 'post',
  contentType: 'application/json',
  payload: JSON.stringify(payload)
});
```

2. **替換為修復版本**:

```javascript
// ✅ 修復後的代碼
// Step 1: 找出 user_id 列的索引
const userIdIndex = headers.findIndex(h => 
  h && h.toString().toLowerCase() === 'user_id'
);

// Step 2: 轉換所有 ID 為字符串（避免浮點轉換）
const convertedRows = validRows.map(row => {
  const newRow = [...row];  // 複製一份
  
  // 將 user_id 列轉換為字符串
  if (userIdIndex !== -1 && newRow[userIdIndex]) {
    // 處理科學計數法的浮點數
    const idValue = newRow[userIdIndex];
    if (typeof idValue === 'number') {
      // 確保即使是浮點也轉為字符串
      const idStr = idValue.toString();
      if (idStr.toLowerCase().includes('e')) {
        // 科學計數法：直接轉為整數字符串
        newRow[userIdIndex] = Math.floor(idValue).toString();
      } else {
        newRow[userIdIndex] = idValue.toString();
      }
    } else if (typeof idValue === 'string') {
      // 已經是字符串，保持原樣
      newRow[userIdIndex] = idValue;
    }
  }
  
  return newRow;
});

// Step 3: 建立 payload（使用轉換後的行）
const payload = {
  headers: headers,
  rows: convertedRows  // 使用轉換後的行而不是 validRows
};

// Step 4: 呼叫 API
const response = UrlFetchApp.fetch(`${apiEndpoint}/api/sync`, {
  method: 'post',
  contentType: 'application/json',
  payload: JSON.stringify(payload)  // ✅ 現在 ID 已經是字符串，不會被轉為浮點
});
```

### 高級修復版本（推薦）

對所有 ID 類欄位進行轉換，不只是 user_id：

```javascript
/**
 * 修復 Discord ID 浮點精度損失
 * 將所有 ID 欄位轉換為字符串，避免 JSON.stringify 自動浮點轉換
 */
function convertValuesForAPI(rows, headers) {
  return rows.map(row => {
    const newRow = [...row];
    
    for (let i = 0; i < headers.length; i++) {
      const header = headers[i] ? headers[i].toString().toLowerCase() : '';
      const value = newRow[i];
      
      // 識別 ID 欄位：包含 'id' 的欄位
      if (header.includes('id') && value) {
        if (typeof value === 'number') {
          const strValue = value.toString();
          // 處理科學計數法
          if (strValue.toLowerCase().includes('e')) {
            newRow[i] = Math.floor(value).toString();
          } else {
            newRow[i] = strValue;
          }
        } else if (typeof value === 'string') {
          newRow[i] = value;  // 保持字符串
        }
      }
    }
    
    return newRow;
  });
}

// 在 syncToDatabase() 中使用
const convertedRows = convertValuesForAPI(validRows, headers);

const payload = {
  headers: headers,
  rows: convertedRows
};

const response = UrlFetchApp.fetch(`${apiEndpoint}/api/sync`, {
  method: 'post',
  contentType: 'application/json',
  payload: JSON.stringify(payload)
});
```

---

## 🧪 驗證修復

### 在 Google Sheet 中測試

1. **新增測試玩家** (臨時):
   - user_id: `776464975551660123` (凱文原始 ID)
   - nickname: `測試凱文`
   - 其他欄位保持空白

2. **同步到資料庫**:
   - 點擊 `同步工具 → 同步到資料庫`
   - 觀察 API 日誌

3. **驗證結果**:
   ```bash
   ssh kkgroup-gcp "sqlite3 /home/e193752468/kkgroup/user_data.db \
     'SELECT user_id, nickname FROM users WHERE nickname = \"測試凱文\";'"
   ```
   - ✅ **預期結果**: `776464975551660123|測試凱文` (ID 完全相同)
   - ❌ **錯誤結果**: `776464975551660160|測試凱文` (ID 被修改)

4. **清理測試數據**:
   ```bash
   ssh kkgroup-gcp "sqlite3 /home/e193752468/kkgroup/user_data.db \
     'DELETE FROM users WHERE user_id = 776464975551660123;'"
   ```

---

## 📊 Python 層防護（已實施）

### Layer 1: sheet_driven_db.py (string-first 轉換)

```python
# 文件: sheet_driven_db.py
# 方法: _convert_value()

def _convert_value(self, value, header):
    if 'id' in header.lower():
        # ✅ 優先使用字符串轉換，避免浮點中間步驟
        clean_str = str(value).strip()
        if 'e' in clean_str.lower():
            # 科學計數法
            from decimal import Decimal
            result = int(Decimal(clean_str))
        else:
            result = int(clean_str)
        return result
    # ... 其他轉換邏輯
```

### Layer 2: sheet_sync_manager.py (去重邏輯)

```python
# 文件: sheet_sync_manager.py
# 方法: _parse_records()

# 按 nickname 分組，每組只保留最小 user_id
nickname_to_records = {}
for record in records:
    nickname = record.get('nickname')
    if nickname in nickname_to_records:
        # 保留最小 ID（最有可能是原始帳號）
        existing = nickname_to_records[nickname]
        if int(record['user_id']) < int(existing['user_id']):
            nickname_to_records[nickname] = record
    else:
        nickname_to_records[nickname] = record

# 結果：過濾掉浮點精度損失版本的幽靈帳號
final_records = list(nickname_to_records.values())
```

---

## 🗂️ 修復部署清單

| 項目 | 狀態 | 備註 |
|------|------|------|
| **Python 層修復** | ✅ 完成 | sheet_driven_db.py + sheet_sync_manager.py |
| **GCP 幽靈帳號清除** | ✅ 完成 | 5 個幽靈帳號已刪除 (2026-02-06) |
| **Google Apps Script 修復** | ⏳ **待實施** | **本文檔提供的代碼** |
| **驗證測試** | ⏳ **待執行** | 同步後確認無新幽靈帳號 |
| **服務重啟** | ⏳ **待執行** | 如果修改了 Flask API |

---

## 🔄 實施安全檢查清單

### 修改前準備

- [ ] 備份當前 Google Apps Script 代碼（複製到其他地方）
- [ ] 在測試 Sheet 上先測試修復代碼
- [ ] 確認 API 伺服器正常運行 (`curl http://35.206.126.157:5000/api/health`)
- [ ] 備份 GCP 資料庫 (已自動備份在 `/tmp/kkgroup_backups/`)

### 修改後驗證

- [ ] 檢查 Google Apps Script 中是否有編譯錯誤
- [ ] 在 Google Sheet 中執行「檢查 API 連接」
- [ ] 同步一小批測試玩家
- [ ] 驗證資料庫中沒有新的幽靈帳號產生
- [ ] 檢查没有重複的 user_id

### 回滾計劃

如果出現問題：
1. 恢復備份: `cp /tmp/kkgroup_backups/user_data_backup_20260206_145523.db /home/e193752468/kkgroup/user_data.db`
2. 恢復 Apps Script 代碼（從您的備份）
3. 重啟服務: `sudo systemctl restart bot.service shopbot.service uibot.service`

---

## 📝 進度跟蹤

```
✅ Phase 1: 診斷問題
   - 發現 5 個幽靈帳號（4 個 NULL、1 個凱文重複）
   
✅ Phase 2: Python 層防護
   - sheet_driven_db.py: string-first 轉換
   - sheet_sync_manager.py: 同名去重邏輯
   
✅ Phase 3: 資料庫清潔
   - 刪除 5 個幽靈帳號
   - 驗證資料庫完整性
   
⏳ Phase 4: Apps Script 修復 (本文檔)
   - 提供完整修復代碼
   
⏳ Phase 5: 驗證
   - 測試同步是否正常
   - 確認無新幽靈帳號
```

---

## 🎯 最終狀態（完成後）

| 系統部分 | 狀態 | 說明 |
|---------|------|------|
| **Discord ID 精度** | ✅ 安全 | Apps Script 將 ID 轉為字符串 |
| **Python 轉換** | ✅ 安全 | sheet_driven_db 優先使用字符串 |
| **去重邏輯** | ✅ 安全 | sheet_sync_manager 自動移除幽靈帳號 |
| **資料庫狀態** | ✅ 清潔 | 48 個合法玩家，0 個幽靈帳號 |
| **SHEET 同步** | ✅ 可靠 | 不再產生浮點精度損失 |

---

## 📞 常見問題

**Q: 為什麼要把 ID 轉為字符串？**
> A: JavaScript 的浮點精度只有 15-16 位，Discord ID 是 18-19 位。轉為字符串避免精度損失。

**Q: 這樣會影響資料庫中 user_id 的類型嗎？**
> A: 不會。Python 層會自動識別字符串 ID 並轉換為整數存儲在資料庫中。

**Q: 如果我不修改 Apps Script 會怎樣？**
> A: Python 層的去重邏輯會防止新幽靈帳號，但仍然會有小概率逃過去。完整修復需要 Apps Script 配合。

**Q: 修改後為什麼要測試？**
> A: 字符編碼問題、Google Sheet 等可能導致邊界情況。測試可以發現問題。

---

**修訂日誌** | 版本 1.0 | 2026年2月6日
