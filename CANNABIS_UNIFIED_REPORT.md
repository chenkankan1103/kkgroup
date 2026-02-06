# 🔄 大麻系統統一遷移 - 完整報告
**遷移日期**: 2026-02-10  
**狀態**: ✅ 代碼修改完成 (功能驗收中)

---

## 📊 遷移概述

### 目標
🎯 **統一大麻系統到單一數據庫**
- ❌ 刪除獨立的 `cannabis_plants` 表
- ❌ 刪除獨立的 `cannabis_inventory` 表  
- ✅ 添加 JSON 欄位到 `users` 表
- ✅ 轉換所有操作到適配器層
- ✅ 移除後台表創建任務

### 完成度

| 項目 | 狀態 | 說明 |
|------|------|------|
| 數據庫統一 | ✅ | 2 個獨立表已刪除, users 表已添加 JSON 欄位 |
| 適配器層 | ✅ | cannabis_unified.py 已創建 |
| cannabis_farming.py | ✅ | 所有函數已改用適配器層 |
| cannabis_cog.py | ✅ | 後台任務已禁用 |
| cannabis_locker.py | ✅ | 無需修改 (使用公開 API) |
| 語法檢查 | ✅ | 所有 Python 文件檢查通過 |

---

## 📝 修改詳情

### 1. 新增文件: `cannabis_unified.py`
```python
# 位置: shop_commands/merchant/cannabis_unified.py
# 功能: 
#   - CannabisFarmingAdapter 類 - 統一的大麻操作適配器
#   - 將同步 SheetDrivenDB 操作包裝為異步
#   - 自動 JSON 序列化/反序列化
#   - 公開 API:
#     - add_plant(), get_user_plants(), update_plant(), remove_plant()
#     - add_inventory(), remove_inventory(), get_inventory()
#     - get_all_user_plants() [管理用]
```

### 2. 修改文件: `cannabis_farming.py`
所有函數已改為使用適配器層:

| 函數名 | 修改 | 詳情 |
|-------|------|------|
| `init_cannabis_tables()` | ✅ | 廢棄 - 現為空函數 |
| `add_inventory()` | ✅ | 使用 adapter.add_inventory() |
| `remove_inventory()` | ✅ | 使用 adapter.remove_inventory() |
| `get_inventory()` | ✅ | 使用 adapter.get_inventory() |
| `plant_cannabis()` | ✅ | 使用 adapter.add_plant() |
| `get_user_plants()` | ✅ | 使用 adapter.get_user_plants() |
| `apply_fertilizer()` | ✅ | 使用 adapter.update_plant() |
| `harvest_plant()` | ✅ | 使用 adapter.update_plant() + adapter.add_inventory() |
| `sell_cannabis()` | ✅ | 使用 remove_inventory() |

**移除的導入**:
- ✅ `import aiosqlite` (已移除)
- ✅ 直接 SQL 執行 (已移除)

**保留的導入**:
- ✅ `from .cannabis_unified import get_adapter` (新增)

### 3. 修改文件: `cannabis_cog.py`
```python
# 修改:
#   - 廢棄 init_cannabis_tables_bg 後台任務 (第 19-36 行)
#   - 改為註釋保留供參考
#   - 移除 self.init_cannabis_tables_bg.start() 和 .cancel()

狀態: ✅ 已廢棄後台任務
日期: 2026-02-10
```

### 4. 不需要修改: `cannabis_locker.py`
✅ 已驗證無需修改 - 使用的是公開 API，在適配器層修改後仍可正常工作

---

## 🗄️ 數據庫架構 (現在)

```
SQLite Database: user_data.db
├─ users (主表)
│  ├─ user_id (INTEGER PRIMARY KEY)
│  ├─ ... (原有 33 個欄位)
│  ├─ cannabis_plants (TEXT) ← JSON 陣列
│  │   格式: [{"id": 1, "seed_type": "常規種", "status": "growing", ...}]
│  ├─ cannabis_inventory (TEXT) ← JSON 物件
│  │   格式: {"種子": {"常規種": 3}, "大麻": {"優質種": 5}}
│  └─ _created_at, _updated_at
├─ event_history (不受影響)
├─ image_cache (不受影響)
├─ game_users (不受影響)
├─ ... (其他非 cannabis 表)
└─ ❌ NO cannabis_plants, cannabis_inventory 獨立表

總用戶: 246 (13 原始 + 233 新用戶)
```

---

## 🔄 數據操作流程 (現在)

### 添加庫存示例
```
舊方式 (已廢棄):
  User Call → cannabis_farming.add_inventory() 
    → aiosqlite.execute("INSERT INTO cannabis_inventory ...")
    → 數據庫

新方式 (已實現):
  User Call → cannabis_farming.add_inventory()
    → adapter.add_inventory()
      → 讀取 user.cannabis_inventory (JSON)
      → 修改 JSON 物件
      → db.set_user_field() → users.cannabis_inventory
      → 保存到數據庫
```

### 種植示例
```
新方式:
  User Call → plant_cannabis()
    → adapter.add_plant()
      → 讀取 user.cannabis_plants (JSON)
      → 生成新 ID
      → 添加植物到 JSON 陣列
      → db.set_user_field() → users.cannabis_plants
      → 保存到數據庫
```

---

## ⚙️ 技術細節

