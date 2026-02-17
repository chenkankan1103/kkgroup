# 🔍 置物櫃 Embed 被綁架審計報告

## 問題描述
置物櫃在手動修復後（通過 `/update_forum_lockers`），過一段時間會變回舊 embed，表示有多個代碼在持續覆蓋置物櫃訊息。

---

## 📊 所有修改 Locker Embed 的代碼位置

### 1️⃣ **背景任務（@tasks.loop）**

#### A) `locker_tasks.py::update_all_locker_embeds()` [DISABLED]
- **File**: `uicommands/tasks/locker_tasks.py` 
- **Interval**: 30 分鐘（如果啟用）
- **Status**: ✅ 已禁用（在 `uibody.py` 第70-75行被設定為 `None`）
- **Function**: 每30分鐘批量編輯所有使用者的 locker_message_id 訊息
- **Issue**: 已禁用但代碼仍存在，若誤啟動會覆蓋所有置物櫃

#### B) `locker_panel.py::update_locker_panel()` [RUNNING]
- **File**: `uicommands/locker_panel.py`
- **Interval**: 30 分鐘
- **Status**: ⚠️ **正在執行**（LockerPanelCog 已被實例化）
- **Function**: 編輯面板概況訊息（panel_message_id，而非個人 locker_message_id）
- **Related Code**: 
  - Line 44: `self.update_locker_panel.start()`
  - Line 96-120: 編輯訊息邏輯
- **Impact**: 面板訊息（**非** 個人置物櫃），低風險

#### C) `cannabis_locker.py::update_panel_task()` [RUNNING]
- **File**: `uicommands/cannabis_locker.py`
- **Interval**: 30 分鐘
- **Status**: ⚠️ **正在執行**（CannabisCog 已被實例化）
- **Function**: 編輯面板概況訊息
- **Related Code**: 
  - Line 42: `self.update_panel_task.start()`
  - Line 92-109: 編輯訊息邏輯
- **Issue**: **與 locker_panel.py 重複功能** — 兩個 cog 都在每30分鐘更新同一個概況面板訊息

---

### 2️⃣ **啟動時一次性調用（非 @tasks.loop）**

#### D) `cannabis_locker.py::update_all_locker_views()` [RUNS AT STARTUP]
- **File**: `uicommands/cannabis_locker.py`
- **Trigger**: PersonalLockerCog.__init__() 中調用（Line 271）
- **Status**: ✅ 執行一次（bot啟動時）
- **Function**: 檢查所有 locker threads，調用 `update_single_locker_view()`
- **Impact**: 
  - 調用 `send_updated_locker_embed()` 來編輯個人的 locker_message_id 訊息
  - 但只在 bot 啟動時執行一次
  - 使用正確的動態 MapleStory API URL（通過 `UserPanel.create_user_embed()`）

#### E-1) `cannabis_locker.py::send_updated_locker_embed()` [HELPER]
- **Called By**: 
  - D) `update_all_locker_views()` → `update_single_locker_view()`
  - User interactions (crop/fertilize 按鈕)
- **Function**: 生成或編輯個人置物櫃訊息
- **Generate Method**: 
  - 優先使用 `UserPanel.create_user_embed()` ✅（動態 API URL）
  - Fallback: `uicommands.utils.embed_utils.create_user_embed()` ✅（動態 API URL）
  - Extreme fallback: 手動建立（line 485+）

---

### 3️⃣ **手動命令**

#### F) `admin_commands.py::update_forum_lockers()` [MANUAL]
- **File**: `uicommands/commands/admin_commands.py`
- **Command**: `/update_forum_lockers`
- **Trigger**: 管理員手動執行
- **Function**: 批量編輯所有使用者的 locker_message_id 訊息
- **Logic**:
  - 嘗試使用 `UserPanel.create_user_embed()` 來創建 embed
  - 若無圖片，計算 MapleStory API URL fallback
  - 編輯訊息並更新 view

---

### 4️⃣ **用戶互動（按鈕回調）**

#### G) Button callbacks 修改 locker embed

**G1) `update_panel.py::UpdatePanelView` 按鈕**
- **File**: `uicommands/views/update_panel.py`
- **Actions**: Line 55, 66 - `await interaction.message.edit(embed=..., view=...)`
- **Function**: 點擊按鈕時刷新 embed

