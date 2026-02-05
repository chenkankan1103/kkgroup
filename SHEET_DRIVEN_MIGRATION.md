# Sheet-Driven 數據庫系統 - 完整遷移指南

## 📋 概述

新的 Sheet-Driven 數據庫系統將 **Google Sheet 作為真實來源** (Row 1 = 欄位定義)，數據庫自動適應 Sheet 的結構。這樣可以：

✅ **無需改代碼即可添加新欄位** - 在 Sheet 中添加欄位，系統自動同步
✅ **消除格式不一致問題** - DB 結構總是與 Sheet 一致
✅ **支持任意欄位名稱** - 無硬編碼的字段列表

---

## 🔧 核心組件

### 1. **sheet_driven_db.py** - 底層 DB 引擎

完整的 Sheet 驅動數據庫實現，提供：
- 自動 schema 適應
- 動態欄位添加
- 類型轉換推測
- JSON 導入/導出

```python
from sheet_driven_db import SheetDrivenDB

db = SheetDrivenDB('user_data.db')

# 讀取用戶
user = db.get_user(123456789)

# 更新用戶
db.set_user(123456789, {'level': 10, 'xp': 5000})

# 同步 Sheet
db.sync_from_sheet(headers, rows)
```

### 2. **sheet_sync_manager.py** - 同步管理層

Sheet 解析和同步的高級接口：

```python
from sheet_sync_manager import SheetSyncManager

manager = SheetSyncManager('user_data.db')

# 從 Sheet 同步
stats = manager.sync_sheet_to_db(headers, rows)

# 查詢用戶
user = manager.get_user(user_id)
manager.set_user_field(user_id, 'kkcoin', 5000)
```

### 3. **db_adapter.py** - 統一適配層 (推薦使用)

所有命令文件應使用這層，提供：
- 簡單的函數接口
- 向後相容性
- 自動 Sheet 格式轉換

```python
from db_adapter import get_user_field, set_user_field, add_user_field

# 這些是最常用的函數
kkcoin = get_user_field(user_id, 'kkcoin', default=0)
set_user_field(user_id, 'kkcoin', 5000)
add_user_field(user_id, 'kkcoin', 100)  # 增加
```

### 4. **sheet_sync_api.py** - Flask API

REST 接口，支持 Apps Script 調用和客戶端查詢。

---

## 🔄 遷移步驟

### 步驟 1: 備份現有數據

```python
from sheet_sync_manager import SheetSyncManager

manager = SheetSyncManager('user_data.db')

# 導出為 JSON (可選備份)
manager.export_to_json('user_data_backup.json')
```

### 步驟 2: 驗證 Sheet 結構

確保 Sheet 的 Row 1 包含所有欄位名稱：
```
user_id  |  nickname  |  level  |  xp  |  kkcoin  |  title  |  hp  |  stamina  |  ...
```

### 步驟 3: 第一次同步

```python
from sheet_sync_manager import SheetSyncManager

manager = SheetSyncManager('user_data.db')

# 假設你已經從 Sheet 讀取數據
headers = ['user_id', 'nickname', 'level', 'xp', 'kkcoin', ...]
rows = [[123456789, 'Player1', 5, 1000, 5000, ...], ...]

# 同步到 DB（自動創建表和欄位）
stats = manager.sync_sheet_to_db(headers, rows)
print(f"插入: {stats['inserted']}, 更新: {stats['updated']}, 錯誤: {stats['errors']}")
```

### 步驟 4: 遷移舊代碼

#### ❌ 舊方式 (直接 sqlite3)
```python
import sqlite3

conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()
cursor.execute("SELECT kkcoin FROM users WHERE user_id = ?", (user_id,))
result = cursor.fetchone()
kkcoin = result[0] if result else 0
```

#### ✅ 新方式 (使用適配層)
```python
from db_adapter import get_user_field

kkcoin = get_user_field(user_id, 'kkcoin', default=0)
```

---

## 📝 常見用法示例

### 獲取用戶資料

```python
from db_adapter import get_user, get_user_field

# 獲取完整用戶資料
user = get_user(user_id)
print(user)  # {'user_id': ..., 'nickname': ..., 'level': ..., ...}

# 獲取特定欄位
kkcoin = get_user_field(user_id, 'kkcoin', default=0)
level = get_user_field(user_id, 'level', default=1)
```

### 更新用戶資料

