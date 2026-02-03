# 周統計面板 - 大麻系統集成說明

## 功能概述

在每周日晚上 23:59 的周統計事件中，系統會自動在用戶的個人線程中發送：
1. **統計 Embed**：顯示本周的 KKCoin、經驗值、等級增長及 AI 評論
2. **種植面板 Embed**（新增）：提供大麻系統的快速訪問按鈕

## 實現位置

### 1. 核心修改：`uicommands/uibody.py` (UpdatePanelCog)

在 `weekly_summary()` 方法中，於發送統計 embed 後添加：

```python
# 添加大麻系統快速訪問面板
try:
    cannabis_embed = discord.Embed(
        title="🌱 種植中心快速訪問",
        description="點擊按鈕快速管理大麻種植系統",
        color=0x2ecc71
    )
    # ... 字段添加 ...
    
    from uicommands.cannabis_locker import WeeklySummaryCannabisPanelView
    view = WeeklySummaryCannabisPanelView(self.bot, user_id)
    await thread.send(embed=cannabis_embed, view=view)
except Exception as e:
    pass  # 靜默失敗
```

### 2. 新增 View 類：`uicommands/cannabis_locker.py`

新增 `WeeklySummaryCannabisPanelView` 類，包含三個按鈕：

```python
class WeeklySummaryCannabisPanelView(discord.ui.View):
    @discord.ui.button(label="施肥加速", style=discord.ButtonStyle.primary, emoji="💧")
    async def fertilize_button(self, interaction, button):
        # 施肥流程
        
    @discord.ui.button(label="收割成熟", style=discord.ButtonStyle.success, emoji="✂️")
    async def harvest_button(self, interaction, button):
        # 收割流程
        
    @discord.ui.button(label="查看狀態", style=discord.ButtonStyle.secondary, emoji="📊")
    async def view_plants_button(self, interaction, button):
        # 查看狀態
```

## 用戶交互流程

### 場景 A：施肥
```
周統計面板出現
    ↓
用戶點擊 [💧 施肥加速]
    ↓
系統顯示成長中的植物列表
    ↓
用戶選擇一個植物
    ↓
系統顯示可用肥料選擇
    ↓
用戶選擇肥料類型
    ↓
✅ 施肥成功，Embed 反饋結果
```

### 場景 B：收割
```
周統計面板出現
    ↓
用戶點擊 [✂️ 收割成熟]
    ↓
系統顯示已成熟的植物列表
    ↓
用戶選擇一個植物
    ↓
✅ 收割成功，大麻添加到庫存，Embed 反饋結果
```

### 場景 C：查看狀態
```
周統計面板出現
    ↓
用戶點擊 [📊 查看狀態]
    ↓
✅ 系統顯示所有植物的完整狀態 Embed
   ├─ 進度條（████░░░░ 45%）
   ├─ 剩餘時間（2h 30m）
   ├─ 施肥次數
   └─ 產量（已成熟的話）
```

## Embed 結構

### 統計 Embed（原有）
```
┌─────────────────────────────────┐
│ 📊 用戶的本週統計                │
│ 統計週期：01/27 - 02/03          │
│                                 │
│ 💰 KKCoin 增長      +5000       │
│ ✨ 經驗值 增長      +2500       │
│ ⭐ 等級 提升        +1         │
│                                 │
│ 🤖 AI 評論：本週...             │
│ 🔄 每週日 23:59 自動統計         │
└─────────────────────────────────┘
```

### 種植面板 Embed（新增）
```
┌─────────────────────────────────┐
│ 🌱 種植中心快速訪問              │
│ 點擊按鈕快速管理大麻種植系統     │
│                                 │
│ 💧 施肥加速                      │
│ 對成長中的植物施肥               │
│                                 │
│ ✂️ 收割成熟                      │
│ 收割已成熟的植物                 │
│                                 │
│ 📊 查看狀態                      │
│ 查看所有植物狀態                 │
│                                 │
│ [💧施肥] [✂️收割] [📊查看]      │
│                                 │
│ 從統計面板快速訪問種植系統       │
└─────────────────────────────────┘
```

### 後續交互 Embed（動態生成）
根據用戶點擊的按鈕，系統會生成相應的 Embed：

