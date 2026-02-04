# 🎯 SHEET 主導的動態同步架構

## 問題：為什麼需要新架構？

### 舊架構的問題
```
❌ 硬編碼的欄位列表（23 個固定欄位）
❌ 每次添加新欄位需要手動修改代碼
❌ 容易遺漏欄位或錯誤對應
❌ DB schema 和代碼不同步
❌ 維護成本高，容易出錯
```

### 典型場景：添加一個新欄位
1. SHEET 添加新列（例如 `stamina_bonus`）
2. 代碼中要手動添加 `stamina_bonus = to_int(row.get('stamina_bonus', 0))`
3. 代碼中要手動添加到 `user_data` 字典
4. DB schema 要手動執行 `ALTER TABLE`
5. 易於遺漏任何一步

## 解決方案：SHEET 主導架構

```
┌─────────────────────────────────────────────────────────┐
│                   SHEET（真實數據源）                      │
│                    Row 1: 分組標題                        │
│                    Row 2: 實際標題 ← 定義所有欄位         │
│                    Row 3+: 數據                           │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              SheetSyncManager                             │
│  ┌──────────────────────────────────────────────────┐    │
│  │ 1. 動態提取表頭（headers = all_values[1]）      │    │
│  │ 2. 自動遷移 schema（無需手動 ALTER TABLE）      │    │
│  │ 3. 動態解析記錄（無硬編碼欄位）                │    │
│  │ 4. 自動 INSERT/UPDATE                           │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   DB（自動適應）                         │
│   ✅ 新增欄位自動添加                                     │
│   ✅ 無需手動 ALTER TABLE                                │
│   ✅ schema 與 SHEET 永遠同步                            │
└─────────────────────────────────────────────────────────┘
```

## 核心機制

### 1. 動態表頭提取
```python
headers = manager.get_sheet_headers(all_values)
# headers = ['user_id', 'nickname', 'level', 'kkcoin', 'title', ...]
# 自動從 SHEET 第 2 行讀取，無需硬編碼
```

### 2. 自動 Schema 遷移
```python
manager.ensure_db_schema(headers)
# 檢查 DB 中的現有欄位
# 對於 SHEET 中有但 DB 中缺失的欄位，自動執行：
# ALTER TABLE users ADD COLUMN new_field TEXT
```

### 3. 動態記錄解析
```python
records = manager.parse_records(headers, data_rows)
# 根據 headers 動態構建字典
# 無硬編碼欄位提取邏輯
```

### 4. 欄位排除列表
```python
EXCLUDE_FIELDS = {'nickname'}
# SHEET 中有但 DB 中不需要的欄位
# 在同步時自動跳過
```

## 對比：舊 vs 新

### 舊架構（150+ 行）
```python
# ❌ 硬編碼提取每個欄位
user_id = to_int(row.get('user_id', 0))
level = to_int(row.get('level', 1))
xp = to_int(row.get('xp', 0))
kkcoin = to_int(row.get('kkcoin', 0))
title = clean_value(row.get('title', '新手'))
hp = to_int(row.get('hp', 100))
# ... 20+ 行欄位提取代碼

# ❌ 硬編碼構建字典
user_data = {
    'user_id': user_id,
    'level': level,
    'xp': xp,
    'kkcoin': kkcoin,
    'title': title,
    'hp': hp,
    # ... 20+ 行字典構建
}

# ❌ 需要手動同步 schema
# 每次 SHEET 添加新欄位都要：
# 1. ALTER TABLE ADD COLUMN
# 2. 修改代碼添加提取邏輯
# 3. 修改 user_data 字典
```

### 新架構（5 行）
```python
# ✅ 自動提取表頭
headers = manager.get_sheet_headers(all_values)

# ✅ 自動遷移 schema
manager.ensure_db_schema(headers)

# ✅ 動態解析記錄
records = manager.parse_records(headers, data_rows)

# ✅ 同步到 DB
updated, inserted, errors = manager.sync_records(records)
```

## 實際效果

### 添加新欄位的工作流

#### 舊架構
1. SHEET 添加新列 `stamina_bonus`
2. **手動** 修改代碼添加 `stamina_bonus = to_int(row.get('stamina_bonus', 0))`
3. **手動** 修改 `user_data` 字典添加 `'stamina_bonus': stamina_bonus`
4. **手動** 執行 `ALTER TABLE users ADD COLUMN stamina_bonus INTEGER DEFAULT 0`
5. **重啟** bot

#### 新架構
1. SHEET 添加新列 `stamina_bonus`
2. **無需修改代碼**
3. 下次同步時自動：
   - 從 SHEET 第 2 行讀取新欄位
   - 自動執行 `ALTER TABLE ADD COLUMN stamina_bonus TEXT`
   - 自動同步數據

**結果：完全自動化，零額外工作** ✅

## 配置

### 修改欄位類型（如需要）
編輯 `sheet_sync_manager.py` 中的 `FIELD_TYPES`：
```python
FIELD_TYPES = {
    'user_id': 'INTEGER PRIMARY KEY',
    'stamina_bonus': 'INTEGER DEFAULT 0',  # 新增自動類型
    'title': 'TEXT DEFAULT "新手"',
}
```

### 排除某些欄位
編輯 `EXCLUDE_FIELDS`：
```python
EXCLUDE_FIELDS = {'nickname', 'internal_field', 'temp_field'}
# 這些欄位在 SHEET 中有但不會同步到 DB
```

## 部署步驟

1. **拉取最新代碼**
   ```bash
   git pull
   ```

2. **重啟 bot**
   ```bash
   sudo systemctl restart discord-bot.service
   ```

3. **檢查日誌**
   ```bash
   sudo journalctl -u discord-bot.service -f
   ```

4. **預期日誌輸出**
   ```
   📋 SHEET 表頭 (第 2 行，共 24 列): ['user_id', 'nickname', ...]
   🔧 檢查並自動同步 DB schema...
   ➕ 添加欄位: new_field（如有新欄位）
   ✅ 新增 1 個欄位
   📊 SHEET 數據行: 54 筆
   ✅ 解析完成: 54 筆有效記錄
   🔍 記錄 1: user_id=123456789, kkcoin=1000, level=1
   ✅ [SHEET→DB 同步] 更新=50, 新增=4, 錯誤=0
   ```

## 優勢總結

| 項目 | 舊架構 | 新架構 |
|------|-------|-------|
| **代碼行數** | 150+ | 5 |
| **添加新欄位** | ❌ 需要手動改代碼 | ✅ 自動適應 |
| **Schema 遷移** | ❌ 手動執行 SQL | ✅ 自動 ALTER TABLE |
| **維護難度** | ❌ 高 | ✅ 低 |
| **擴展性** | ❌ 差 | ✅ 優秀 |
| **錯誤風險** | ❌ 高 | ✅ 低 |
| **一勞永逸** | ❌ 否 | ✅ 是 |

## 未來改進

1. **版本控制**：記錄 schema 變化歷史
2. **欄位驗證**：在同步前驗證數據完整性
3. **回滾功能**：支持同步失敗自動回滾
4. **性能優化**：批量同步大量記錄時的性能優化

---

**部署日期**: 2026-02-05  
**版本**: 1.0 (SHEET 主導架構)  
**狀態**: ✅ 生產就緒
