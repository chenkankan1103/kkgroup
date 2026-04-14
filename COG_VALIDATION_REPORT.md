# 🔍 Cog 導入檢驗報告

**日期**: 2026-04-14  
**檢驗內容**: Cog 功能正常性 & 資料庫引用方式

## 概況

- **總 Cog 數量**: 40+
- **有 setup() 函數的 Cog**: 20+
- **資料庫導入問題**: ⚠️ **有 8 個 Cog 使用舊的目錄導入路徑**

---

## ✅ 正確的專案結構

重構後的目錄結構：
- ✅ `cogs/common/` - 公共命令 Cog
- ✅ `cogs/shop/` - 商店 Cog
- ✅ `cogs/ui/` - UI Cog  
- ✅ `db_adapter` - 統一資料庫接口（根目錄）

**已移除的舊目錄**：
- ❌ `uicommands/` - 已遷移到 `cogs/ui/`
- ❌ `shop_commands/` - 已遷移到 `cogs/shop/`
- ❌ `commands/` - 已遷移到 `cogs/common/`

---

## 🐛 發現的問題

### 問題 1: 舊的絕對導入路徑

以下 Cog 仍在使用已不存在的目錄路徑：

| 文件 | 問題 | 影響 |
|------|------|------|
| `cogs/shop/shop.py` | `from shop_commands.merchant.xxx` | ❌ ImportError |
| `cogs/ui/cannabis_locker.py` | `from shop_commands.merchant.xxx` | ❌ ImportError |
| `cogs/shop/merchant/cannabis_merchant_view.py` | `from shop_commands.merchant.xxx` | ❌ ImportError |
| `cogs/ui/commands/admin_commands.py` | `from uicommands.views import` | ❌ ImportError |
| `cogs/ui/cannabis_locker.py` | `from uicommands.utils import` | ❌ ImportError |
| `cogs/ui/cogs/locker_event_listener.py` | `from uicommands.events import` | ❌ ImportError |
| `cogs/ui/cogs/locker_event_test.py` | `from uicommands.events import` | ❌ ImportError |

### 問題 2: 資料庫引用統計

✅ **正確的導入方式** (20 個 Cog):
```python
from db_adapter import get_user_field, set_user_field, ...
```

這些 Cog 使用正確的絕對導入，不會有問題：
- ✅ `cogs/common/kcoin.py`
- ✅ `cogs/common/leaderboard_manager.py`
- ✅ `cogs/common/AI.py`
- ✅ `cogs/common/work_function/database.py`
- ✅ `cogs/ui/airdrop_system.py`
- ✅ `cogs/ui/welcome_message.py`
- ✅ `cogs/ui/uibody.py`
- 等等...

---

## 🛠️ 修復方案

### 需要修復的文件列表

#### 1. `cogs/shop/shop.py`
```python
# ❌ 現在
from shop_commands.merchant.views import (...)
from shop_commands.merchant.database import (...)
from shop_commands.merchant.config import (...)
from shop_commands.role_expiration_manager import (...)

# ✅ 應該改成
from .merchant.views import (...)
from .merchant.database import (...)
from .merchant.config import (...)
from .role_expiration_manager import (...)
```

#### 2. `cogs/ui/cannabis_locker.py`
```python
# ❌ 現在
from shop_commands.merchant.cannabis_farming import (...)
from shop_commands.merchant.cannabis_config import (...)
from shop_commands.merchant.database import (...)
from uicommands.utils.locker_embed_generator import (...)
from uicommands.views import (...)

# ✅ 應該改成
from cogs.shop.merchant.cannabis_farming import (...)
from cogs.shop.merchant.cannabis_config import (...)
from cogs.shop.merchant.database import (...)
from cogs.ui.utils.locker_embed_generator import (...)
from cogs.ui.views import (...)
```

#### 3. `cogs/shop/merchant/cannabis_merchant_view.py`
```python
# ❌ 現在
from shop_commands.merchant.database import (...)
from shop_commands.merchant.cannabis_farming import (...)

# ✅ 應該改成
from ..database import (...)
from .cannabis_farming import (...)
```

#### 4. `cogs/ui/commands/admin_commands.py`
```python
# ❌ 現在
from uicommands.views import (...)
from uicommands.utils.locker_embed_generator import (...)
from uicommands.utils.image_utils import (...)

# ✅ 應該改成
from ..views import (...)
from ..utils.locker_embed_generator import (...)
from ..utils.image_utils import (...)
```

#### 5. 其他相關文件
- `cogs/ui/cannabis_locker.py` - 行 469, 482
- `cogs/ui/cogs/locker_event_listener.py` - 行 9-18
- `cogs/ui/cogs/locker_event_test.py` - 行 9

---

## 📊 影響範圍

### 受影響的功能
1. **商店系統** (`cogs/shop/shop.py`)
   - 物品購買
   - 角色管理
   - 賭博功能
   - 紙娃娃系統

2. **置物櫃系統** (`cogs/ui/cannabis_locker.py`)
   - 大麻種植
   - 庫存管理
   - 面板顯示

3. **管理員命令** (`cogs/ui/commands/admin_commands.py`)
   - 使用者管理
   - 置物櫃維護

4. **事件監聽** (`cogs/ui/cogs/locker_event_listener.py`)
   - 置物櫃事件處理
   - 動態更新

---

## ✅ 資料庫引用驗證

### 統計結果
- ✅ **使用 `db_adapter` 的 Cog**: 20+
  - 這些 Cog 的資料庫引用方式正確
  - 都使用了統一的 `from db_adapter import` 方式
  
- ⚠️ **需要修復的 Cog**: 8
  - 主要是因為導入目錄路徑錯誤，而非資料庫引用方式

### 資料庫方法範例（正確用法）
```python
# 獲取使用者欄位
from db_adapter import get_user_field, set_user_field, add_user_field

# 金幣操作
kkcoin = get_user_field(user_id, 'kkcoin', default=0)
set_user_field(user_id, 'kkcoin', new_value)
add_user_field(user_id, 'kkcoin', increase_amount)

# 取得所有使用者
from db_adapter import get_all_users
users = get_all_users()
```

---

## 🎯 建議行動

### 優先級 1 (高):
- [ ] 修復 `cogs/shop/shop.py` (商店功能無法運作)
- [ ] 修復 `cogs/ui/cannabis_locker.py` (置物櫃無法運作)

### 優先級 2 (中):
- [ ] 修復 `cogs/shop/merchant/cannabis_merchant_view.py`
- [ ] 修復 `cogs/ui/commands/admin_commands.py`
- [ ] 修復事件監聽相關文件

### 優先級 3 (低):
- [ ] 測試所有修復後的 Cog
- [ ] 驗證 Discord 機器人的完整功能

---

## 結論

**當前狀態**: ⚠️ **部分 Cog 因導入路徑錯誤無法運作**

**根本原因**: 重構時遷移了目錄結構（uicommands → cogs/ui, shop_commands → cogs/shop），但部分 Cog 文件仍使用舊的導入路徑

**修復難度**: ⭐ 低 (只需更新 import 語句)

**預計修復時間**: 30-60 分鐘
