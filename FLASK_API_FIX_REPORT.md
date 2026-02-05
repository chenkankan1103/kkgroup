# GCP Flask API 修復總結

## 🔴 問題診斷

### 症狀
```
❌ gunicorn 進程已退出（Exit 1）
❌ 5000 端口無響應
❌ Apps Script 收到 JSON 解析錯誤（<!doctype...）
```

### 根本原因
在 `sheet_sync_api.py` 的頂級代碼中，進行了**同步初始化**：

```python
# ❌ 舊代碼（會在模塊導入時執行）
sync_manager = SheetSyncManager('user_data.db')
db = SheetDrivenDB('user_data.db')
```

當 gunicorn 匯入模塊時：
1. 如果 user_data.db 有任何問題（損壞、鎖定、權限等）
2. SheetDrivenDB 初始化會失敗
3. gunicorn 無法完成導入，進程立即退出
4. 用戶端收到 HTML 500 錯誤而非 JSON

---

## ✅ 解決方案

### 方案 1：延遲初始化（已實施）

改為**延遲初始化**（Lazy Initialization）：

```python
# ✅ 新代碼（只在首次使用時初始化）
_sync_manager = None
_db = None

def get_sync_manager():
    """獲取同步管理器（延遲初始化）"""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SheetSyncManager('user_data.db')
    return _sync_manager

def get_db():
    """獲取數據庫引擎（延遲初始化）"""
    global _db
    if _db is None:
        _db = SheetDrivenDB('user_data.db')
    return _db
```

所有引用改為：
```python
# ✅ 改為通過 getter 函數
get_sync_manager().ensure_db_schema(headers)
get_db().get_user(user_id)
```

### 優點
✅ gunicorn 可以成功導入模塊  
✅ 應用啟動時不會因 DB 初始化失敗而退出  
✅ 首個 API 請求時才初始化（此時會顯示真實錯誤）  
✅ 錯誤被正確返回為 JSON（通過異常處理器）

---

## 🔧 修復步驟（GCP）

### 1. 等待自動部署（2-3 分鐘）

新代碼已推送到 GitHub，GCP 應自動拉取。

### 2. 手動重啟 Flask API

```bash
cd ~/kkgroup
chmod +x restart_flask_api.sh
./restart_flask_api.sh
```

此腳本會：
- 拉取最新代碼
- 檢查 Python 語法
- 停止舊的 gunicorn
- 啟動新的 gunicorn
- 驗證 /api/health 端點

### 3. 驗證修復

```bash
# 檢查 gunicorn 進程
ps aux | grep gunicorn

# 測試 API
curl http://localhost:5000/api/health

# 查看實時日誌
tail -f gunicorn.log
```

### 4. 如果仍有問題

執行診斷指令：

```bash
chmod +x diagnose_startup.sh
./diagnose_startup.sh
```

此指令會逐步檢查：
1. Python 語法
2. 模塊導入
3. Flask 啟動
4. gunicorn 詳細錯誤

---

## 📊 修改文件列表

| 文件 | 修改內容 |
|------|--------|
| sheet_sync_api.py | 改為延遲初始化 + 所有 getter 呼叫 |
| diagnose_startup.sh | 新增：啟動錯誤診斷工具 |
| test_flask_simple.py | 新增：簡化版 Flask 測試 |
| restart_flask_api.sh | 新增：GCP 重啟腳本（此文件） |

---

## 📈 預期結果

修復後：

✅ gunicorn 成功啟動  
✅ 5000 端口正常監聽  
✅ /api/health 返回 JSON  
✅ /api/sync 可正常同步  
✅ Apps Script 收到正確的 JSON 回應  
✅ Discord Bot 工作正常（如果連接 API）

---

## 🆘 常見問題

### Q: 仍然收到 "連接被拒絕"
**A:** gunicorn 可能還未成功啟動，等 5-10 秒後重試。  
檢查日誌：`tail -50 gunicorn.log | grep -i error`

### Q: 5000 端口被佔用
**A:** 殺死占用進程：  
```bash
lsof -i :5000 | awk 'NR!=1 {print $2}' | xargs kill -9
```

### Q: User_data.db 損壞
**A:** 可以暫時刪除並讓系統重建：  
```bash
# 備份
cp user_data.db user_data.db.backup
# 刪除
rm user_data.db
# 下次 API 呼叫時會自動創建新的
```

### Q: Python 模塊缺失
**A:** 確保已安裝依賴：  
```bash
pip install flask gspread oauth2client google-auth-oauthlib
```

---

## 📝 技術細節

### 為什麼選擇延遲初始化？

| 方案 | 優點 | 缺點 |
|------|------|------|
| **同步初始化（舊）** | 簡單 | gunicorn 啟動時失敗 |
| **延遲初始化（新）** | ✅ gunicorn 啟動快速 | 首次請求時略有延遲 |
| **Connection Pool** | 資源管理佳 | 複雜度高 |

選擇延遲初始化是因為：
1. gunicorn 啟動立即成功
2. 錯誤在 API 層被正確處理
3. 實現簡單，改動最小

---

## 🚀 後續優化

可以考慮的改進：

1. **添加應用程序初始化事件**
   ```python
   @app.before_first_request
   def init_resources():
       get_sync_manager()
       get_db()
   ```

2. **Connection pooling**
   ```python
   # 使用連接池管理數據庫連接
   ```

3. **Healthcheck 端點改進**
   ```python
   @app.route('/api/health/detailed')
   def health_detailed():
       return {
           'app': 'ok',
           'db': check_db_health(),
           'sheets': check_sheets_health()
       }
   ```

---

## ✍️ 修復者備註

**commit**: 07e542e  
**日期**: 2026-02-05  
**修復内容**:
- Sheet-Driven DB 延遲初始化
- 所有 API 端點改用 getter 函數
- 全局異常處理確保 JSON 返回
- 新增診斷和重啟工具

修復後系統應恢復正常運行。如有問題，執行 `diagnose_startup.sh` 診斷。