```python
from db_adapter import set_user_field, add_user_field

# 直接設置
set_user_field(user_id, 'title', '武士')

# 增加/減少
add_user_field(user_id, 'kkcoin', 100)   # 增加 100 kkcoin
add_user_field(user_id, 'xp', 50)        # 增加 50 xp
add_user_field(user_id, 'kkcoin', -50)   # 減少 50 kkcoin
```

### 裝備系統 (shop_commands 適用)

```python
from db_adapter import get_user_equipment, update_user_equipment

# 獲取所有裝備
equipment = get_user_equipment(user_id)
# {'face': 20000, 'hair': 30000, 'skin': 12000, 'top': ..., 'bottom': ..., 'shoes': ...}

# 更新裝備
update_user_equipment(user_id, 'face', 20001)
```

### 批量操作

```python
from db_adapter import get_all_users, batch_set_users

# 獲取所有用戶
all_users = get_all_users(limit=100)

# 批量更新
updates = {
    user_id_1: {'level': 10, 'title': '武士'},
    user_id_2: {'level': 5, 'title': '新手'},
}
batch_set_users(updates)
```

---

## 🚀 API 端點使用

### 同步 Sheet 數據
```bash
curl -X POST http://localhost:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{
    "headers": ["user_id", "nickname", "level", "kkcoin"],
    "rows": [
      ["123456789", "Player1", "5", "1000"],
      ["987654321", "Player2", "3", "500"]
    ]
  }'
```

### 獲取用戶資料
```bash
curl http://localhost:5000/api/user/123456789
```

### 更新用戶欄位
```bash
curl -X PUT http://localhost:5000/api/user/123456789/kkcoin \
  -H "Content-Type: application/json" \
  -d '{"value": 5000}'
```

### 增加用戶欄位
```bash
curl -X POST http://localhost:5000/api/user/123456789/kkcoin/add \
  -H "Content-Type: application/json" \
  -d '{"amount": 100}'
```

---

## 📊 DB 統計

```python
from db_adapter import get_db_stats, count_users

stats = get_db_stats()
print(f"用戶總數: {stats['total_users']}")
print(f"欄位數: {stats['total_columns']}")
print(f"所有欄位: {stats['columns']}")
```

---

## ⚠️ 注意事項

1. **虛擬帳號**: 系統自動跳過 `nickname` 為 `Unknown_*` 的帳號
2. **類型推測**: 系統根據欄位名推測類型 (如 `kkcoin` → 整數，`title` → 文本)
3. **向後相容**: 所有舊函數仍可使用 (通過 `db_adapter.py`)
4. **JSON 字段**: 複雜結構 (`config`, `inventory` 等) 自動存為 JSON 文本

---

## 🔄 文件改寫清單

需要改寫的文件 (使用 `db_adapter` 替換舊代碼):

- [ ] `commands/kcoin.py` - 貨幣系統
- [ ] `commands/jail.py` - 監獄系統  
- [ ] `commands/work_function/database.py` - 工作系統
- [ ] `shop_commands/merchant/database.py` - 商人系統
- [ ] `uicommands/welcome_message.py` - UI 歡迎訊息
- [ ] `verify_user_id.py` - ID 驗證
- [ ] 任何其他直接使用 `sqlite3` 的文件

**替換模式:**
```python
# ❌ 舊
import sqlite3
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()
cursor.execute(...)

# ✅ 新
from db_adapter import get_user_field, set_user_field, add_user_field
value = get_user_field(user_id, 'field_name')
```

---

## ✅ 驗證清單

遷移完成後，請驗證：

- [ ] 所有新欄位自動添加到 DB (無需代碼修改)
- [ ] 手動在 Sheet 添加新欄位，同步成功
- [ ] 所有指令正常運作
- [ ] 用戶資料正確保存和讀取
- [ ] API 端點全部可用
- [ ] 統計資訊正確

---

## 📞 故障排除

### 問題：同步時說找不到 user_id
**解決**：系統會自動偵測 user_id 欄位。確保第一列包含有效的 Discord ID (18-20 位數字)

### 問題：新欄位添加不成功
**解決**：確保：
1. Sheet Row 1 包含新欄位名稱
2. 等待同步完成
3. 檢查 `/api/stats` 確認欄位已添加

### 問題：舊代碼無法執行
**解決**：所有舊函數都通過 `db_adapter.py` 提供相容版本。確保 import 使用的是 `db_adapter` 而非直接操作 sqlite3。

---

## 📚 更多資訊

- 核心引擎: `sheet_driven_db.py`
- 同步管理: `sheet_sync_manager.py`  
- API 文檔: 啟動 `sheet_sync_api.py` 後訪問 `http://localhost:5000`
