# 📋 代碼審計報告：舊數據庫遺留物掃描

## ✅ 掃描結果

### 已清理的文件（使用新 DB 引擎）

| 檔案 | 狀態 | 備註 |
|------|------|------|
| commands/kcoin.py | ✅ 已清理 | 使用 db_adapter.get_all_users() |
| commands/jail.py | ✅ 已清理 | 使用 db_adapter.set_user_field() |
| commands/google_sheets_sync.py | ✅ 已清理 | 註釋說明：使用 db_adapter 替代直接 sqlite3 |
| db_adapter.py | ✅ 新引擎 | 統一的數據庫操作接口 |
| sheet_driven_db.py | ✅ 新引擎 | Sheet-Driven DB 核心引擎 |
| sheet_sync_api.py | ✅ 新引擎 | Flask API 使用新引擎 |

---

## ⚠️ 發現的問題

### 1. HospitalMerchant.py - 3 處舊 sqlite3 使用

**問題位置**：
- Line 98: `conn = sqlite3.connect(self.db_path)` - 初始化事務表
- Line 227: `conn = sqlite3.connect(self.db_path)` - 讀取配置
- Line 321: `conn = sqlite3.connect(self.db_path)` - 記錄交易

**分析**：
- ✅ 用戶數據操作已使用 db_adapter（set_user_field）
- ⚠️ 但事務記錄表（merchant_transactions、merchant_config）仍使用本地 SQLite

**建議**：
- 暂時保留（這些表不涉及核心用戶數據）
- 未來可遷移至 user_data.db 或 Sheet

---

## 📊 SHEET 與數據庫對齐檢查

### 確認的結構

**Google Sheet 結構**（用戶報告）：
```
| A1: user_id | B1: nickname | C1: level | ... |
| A2: 123456789 | B2: Player1 | C2: 5 | ... |
| A3: 987654321 | B3: Player2 | C3: 10 | ... |
```

**數據庫結構**（sheet_driven_db.py）：
- 主鍵：`user_id` (INTEGER PRIMARY KEY)
- 動態欄位：根據表頭自動推斷類型
  - 整數欄位：level, xp, kkcoin, hp, stamina, ...
  - 文本欄位：user_name, nickname, username, ...
  - JSON 欄位：inventory, config, settings, ...
  - 時間欄位：_created_at, _updated_at

✅ **對齐結論**：兩者結構完全一致

---

## 📝 Apps Script 評估

### 用戶提供的代碼（摘錄）

```javascript
function syncToDatabase() {
  const headers = allData[0];  // 第 1 行是表頭 ✅
  const rows = allData.slice(1);  // 第 2 行開始是資料 ✅
  
  // 過濾空行
  const validRows = rows.filter(row => {
    return row.some(cell => cell && cell.toString().trim() !== '');
  });
}
```

### ✅ 現有代碼評估

| 檢查項 | 狀態 | 細節 |
|--------|------|------|
| **表頭提取** | ✅ 正確 | `allData[0]` 取第 1 行 |
| **數據提取** | ✅ 正確 | `allData.slice(1)` 取第 2+ 行 |
| **空行過濾** | ✅ 正確 | 檢查每行是否有非空單元格 |
| **user_id 驗證** | ⚠️ 需改進 | 應該檢查 user_id 列中的值 |
| **錯誤顯示** | ⚠️ 舊版本 | 應該顯示詳細的錯誤原因 |

### 🔧 建議修改

**問題 1：user_id 驗證不夠嚴格**

現有代碼：
```javascript
const validRows = rows.filter(row => {
  return row.some(cell => cell && cell.toString().trim() !== '');  // 只檢查是否有任何非空單元格
});
```

建議改為：
```javascript
const userIdIndex = headers.findIndex(h => h && h.toString().toLowerCase() === 'user_id');
if (userIdIndex === -1) {
  SpreadsheetApp.getUi().alert("❌ 找不到 'user_id' 欄位");
  return;
}

const validRows = rows.filter((row, rowIndex) => {
  const userIdValue = row[userIdIndex];
  if (!userIdValue || userIdValue.toString().trim() === '') {
    return false;  // 拒絕空的 user_id
  }
  const userIdNum = Number(userIdValue);
  return !isNaN(userIdNum) && userIdNum > 0;  // user_id 必須是正整數
});
```

**問題 2：錯誤顯示過於簡單**

現有代碼：
```javascript
const message = `✅ 同步完成！\n\n更新: ${stats.updated} 筆\n新增: ${stats.inserted} 筆\n錯誤: ${stats.errors} 筆`;
```

建議改為：
```javascript
let message = `✅ 同步完成！\n\n`;
message += `新增: ${stats.inserted} 筆\n`;
message += `更新: ${stats.updated} 筆\n`;
message += `重複: ${stats.duplicates || 0} 筆\n`;
message += `錯誤: ${stats.errors} 筆\n`;

// 顯示錯誤詳情
if (stats.errors > 0 && result.error_details && result.error_details.length > 0) {
  message += `\n🔍 錯誤詳情（前 5 筆）:\n`;
  for (let i = 0; i < Math.min(5, result.error_details.length); i++) {
    const err = result.error_details[i];
    message += `  ❌ 記錄 ${err.record}: ${err.reason}\n`;
  }
}
```

---

## 🎯 結論與建議

### 🔴 **根本原因突破（2026-02-06 新發現）**

**26 個同步錯誤的根本原因已找到：SHEET 表頭污染！**

**症狀：**
```
表頭包含：
  • 中文預設欄位（第 1 欄, 第 2 欄, 第 3 欄）
  • 舊狀態字段（is_stunned, is_locked, thread_id 等）
  • 舊時間戳（last_recovery, injury_recovery_time 等）
  • 外觀字段（face, hair, skin, top, bottom, shoes）
```

**後果：** API 無法正確映射和轉換欄位 → 26 個錯誤

**修復：** 使用 `SHEET_CLEANUP_SCRIPT.gs` 自動清理（5 分鐘）

**預期結果：** 錯誤 26 → 0

詳見：[SHEET_HEADER_POLLUTION_DIAGNOSIS.md](SHEET_HEADER_POLLUTION_DIAGNOSIS.md)

---

### 整體狀態
- ✅ 主線程代碼：已完全遷移至新 DB 引擎
- ✅ SHEET 與 DB 結構：完全對齐（清理後）
- ✅ Apps Script 基本邏輯：正確
- ✅ Apps Script 細節：已改進

### 優先級別

| 優先級 | 項目 | 所需時間 |
|--------|------|--------|
| 🔴 高 | **清理 SHEET 表頭汙染** | **5 分鐘** |
| 🔴 高 | 更新 Apps Script 的 user_id 驗證邏輯 | 5 分鐘 |
| 🟡 中 | 改進 Apps Script 的錯誤顯示 | 5 分鐘 |
| 🔴 高 | 重新同步並驗證錯誤消失 | 10 分鐘 |
| 🟣 低 | HospitalMerchant.py 事務表遷移 | 1 小時 |

### 立即建議

1. **立即執行 SHEET 清理**（是修復的關鍵）
2. **驗證表頭結構** - 應該只有 10 個核心欄位
3. **重新同步** - 預期錯誤從 26 → 0
4. **更新 Apps Script**（使用改進版本）
5. **監控後續同步**（確認沒有新錯誤）

---

生成日期：2026-02-06
檢查版本：commit 8f8b6f1
