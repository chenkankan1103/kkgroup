# 🔄 SHEET 同步修復部署指南

## 問題摘要

Discord Bot 的舊自動同步循環（每 1 分鐘執行）干擾了新的 Flask API + Google Apps Script 方案。當用戶點擊 Apps Script 的「同步」按鈕時，資料格式不對導致同步失敗。

### 根本原因
1. **舊自動同步循環仍在運行** - `google_sheets_sync.py` 的 `auto_sync_loop` 和 `auto_export_loop` 每分鐘執行
2. **Apps Script 數據格式問題** - 表頭行可能包含空欄位或列標題，導致數據行對齊錯誤
3. **字段名被當作數據** - `user_id` 等字段名被誤認為是實際的用戶 ID 數據

## ✅ 已完成的修復

### 1. 停用 Discord Bot 自動同步循環
**文件**: `commands/google_sheets_sync.py`

```python
# 已修改 __init__ 方法：註釋掉以下行
# if not self.auto_sync_loop.is_running():
#     self.auto_sync_loop.start()
# if not self.auto_export_loop.is_running():
#     self.auto_export_loop.start()
```

✅ **效果**: 不再有每 1 分鐘和 5 分鐘的自動同步，避免干擾

---

### 2. 改進 Apps Script 數據過濾邏輯
**文件**: `SHEET_SYNC_APPS_SCRIPT.gs`

**改進內容**:
- ✅ 正確識別 Row 2 (allData[1]) 作為表頭
- ✅ 正確過濾空欄位，但保持列對齐
- ✅ 過濾空行和無效記錄
- ✅ 詳細的日誌輸出便於調試

**關鍵邏輯**:
```javascript
// Row 2 = 表頭
const headers = headerRowRaw.filter(h => h && h.toString().trim() !== '');

// Row 3+ = 資料，按照表頭數量對齐
const rows = dataRowsRaw
  .filter(row => row.some(cell => cell && cell.toString().trim() !== ''))  // 移除空行
  .map(row => row.slice(0, headers.length));  // 截斷到表頭長度
```

✅ **效果**: 確保傳送給 API 的數據格式正確

---

### 3. 強化 Python API 字段名過濾
**文件**: `sheet_sync_manager.py` - `_to_int()` 方法

```python
def _to_int(self, val):
    # ... 前面的邏輯 ...
    
    # ⚠️ 過濾掉表頭字符串（例如 "user_id", "nickname" 等）
    if val_str.isalpha() or '_' in val_str:
        # 可能是欄位名稱而非數據
        return 0
```

✅ **效果**: 即使字段名漏過了 Apps Script 的過濾，也會在 Python 端被識別為無效

---

## 📋 部署步驟

### **A. 在 GCP 上部署更新的代碼** (必須)

1. **SSH 連接到 GCP 實例**:
   ```bash
   gcloud compute ssh your-instance-name --zone=your-zone
   cd /path/to/kkgroup
   ```

2. **更新代碼** (使用 git 或手動上傳):
   ```bash
   git pull origin main
   # 或手動複製更新的文件：
   # - commands/google_sheets_sync.py
   # - sheet_sync_manager.py
   # - sheet_sync_api.py
   ```

3. **重啟 Flask API 服務**:
   ```bash
   # 如果使用 Supervisor
   sudo supervisorctl restart sheet-sync-api
   
   # 或手動運行
   source venv/bin/activate
   python sheet_sync_api.py &
   ```

4. **驗證服務狀態**:
   ```bash
   curl http://localhost:5000/api/health
   # 應返回: {"status": "ok", "message": "API 健康", ...}
   ```

5. **重啟 Discord Bot** (可選，如果 Bot 在同一實例上):
   ```bash
   # 停止舊進程
   pkill -f "python.*bot.py"
   
   # 啟動新 Bot
   python bot.py &
   ```

---

### **B. 在 Google Sheets 中部署新的 Apps Script** (必須)

1. **打開 Google Sheets** - 「玩家資料」工作表
   
2. **打開 Apps Script 編輯器**:
   - 選擇 「擴充功能」→ 「Apps Script」

3. **刪除舊代碼，複製新的代碼**:
   - 從 [SHEET_SYNC_APPS_SCRIPT.gs](./SHEET_SYNC_APPS_SCRIPT.gs) 複製全部代碼
   - 貼到編輯器中

4. **修改 API_ENDPOINT**:
   ```javascript
   const API_ENDPOINT = "http://YOUR_GCP_IP:5000";
   // 例如: "http://34.151.123.45:5000"
   ```
   - 替換為你的 GCP Compute Engine 實例的外部 IP 地址

5. **保存項目**:
   - 按 Ctrl+S 或 Cmd+S
   - 或點擊「💾 保存」按鈕

6. **刷新 Google Sheets 頁面**:
   - F5 或 Cmd+R
   - 應該看到「🔄 同步工具」菜單

---

## 🧪 測試步驟

### **Step 1: 驗證 API 連接**