#### 施肥選擇
```
┌─────────────────────────────────┐
│ 💧 選擇要施肥的植物              │
│                                 │
│ #1 🌿 常規種                    │
│ 已施肥：0次                      │
│                                 │
│ #2 🌾 優質種                    │
│ 已施肥：1次                      │
│                                 │
│ #3 💛 黃金種                    │
│ 已施肥：0次                      │
│                                 │
│ [選擇植物按鈕們...]             │
└─────────────────────────────────┘
```

#### 狀態查看
```
┌─────────────────────────────────┐
│ 🌱 我的植物狀態                  │
│                                 │
│ #1 🌿                           │
│ 種類：常規種                     │
│ 進度：████░░░░░░░░░░░░░░ 20%  │
│ 剩餘 3h 45m                      │
│ 施肥：1次                        │
│                                 │
│ #2 🌾                           │
│ 種類：優質種                     │
│ 進度：███████████░░░░░░░░ 65%  │
│ 剩餘 0h 52m                      │
│ 施肥：2次                        │
│                                 │
│ #3 💛                           │
│ 種類：黃金種                     │
│ 進度：██████████████████ 100%  │
│ ✅ 已成熟                        │
│ 施肥：0次                        │
└─────────────────────────────────┘
```

## 設計特色

### ✨ 優勢

1. **自然集成**
   - 無縫融入周統計流程
   - 用戶已經在查看統計，直接提供快速訪問

2. **操作簡化**
   - 只需 3 個按鈕就能覆蓋核心功能
   - 無需輸入命令，直接按鈕交互

3. **信息清晰**
   - 統計 Embed 和種植面板分離，各自專注
   - 按完按鈕後立即顯示新 Embed，保持上下文

4. **級聯交互**
   - 第一層：種植面板（3 個按鈕）
   - 第二層：植物選擇（若干個按鈕）
   - 第三層：操作選擇或完成（肥料選擇等）

5. **可擴展性**
   - 易於添加更多快速訪問按鈕
   - 可重用的 View 類設計

## 錯誤處理

- ✅ 試圖施肥但無肥料 → 提示「你沒有肥料」
- ✅ 試圖收割但無成熟植物 → 提示「沒有已成熟的植物」
- ✅ 查看狀態但無植物 → 提示「還沒有種植任何植物」
- ✅ 所有操作都包裹在 try-except 中
- ✅ 大麻系統不可用時不影響周統計流程

## 技術實現

### 異步操作
- 所有數據庫查詢都是異步的 (`await`)
- 所有 Discord API 調用都是異步的

### 數據庫查詢
- `get_user_plants(user_id)` - 獲取用戶植物列表
- `get_inventory(user_id)` - 獲取用戶庫存
- `apply_fertilizer()` - 施肥
- `harvest_plant()` - 收割
- `remove_inventory()` - 移除庫存

### Embed 字段
- 颜色编码：綠色(種植)、藍色(施肥)、金色(成熟)
- 進度條：使用 █ 和 ░ 字符
- 時間計算：剩餘秒數轉換為小時分鐘

## 導入驗證

✅ 所有模塊已驗證可正確導入：
- `WeeklySummaryCannabisPanelView` (cannabis_locker.py)
- `UpdatePanelCog` (uibody.py) - 集成周統計的 Cog

## 后续建议

### 可选改进方向

1. **添加统计信息**
   - 在种植面板 Embed 中显示总植物数、今周收成等

2. **快捷购买按鈕**
   - 添加直接購買種子/肥料的按鈕（跳轉到黑市）

3. **提醒功能**
   - 植物即将成熟时的自动提醒

4. **排行榜**
   - 本周收成最多的用户排行

5. **自动化**
   - 支持多个快速访问面板同时显示

## 文件修改總結

| 文件 | 修改內容 | 影響 |
|------|---------|------|
| uicommands/uibody.py | 在 weekly_summary() 後添加種植面板 Embed | 發送額外 Embed（低風險） |
| uicommands/cannabis_locker.py | 新增 WeeklySummaryCannabisPanelView 類 | 新增功能，無影響現有功能 |

## 部署清單

- ✅ 代碼實現完成
- ✅ 語法驗證通過
- ✅ 導入驗證通過
- 🔄 等待機器人測試
- 🔄 驗證 Discord 上的實際效果

## 狀態

**當前版本**: Alpha 1.0
**上次更新**: 2026-02-03
**狀態**: 準備完畢，等待運行測試