**G2) `personal_locker.py::PersonalLockerView` 按鈕**
- **File**: `uicommands/views/personal_locker.py`
- **Actions**: Line 326 - `await interaction.message.edit(...)`
- **Function**: 植物/庫存操作後更新 embed

**G3) `locker_panel.py::LockerPanelView` 按鈕**
- **File**: `uicommands/views/locker_panel.py`
- **Actions**: Line 89 - `await interaction.message.edit(...)`

---

## ⚠️ 重複性任務分析

### 重複 #1: 面板統計更新（30分鐘間隔）
```
locker_panel.py::update_locker_panel()  [每30分鐘編輯面板]
cannabis_locker.py::update_panel_task()  [每30分鐘編輯面板]
```
- **Issue**: 兩個 cog 都在試圖編輯同一個概況面板訊息
- **Solution**: 只保留一個

### 可能的"過陣子變回舊embed"原因

雖然 `locker_tasks.py::update_all_locker_embeds()` 已禁用，但以下可能是間接原因：

1. **用戶操作後的按鈕回調** (G1-G3)
   - 每次植物操作或更新面板時
   - 會調用 `send_updated_locker_embed()` 生成新 embed
   - 如果此時沒有正確調用 `UserPanel.create_user_embed()`，может使用舊 embed_image_source

2. **cannabis_locker.py::send_updated_locker_embed() 的 fallback 邏輯**
   - Line 440-490: 若無法取得 UserPanel，會 fallback
   - 若 fallback 邏輯有 bug，会生成舊 embed

3. **locker_tasks.py 仍可能被誤啟動**
   - 若環境變數或代碼被修改，背景任務可能重新啟動
   - 會每30分鐘覆蓋所有置物櫃訊息

---

## 🎯 核心問題

### 多個代碼路徑修改同一資源
```
個人置物櫃訊息 (locker_message_id)
    ↓
    ├─ /update_forum_lockers (手動命令)
    ├─ locker_tasks.py::update_all_locker_embeds() [DISABLED]
    ├─ cannabis_locker.py::send_updated_locker_embed() [啟動時 + 按鈕]
    ├─ personal_locker.py 按鈕回調
    ├─ update_panel.py 按鈕回調
    └─ locker_panel.py 按鈕回調
```

### 面板訊息 (panel_message_id)
```
概況面板訊息
    ↓
    ├─ locker_panel.py::update_locker_panel() [每30分鐘]
    └─ cannabis_locker.py::update_panel_task() [每30分鐘] ← DUPLICATE!
```

---

## 💡 整合建議

### Phase 1: 立即修復（去重）
1. **關閉 locker_panel.py 背景任務**
   - 將 locker_panel.py 的 `update_locker_panel.start()` 移除或條件禁用
   - 讓 cannabis_locker.py 的 `update_panel_task()` 成為唯一的面板更新源

2. **移除或保護 locker_tasks.py**
   - 目前已禁用，但應刪除或標記為 deprecated
   - 防止未來誤啟動

### Phase 2: 統一 embed 生成邏輯
1. **創建中心化的 locker embed 生成器**
   - 新建 `uicommands/utils/locker_embed_generator.py`
   - 統一所有 embed 生成邏輯
   - 確保所有路徑都使用動態 MapleStory API URL

2. **審計並修復所有 embed 生成路徑**
   - F) admin_commands.py 
   - E-1) cannabis_locker.py::send_updated_locker_embed()
   - G1-G3) 所有按鈕回調

### Phase 3: 消除硬編碼按鈕更新
1. **統一按鈕回調邏輯**
   - 所有按鈕都應呼叫中心化的 embed 生成器
   - 避免各自實現 embed 生成

---

## 📝 檔案變動清單

| File | Change | Priority |
|------|--------|----------|
| `uicommands/locker_panel.py` | 禁用 `update_locker_panel()` 背景任務 | 🔴 High |
| `uicommands/tasks/locker_tasks.py` | 標記為 deprecated 或刪除 | 🔴 High |
| `uicommands/cannabis_locker.py` | 整合面板更新邏輯 + 改進 send_updated_locker_embed() | 🟡 Medium |
| `uicommands/commands/admin_commands.py` | 改進 update_forum_lockers() 邏輯 | 🟡 Medium |
| `uicommands/views/*_locker*.py` | 統一按鈕回調邏輯 | 🟡 Medium |
| `uicommands/utils/locker_embed_generator.py` | **新建** 中心化生成器 | 🟢 Low (建議) |

