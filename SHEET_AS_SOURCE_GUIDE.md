# 🎯 SHEET 為主的同步系統 - 實作指南

**更新日期：** 2026-02-06  
**新功能：** API 現在支持根據 SHEET 表頭順序導出數據

---

## 📌 核心概念

**以前的問題：**
- 從 DB 導出數據時，按 DB 的列順序
- 導致 SHEET 中的欄位錯位（例如 nickname 在第 19 列而不是第 2 列）

**新的解決方案：**
- Apps Script 在調用 `/api/export` 時，傳送 SHEET 的表頭順序
- API 根據 SHEET 的順序重新排列導出的數據
- ✅ **結果：DB 的數據完全按照 SHEET 的欄位順序返回**

---

## 🔧 實作步驟

### 步驟 1：更新 Flask API（已完成）

✅ `sheet_sync_api.py` 已更新：
- `/api/export` 現在支持 POST 請求
- 可以接收 `headers` 參數（SHEET 的表頭順序）
- 根據表頭順序重新排列導出的數據

✅ `sheet_driven_db.py` 已新增：
- `export_to_sheet_format_ordered()` 方法
- 按指定的表頭順序導出數據

### 步驟 2：更新 Google Apps Script（已完成）

✅ `SHEET_SYNC_APPS_SCRIPT_UPDATED.gs` 已更新：
- `syncFromDatabase()` 现在傳送 SHEET 的表頭到 API
- 自動檢測當前 SHEET 的表頭
- 如果沒有表頭，則降級為 GET 請求（向後相容）

### 步驟 3：部署到 Google Sheet

1. 在 Google Sheet 中打開「玩家資料」工作頁
2. 選擇「擴充功能」→「Apps Script」
3. 複製 `SHEET_SYNC_APPS_SCRIPT_UPDATED.gs` 中的代碼
4. 保存並刷新 SHEET

---

## 🚀 使用方式

### 同步到資料庫（SHEET → DB）

```
1. 在 SHEET 中做更改（例如改變 level、kkcoin 等）
2. 點選「🔄 同步工具」→「📤 同步到資料庫」
3. 數據写入 DB（按 SHEET 的欄位順序）
```

### 從資料庫同步（DB → SHEET）⭐ **新功能**

```
1. 點選「🔄 同步工具」→「📥 從資料庫同步」
2. API 自動按 SHEET 的表頭順序返回 DB 中的數據
3. ✅ SHEET 中的欄位現在不會錯位！
```

---

## 📊 API 文檔

### POST /api/export（新功能）

**請求體：**
```json
{
  "headers": ["user_id", "nickname", "level", "kkcoin", "hp", "stamina", "face", "hair", "skin", "top", "bottom", "shoes"]
}
```

**回應：**
```json
{
  "status": "success",
  "headers": ["user_id", "nickname", "level", "kkcoin", "hp", "stamina", "face", "hair", "skin", "top", "bottom", "shoes"],
  "rows": [
    [123456789, "Player1", 5, 1000, 100, 100, 0, 1, 2, 3, 4, 5],
    [987654321, "Player2", 10, 5000, 100, 100, 1, 2, 3, 4, 5, 6]
  ],
  "stats": {
    "total_rows": 2,
    "total_columns": 12,
    "exported_at": "2026-02-06T12:34:56"
  }
}
```

**重點：** 返回的列順序與請求中的 `headers` 順序相同！

### GET /api/export（向後相容）

**回應：**
```json
{
  "status": "success",
  "headers": ["user_id", "...(DB順序)..."],
  "rows": [...],
  "message": "導出 N 筆用戶資料（按 DB 順序）"
}
```

**說明：** 如果沒有傳送表頭，則按 DB 的列順序返回（原始行為）

---

## ✅ 驗證方式

### 驗證 1：欄位位置是否正確

```
1. 在 SHEET 中查看同步回來的數據
2. 確認：
   - A1: user_id
   - B1: 你的第二個欄位（例如 nickname）
   - ...(其他欄位按順序排列)
```

### 驗證 2：沒有欄位錯位

```
1. 修改 DB 中某個玩家的 level（通過機器人或其他方式）
2. 執行「從資料庫同步」
3. 確認 level 更新到了 SHEET 中正確的欄位（而不是其他欄位）
```

### 驗證 3：測試 curl 命令

```bash
# 手動測試 API（以 SHEET 為主）
curl -X POST http://35.209.101.28:5000/api/export \
  -H "Content-Type: application/json" \
  -d '{
    "headers": ["user_id", "nickname", "level", "kkcoin"]
  }'

# 回應應該按照請求的順序返回
```

---

## 🔄 工作流程圖

```
SHEET（玩家資料工作頁）
  │
  ├─ 表頭順序（例如：user_id, last_recovery, ..., nickname）
  │
  ├─ 📤 同步到資料庫
  │    └─ Apps Script 發送 SHEET 數據和表頭到 /api/sync
  │    └─ API 按表頭順序存儲到 DB
  │
  └─ 📥 從資料庫同步
       ├─ Apps Script 讀取當前 SHEET 的表頭
       ├─ 發送表頭順序到 /api/export（POST）
       ├─ API 按該順序從 DB 查詢數據
       ├─ 返回重新排列的數據
       └─ 寫回 SHEET（欄位位置正確！）

DB（SQLite3）
  └─ 實際存儲的列順序可能不同，但被 API 重新排列
```

---

## 🎯 常見問題

**Q1：如果 SHEET 中有 DB 沒有的欄位怎麼辦？**

A：API 會自動用空值填充那些欄位。

```python
# 例如 SHEET 有這些欄位：
headers = ['user_id', 'nickname', 'custom_field']

# 但 DB 中沒有 'custom_field'
# API 會返回：
[123456789, 'Player1', '']  # ← custom_field 為空
```

---

**Q2：如果 SHEET 的表頭順序與之前不同會怎樣？**

A：API 會按新的順序返回數據。這允許你隨時調整 SHEET 的欄位順序，數據會自動按新順序同步。

```
舊順序：user_id, nickname, level, kkcoin
新順序：user_id, kkcoin, level, nickname

同步後→ 數據會按新順序重新排列
```

---

**Q3：向後相容嗎？**

A：是的！如果 Apps Script 仍然使用 GET 請求（舊版本），API 會按 DB 順序返回（原始行為）。

---

## 📝 下一步

1. ✅ **更新 Flask API** ← 已完成（sheet_sync_api.py, sheet_driven_db.py）
2. ✅ **更新 Apps Script** ← 已完成（SHEET_SYNC_APPS_SCRIPT_UPDATED.gs）
3. 🔄 **部署到 Google Sheet** ← 需要用戶操作
4. 🧪 **測試同步功能** ← 驗證欄位順序是否正確

---

## 🔍 故障排除

### 同步後欄位仍然錯位

**原因：** Apps Script 版本過舊或未正確傳送表頭

**解決：**
1. 確保使用了 SHEET_SYNC_APPS_SCRIPT_UPDATED.gs 的最新版本
2. 檢查 Apps Script 的執行日誌
3. 確認 API 是否收到了 headers 參數

### API 返回 400 或其他錯誤

**原因：** 表頭格式不正確或包含無效字符

**解決：**
1. 檢查表頭是否包含 `第 1 欄` 等垃圾欄位（應該刪除）
2. 過濾空白欄位
3. 確保所有表頭都是有效的列名

---

**總結：** 這個更新使 SHEET 成為「同步的主源」，API 會尊重 SHEET 定義的欄位順序和結構！
