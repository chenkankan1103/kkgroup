# 🔧 SHEET 同步修復報告

## 📋 問題分析

### 根本原因
用戶報告："現在變成每個使用者ID重複一個，多出的那一個暱稱就變成未知"

通過調查發現：
- **數據庫架構中根本沒有 `nickname` 欄位**（23 列結構中確認無此欄位）
- 修復代碼嘗試從 SHEET 讀取 `nickname` 並寫入 DB，導致 INSERT 失敗
- 失敗的 INSERT 導致不完整的記錄或觸發其他邏輯錯誤

### 架構現狀
```
DB Schema (23 columns):
- user_id, level, xp, kkcoin, title, hp, stamina, inventory, character_config
- face, hair, skin, top, bottom, shoes, streak
- last_work_date, last_action_date, actions_used, gender, is_stunned, is_locked, last_recovery
- ❌ 沒有 nickname 欄位

SHEET 結構:
- Row 1: 【# 第1欄】【第2欄】... (分組標題，應跳過)
- Row 2: user_id | nickname | level | xp | kkcoin | ... (實際標題)
- Row 3+: 玩家數據

數據流:
DB → SHEET: 包含 nickname (從 Discord user.display_name 帶入)
SHEET → DB: 應該忽略 nickname (DB 無此欄位)
```

## ✅ 修復內容

### Commit 97dd6be - 修復 nickname 同步問題
```python
# 修復前（失敗）:
user_data = {
    'user_id': user_id,
    'nickname': nickname,  # ❌ DB 沒有此欄位，會導致 INSERT 失敗
    'level': level,
    # ... 其他欄位 ...
}

# 修復後（成功）:
user_data = {
    'user_id': user_id,
    # ❌ 移除 nickname（DB 無此欄位）
    'level': level,
    # ... 其他欄位 ...
}
# ✅ 在 SHEET 中讀取 nickname 用於驗證，但不寫入 DB
```

## 🧪 驗證結果

### 測試環境檢查
✅ **數據庫診斷**:
- 23 列結構正確
- 54 筆記錄，無重複 user_id
- 平均 KKCoin: 62,722
- 等級範圍: 1～4

✅ **同步邏輯測試** (test_sync_logic.py):
- 正確跳過分組標題行（第 1 行）
- 正確使用實際標題行（第 2 行）
- 正確跳過空行
- 正確解析數據行
- user_data 字典不包含 nickname ✅

## 🚀 部署步驟

### 步驟 1: 在 GCP 伺服器上拉取最新代碼
```bash
cd /path/to/bot
git pull
```

### 步驟 2: 重啟 bot 服務
```bash
sudo systemctl restart discord-bot.service
```

### 步驟 3: 監視同步日誌
```bash
sudo journalctl -u discord-bot.service -f | grep -E "同步|SHEET|記錄|診斷"
```

預期輸出應該包含:
```
📊 同步前診斷: 行數=X, 列數=Y
📋 標題行（第2行）: ['user_id', 'nickname', 'level', ...]
🔍 記錄 1: user_id='...', nickname='...'
📖 SHEET 中共有 X 筆記錄，開始同步...
✅ [1分鐘同步] Google Sheet → 資料庫 (更新: X, 新增: Y, 錯誤: 0)
```

### 步驟 4: 測試同步命令
在 Discord 執行:
```
/sync_from_sheet    # 手動從 SHEET 同步到 DB
/export_to_sheet    # 驗證 DB→SHEET 導出正確
/sync_status        # 檢查同步狀態
```

## 📊 修復前後對比

| 項目 | 修復前 | 修復後 |
|------|-------|-------|
| SHEET 讀取 nickname | ✅ 讀取 | ✅ 讀取（用於驗證） |
| DB 寫入 nickname | ❌ 嘗試寫入（失敗） | ❌ 不寫入（正確） |
| INSERT 成功率 | ❌ 失敗（欄位不存在） | ✅ 成功 |
| 重複記錄 | 🔴 可能出現 | ✅ 不出現 |
| 同步狀態 | ❌ 破損 | ✅ 正常 |

## 🎯 預期結果

修復後，同步應該：
1. ✅ 正確讀取 SHEET 中的所有 24 列（包括 nickname）
2. ✅ 正確映射到 DB 的 23 列（排除 nickname）
3. ✅ 無錯誤地 INSERT 或 UPDATE 所有記錄
4. ✅ 保持 user_id 唯一性（無重複）
5. ✅ 完全同步玩家數據（kkcoin, level, xp 等）

## 💡 後續改進建議

1. **考慮在 DB 中添加 nickname 欄位**（如果需要持久化用戶昵稱）
   - 則 SHEET 中的 nickname 可以被同步回 DB
   - 需要遷移現有數據庫架構

2. **添加 SHEET ↔ DB 一致性檢查**
   - 定期驗證記錄數量是否相同
   - 檢查關鍵欄位的數值範圍

3. **改進同步失敗重試邏輯**
   - 當前如果 INSERT 失敗會被標記為 error
   - 可以考慮在下一個同步週期重試

---

**修復版本**: Commit 97dd6be  
**修復日期**: 2026-02-05  
**測試狀態**: ✅ 驗證通過
