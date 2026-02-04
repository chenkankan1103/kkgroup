# SHEET → DB 同步修復部署指南

## 📋 已完成的改進

### 1. 科學記號支援 ✅
- `_to_int()` 方法現在能正確處理 `4.98503E+17` 等科學記號格式
- 自動轉換為正確的整數値

### 2. 自動偵測 user_id 欄位 ✅
- 當 SHEET 表頭缺少明確的 `user_id` 欄位時，自動偵測（例如「第 1 欄」）
- 使用啟發式方法識別最可能是 user_id 的欄位

### 3. 虛擬帳號處理 ✅
- 自動跳過 nickname 為 `Unknown_XXXX` 的虛擬帳號
- 新增清理工具 `cleanup_virtual_accounts.py`

### 4. Nickname 存儲 ✅
- 將 nickname 從排除列表移除，現在被存儲到 DB 中
- 便於追蹤虛擬帳號和後續管理

## 🚀 部署步驟

### 步驟 1: 更新生產環境代碼
```bash
cd /path/to/kkgroup
git pull
```

### 步驟 2: 重啟 Discord 機器人
```bash
# 根據你的設定選擇：
systemctl restart discord-bot
# 或
supervisorctl restart discord-bot
# 或其他重啟方式
```

### 步驟 3: 驗證同步
1. 檢查日誌中是否出現新訊息：
   - `📊 將科學記號轉換: XXX → YYY`
   - `✅ 找到 'user_id' 欄位在表頭中`
   - `⏭️ 行 X 跳過: 虛擬帳號 (Unknown_XXXX)`

2. 確認 user_data.db 包含 nickname 欄位（如有 DB 損壞可重建）

### 步驟 4: 清理虛擬帳號（可選）
```bash
# 查看檢測到的虛擬帳號（不删除）
python cleanup_virtual_accounts.py
# 提示後輸入 yes 確認刪除

# 或強制執行（跳過確認）
python cleanup_virtual_accounts.py --force
```

## 📊 預期結果

部署後，SHEET 中的資料應該正確同步到 DB：
- ✅ 科學記號的 user_id 正確轉換
- ✅ 虛擬帳號被自動過濾
- ✅ 真實玩家資料完整同步
- ✅ 可選清理虛擬帳號記錄

## 📝 核心修改

### `sheet_sync_manager.py`
- `_to_int()`: 增強科學記號處理
- `parse_records()`: 新增虛擬帳號檢查和偵測邏輯
- `_detect_user_id_col()`: 啟發式欄位偵測
- `clean_virtual_accounts()`: 清理虛擬帳號方法
- `EXCLUDE_FIELDS`: 移除 nickname，改為存儲

### `cleanup_virtual_accounts.py` (新檔案)
- 獨立清理工具
- 支援 `--force` 跳過確認

## 🔧 故障排除

### 問題：仍看到「user_id 無效」訊息
- 確認機器人是否已重啟並加載新代碼
- 檢查 SHEET 中 user_id 欄位是否確實包含有效的大整數

### 問題：DB 結構不對
- 備份舊 `user_data.db`
- 刪除 `user_data.db`
- 重啟機器人，讓它自動重建 DB 並重新同步

### 問題：虛擬帳號仍未清理
- 執行 `python cleanup_virtual_accounts.py --force`
