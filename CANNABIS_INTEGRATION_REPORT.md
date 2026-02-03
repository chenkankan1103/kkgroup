# 大麻種植系統 - 集成完成報告

## 系統概述

完成了一個完整的大麻種植系統，集成到現有的黑市商人UI和個人置物櫃中。用戶無需使用命令，所有操作都通過嵌入式按鈕進行。

## 集成結構

### 1. 黑市商人整合 (Black Market Integration)

**位置**: `shop_commands/merchant/views.py` - `ExploreView` 類
**新增按鈕**: "🌱 種植大麻"

**流程**:
```
黑市主菜單 (ExploreView)
  └─ 🌱 種植大麻 按鈕
      └─ CannabisMerchantView (大麻商店菜單)
          ├─ 購買種子 → SeedCategoryView → BuySeedModal
          ├─ 購買肥料 → FertilizerCategoryView → BuyFertilizerModal
          ├─ 出售大麻 → SellCannabisCategoryView
          └─ 返回 → ExploreView
```

### 2. 個人置物櫃整合 (Personal Locker Integration)

**位置**: `uicommands/cannabis_locker.py` - `PersonalLockerCog` 類
**命令**: `/置物櫃`

**流程**:
```
個人置物櫃 (PersonalLockerCog)
  └─ PersonalLockerMenuView (菜單)
      ├─ 查看植物 → PlantActionView
      │   ├─ 施肥 → SelectPlantForFertilizerView → SelectFertilizerView
      │   └─ 收割 → SelectPlantForHarvestView
      ├─ 查看庫存 (庫存清單)
      ├─ 種植大麻 → SelectSeedToPlanView
      └─ 查看更多 → MoreOptionsView
```

## 新增檔案

### 1. `shop_commands/merchant/cannabis_merchant_view.py`
黑市商人的大麻購買/出售界面
- `CannabisMerchantView`: 主菜單（3個按鈕）
- `SeedCategoryView`: 種子選擇
- `BuySeedModal`: 種子購買數量輸入
- `FertilizerCategoryView`: 肥料選擇
- `BuyFertilizerModal`: 肥料購買數量輸入
- `SellCannabisCategoryView`: 出售大麻選擇

**功能**:
- ✅ 購買種子（按數量）
- ✅ 購買肥料（按數量）
- ✅ 出售大麻（全部或部分）
- ✅ 自動扣除/增加KKcoin
- ✅ 庫存管理

### 2. `uicommands/cannabis_locker.py` (已更新)
個人置物櫃的種植管理界面
- `PersonalLockerCog`: 主Cog
- `PersonalLockerMenuView`: 主菜單（4個按鈕）
- `PlantActionView`: 植物操作（施肥/收割）
- `MoreOptionsView`: 更多選項
- `SelectSeedToPlanView`: 選擇種子種植
- `SelectPlantForFertilizerView`: 選擇植物施肥
- `SelectFertilizerView`: 選擇肥料類型
- `SelectPlantForHarvestView`: 選擇植物收割

**功能**:
- ✅ 查看所有種植中的植物
- ✅ 實時進度條顯示
- ✅ 剩餘成長時間計算
- ✅ 庫存清單（種子/肥料/大麻成品）
- ✅ 種植新植物
- ✅ 施肥加速成長
- ✅ 收割成熟植物
- ✅ 按鈕交互（無需輸入命令）

### 3. `shop_commands/merchant/views.py` (已修改)
在 `ExploreView` 類中添加大麻按鈕
```python
@discord.ui.button(label="🌱 種植大麻", style=discord.ButtonStyle.success, custom_id="persistent_cannabis")
async def cannabis_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    from shop_commands.merchant.cannabis_merchant_view import CannabisMerchantView
    # 顯示大麻商店菜單
```

## 已有支持檔案

### `shop_commands/merchant/cannabis_farming.py` (已存在)
核心後端邏輯：
- 數據庫表初始化
- 庫存管理（add/remove/get_inventory）
- 植物生命週期管理（plant/apply_fertilizer/harvest）
- 大麻出售邏輯

### `shop_commands/merchant/cannabis_config.py` (已存在)
配置檔案：
- 種子配置（常規種/優質種/黃金種）
- 肥料配置（基礎/進階/超級）
- 產品價格

## 工作流程示例

### 購買種子流程
1. 用戶在Discord中點擊黑市商人 → "探索"
2. 看到菜單，點擊 "🌱 種植大麻"
3. 看到大麻商店菜單，點擊 "購買種子"
4. 選擇種子類型（如"優質種"）
5. 輸入購買數量（Modal彈窗）
6. 確認購買（KKcoin自動扣除）
7. 種子添加到庫存

### 種植流程
1. 用戶輸入命令 `/置物櫃`
2. 看到個人置物櫃，點擊 "種植大麻"
3. 選擇要種植的種子類型
4. 種植成功，植物開始成長
5. 可以在置物櫃查看進度條和剩餘時間

### 施肥流程
1. 在個人置物櫃點擊 "查看更多" → "施肥"
2. 選擇要施肥的植物
3. 選擇肥料類型
4. 施肥成功，成長時間減少

### 收割流程
1. 植物成熟後，點擊 "查看更多" → "收割"
2. 選擇已成熟的植物
3. 收割成功，大麻添加到庫存
4. 可在黑市商人出售

## 技術細節

### 數據流
```
用戶互動 (Discord Button)
  ↓
View/Modal 類 (handlers)
  ↓
cannabis_farming.py 函數 (核心邏輯)
  ↓
SQLite 數據庫 (數據持久化)
  ↓
Discord Embed + KKcoin 更新
```

### 錯誤處理
- ✅ 所有函數調用都包裝在 try-except 中
- ✅ 用戶友好的錯誤消息（ephemeral=True）
- ✅ 數據驗證（數量>0、KKcoin充足、庫存存在）

### 性能優化
- ✅ 異步操作（async/await）
- ✅ 限制選擇按鈕數量（最多5個）
- ✅ Modal用於數值輸入（避免多次點擊）

## 導入驗證

已驗證所有模塊可正確導入：
- ✅ `shop_commands.merchant.cannabis_merchant_view`
- ✅ `uicommands.cannabis_locker`
- ✅ `shop_commands.merchant.views` (包含新的cannabis_button)

## 部署步驟

1. 確保所有文件已創建/修改
2. 運行機器人，加載新的Cog
3. 測試黑市商人的大麻按鈕
4. 測試個人置物櫃命令

## 待辦項

- 🔄 運行機器人進行實際測試
- 🔄 驗證Discord上的按鈕交互
- 🔄 測試完整的購買→種植→施肥→收割→出售流程
- 🔄 監控性能和錯誤日誌

## 備註

此集成完全遵循現有代碼模式：
- 使用 `discord.ui.View` 和 `Button`
- 異步處理所有I/O操作
- 遵循 Cog 架構
- 與現有KKcoin系統集成
- 使用 aiosqlite 進行數據庫操作