1. 在 Google Sheets 中，點擊 「🔄 同步工具」→ 「✅ 檢查 API 連接」
2. 應該看到: 
   ```
   ✅ API 連接正常
   訊息: API 健康
   時間: 2024-XX-XX XX:XX:XX
   ```
3. 如果失敗，檢查：
   - GCP 防火牆是否開放 TCP 5000
   - Flask API 是否正在運行: `curl http://your-ip:5000/api/health`
   - API_ENDPOINT 是否正確

---

### **Step 2: 驗證表頭識別**

1. 在 Google Sheets 中，手動編輯一筆玩家數據（例如增加 kkcoin）
2. 點擊 「🔄 同步工具」→ 「📤 同步到資料庫」
3. 檢查 Google Apps Script 的日誌 (按 Ctrl+Enter 打開執行日誌):
   ```
   ✅ 表頭已識別 (X 列): user_id, nickname, level, ...
   🔍 完整表頭: ["user_id", "nickname", ...]
   📊 資料行過濾完成: X 筆有效記錄
   📝 第 1 筆資料: ["123456789", "玩家名", ...]
   🔍 第 1 筆資料的第 1 列值: "123456789" (是否數字: true)
   ```

4. **重要檢查點**:
   - ✅ 表頭是否正確（不是「第 1 欄」、「第 2 欄」）
   - ✅ 第 1 筆資料的第 1 列是否是數字（user_id）
   - ✅ 是否顯示「是否數字: true」

---

### **Step 3: 檢查 Flask API 日誌**

在 GCP 實例上，監控 Flask API 日誌：

```bash
# 如果使用 Supervisor
tail -f /var/log/sheet-sync-api.log

# 或查看 Flask 直接輸出
python sheet_sync_api.py
```

**期望日誌輸出**:
```
📥 收到同步請求
✅ 表頭 (6 列): ['user_id', 'nickname', 'level', 'xp', 'kkcoin', 'title']
📊 解析 X 筆記錄
✅ 檢查 DB schema...
📝 記錄 1: user_id=123456789, nickname=玩家名, ...
✅ 記錄有效，準備插入/更新
📊 同步完成: 更新 X 筆, 新增 Y 筆, 錯誤 Z 筆
```

**常見錯誤**:
- ❌ `⚠️ 無法轉換: user_id` → 表頭還是被當作數據
- ❌ `❌ user_id 無效` → 數據格式問題

---

### **Step 4: 驗證數據庫更新**

1. 在 GCP 實例上，檢查數據庫：
   ```bash
   sqlite3 user_data.db
   SELECT COUNT(*) FROM users;  -- 應該看到玩家記錄數
   SELECT user_id, nickname, kkcoin FROM users LIMIT 3;  -- 檢查數據
   ```

2. 驗證你在 SHEET 中編輯的數據是否已保存到數據庫

---

## 🐛 故障排查

| 問題 | 原因 | 解決方案 |
|------|------|---------|
| ❌ 「無法連接到 API」 | API_ENDPOINT 錯誤或 Flask 未運行 | 1. 檢查 GCP IP; 2. 檢查防火牆; 3. 重啟 Flask |
| ❌ 「表頭為 '第 1 欄', '第 2 欄'...」 | Apps Script 代碼未更新 | 複製最新的 SHEET_SYNC_APPS_SCRIPT.gs 代碼 |
| ❌ 「無法轉換: user_id」 | 表頭被當作數據行 | Apps Script 過濾邏輯有問題，檢查日誌 |
| ✅ API 成功但數據未更新 | 數據行開始位置錯誤 | 檢查 Apps Script 日誌中的「第 1 筆資料」 |

---

## 📊 驗證清單

- [ ] Discord Bot 的 `auto_sync_loop` 已停用
- [ ] GCP 上的 Flask API 已更新並運行
- [ ] Google Sheets 的 Apps Script 已更新
- [ ] Apps Script 的 `API_ENDPOINT` 已改為正確的 GCP IP
- [ ] GCP 防火牆允許 TCP 5000 入站流量
- [ ] API 連接檢查 ✅ 通過
- [ ] 表頭識別正確（不是列標題）
- [ ] 第 1 筆資料的第 1 列是數字
- [ ] Flask API 日誌顯示成功同步
- [ ] 數據庫中的數據已更新

---

## 📞 後續支持

如果部署後仍有問題，請檢查：

1. **Google Apps Script 日誌** (Ctrl+Enter):
   - 查看完整的日誌消息，特別是表頭和第 1 筆資料的輸出

2. **Flask API 日誌**:
   - 查看 GCP 日誌中 API 收到的實際數據結構

3. **數據庫驗證**:
   ```bash
   sqlite3 user_data.db ".tables"  -- 查看表
   sqlite3 user_data.db ".schema users"  -- 查看 users 表結構
   ```

---

## 📝 版本歷史

| 版本 | 日期 | 變更 |
|------|------|------|
| 1.0 | 2024 | 初版 - 停用舊同步循環，改進 Apps Script 和 Python 過濾 |