### 線程安全性
```python
# 使用 ThreadPoolExecutor 包裝同步操作
_executor = ThreadPoolExecutor(max_workers=4)

# 每次調用 DB 操作時:
await asyncio.get_event_loop().run_in_executor(_executor, _do_operation)
```

**好處**:
- Discord.py 保持異步特性 ✅
- SheetDrivenDB 同步操作無阻塞 ✅
- 4 個線程足夠處理常見操作 ✅

### JSON 序列化
```python
# 植物存儲格式
plants: List[Dict] = [
    {
        "id": 1,
        "seed_type": "常規種",
        "guild_id": 123456789,
        "channel_id": 987654321,
        "planted_at": "2026-02-10T10:30:00",
        "matured_at": "2026-02-10T11:30:00",
        "progress": 50.0,
        "fertilizer_applied": 1,
        "status": "growing",
        "harvested_amount": 0
    }
]

# 庫存存儲格式
inventory: Dict = {
    "種子": {
        "常規種": 5,
        "優質種": 2,
        "黃金種": 1
    },
    "大麻": {
        "常規種": 8,
        "優質種": 3
    },
    "肥料": {
        "基礎肥料": 10
    }
}
```

---

## ✅ 已測試項目

| 項目 | 結果 | 備註 |
|------|------|------|
| Python 語法 | ✅ | cannabis_farming.py, cannabis_unified.py, cannabis_cog.py 全部通過 |
| 導入檢查 | ✅ | 所有 import 語句正確 |
| 後台任務移除 | ✅ | init_cannabis_tables_bg 已廢棄 |

---

## 🚀 下一步 (優先級)

### 優先級 1 (立即執行)
- [ ] **在 SSH 服務器上運行功能測試**
  ```bash
  cd /home/e193752468/kkgroup
  python3 /tmp/test_cannabis_unified.py
  ```
  測試項目:
  1. 獲取現有庫存
  2. 添加庫存 (種子)
  3. 獲取植物列表
  4. 驗證 JSON 欄位格式
  5. 移除庫存

- [ ] **在 Discord 測試大麻命令**
  - `/種植` - 購買種子
  - `/我的農場` - 查看植物
  - `/施肥` - 施肥加速
  - `/收割` - 收割植物
  - `/出售` - 出售大麻

### 優先級 2 (功能完善)
- [ ] **新用戶初始化**
  - 為新用戶初始化空的 cannabis_plants 和 cannabis_inventory
  - 或贈送初始種子 (5 個常規種)
  - 修改: users 表的初始化邏輯

- [ ] **管理員命令**
  - 驗證 get_all_user_plants() 是否正常工作
  - 測試統計功能 (總植物數、庫存統計等)

### 優先級 3 (未來改進)
- [ ] **UIBOT 置物櫃功能完善**
  - 添加用戶存在性驗證
  - 添加紙娃娃圖片顯示
  - 集成圖片 URL 動態更新

---

## ⚠️ 已知問題 & 限制

### apply_fertilizer() [中等優先級]
**問題**: 施肥時需要遍歷所有用戶來找到植物  
**影響**: 多用戶環境下性能可能不佳 (若用戶 > 10000)  
**解決方案**: 建議調用端提供 user_id 參數，改簽名為 `apply_fertilizer(user_id, plant_id, ...)`

**目前實現**:
```python
async def apply_fertilizer(plant_id: int, fertilizer_type: str) -> bool:
    adapter = get_adapter()
    users = db.get_all_users()  # ⚠️ 遍歷所有用戶
    for user in users:
        plants = await adapter.get_user_plants(user_id)
        ...
```

**改進版本** (建議):
```python
async def apply_fertilizer(user_id: int, plant_id: int, fertilizer_type: str) -> bool:
    # 直接查詢該用戶的植物，性能更優
    adapter = get_adapter()
    plants = await adapter.get_user_plants(user_id)
    for plant in plants:
        if plant.get('id') == plant_id:
            ...
```

---

## 📚 參考

### 文件位置
- `cannabis_unified.py`: `shop_commands/merchant/cannabis_unified.py`
- `cannabis_farming.py`: `shop_commands/merchant/cannabis_farming.py`
- `cannabis_cog.py`: `shop_commands/cannabis_cog.py`
- `cannabis_locker.py`: `uicommands/cannabis_locker.py`

### 公開 API
- `get_adapter()` - 獲取適配器實例
- `add_inventory(user_id, item_type, item_name, quantity)`
- `remove_inventory(user_id, item_type, item_name, quantity)`
- `get_inventory(user_id)`
- `plant_cannabis(user_id, guild_id, channel_id, seed_type)`
- `get_user_plants(user_id)`
- `apply_fertilizer(plant_id, fertilizer_type)` ⚠️ 待改進
- `harvest_plant(plant_id)`
- `sell_cannabis(user_id, seed_type, quantity)`

---

## 🎉 統一完成清單

- ✅ 數據庫統一到 users 表
- ✅ 適配器層完成
- ✅ cannabis_farming.py 改寫完成
- ✅ cannabis_cog.py 後台任務移除
- ✅ 所有文件語法檢查通過
- ⏳ 完整功能測試 (待執行)
- ⏳ Discord 命令測試 (待執行)
- ⏳ apply_fertilizer() 性能優化 (待決定)

---

**下一步**: 在 SSH 服務器上執行 `/tmp/test_cannabis_unified.py` 進行功能驗證
