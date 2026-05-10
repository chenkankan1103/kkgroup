# Discord Bot 系統詳解

## 系統概述

KKGroup Discord Bot 系統採用多服務架構，包含主 Bot、商店 Bot 和 UI Bot，每個服務獨立運行並透過 systemd 管理。

## Bot 服務架構

### 1. 主 Bot (`bots/bot.py`)
**功能範圍**:
- 核心指令處理
- 用戶管理
- 基礎互動功能
- 系統狀態監控

**關鍵特性**:
- 使用 `discord.py` 框架
- 支援 Slash Commands
- 整合 Cogs 系統
- 非同步事件處理

### 2. 商店 Bot (`bots/shopbot.py`)
**功能範圍**:
- 虛擬商店管理
- 交易處理
- 商品管理
- 經濟系統

**關鍵特性**:
- 整合商店 Cogs
- 支援多種交易類型
- 實時庫存管理
- 交易記錄追蹤

### 3. UI Bot (`bots/uibot.py`)
**功能範圍**:
- 用戶界面管理
- 視覺化組件
- 互動式表單
- 狀態顯示

**關鍵特性**:
- 豐富的 UI 組件
- 按鈕和選單系統
- 動態內容更新
- 響應式設計

## Cogs 模組系統

### Common Cogs (`cogs/common/`)
核心功能模組，提供基礎服務：

#### 主要模組
- **AI.py**: AI 相關功能整合
- **work_function/**: 工作相關功能集合
- **工具類模組**: 通用工具和輔助功能

#### 特色功能
- 模組化設計，易於維護
- 統一的錯誤處理
- 共享配置和資源

### Shop Cogs (`cogs/shop/`)
商業功能模組：

#### 核心模組
- **HospitalMerchant.py**: 醫院商家系統
- **cannabis_cog.py**: 特殊商品管理
- **merchant/**: 商家核心功能

#### 功能特色
- 完整的經濟系統
- 多樣化商品類型
- 自動化交易流程

### UI Cogs (`cogs/ui/`)
用戶界面模組：

#### 主要組件
- **AvatarReset.py**: 頭像重置功能
- **ScamParkEvents.py**: 特殊事件處理
- **commands/**: 指令處理系統
- **events/**: 事件處理系統

#### 設計特點
- 直觀的用戶體驗
- 豐富的視覺效果
- 響應式互動設計

## 按鈕和視圖系統

### PersistentEmbedView
**用途**: 臨時視圖，30秒超時
```python
from shared.utils.embed_views import PersistentEmbedView

# 創建臨時視圖
view = PersistentEmbedView(timeout=30)
```

### PersistentViewBase
**用途**: 永久視圖，無超時限制
```python
from shared.utils.embed_views import PersistentViewBase

# 創建永久視圖
view = PersistentViewBase()
```

### 按鈕樣式
- **primary**: 主要操作（藍色）
- **secondary**: 次要操作（灰色）
- **success**: 成功操作（綠色）
- **danger**: 危險操作（紅色）
- **link**: 連結操作（藍色連結）

### 視圖註冊系統
```python
from shared.utils.view_registry import register_view

# 註冊視圖
@register_view
class MyView(PersistentViewBase):
    pass
```

## Discord 指令系統

### Slash Commands
使用 `@app_commands.command()` 裝飾器：
```python
import discord
from discord import app_commands

@bot.tree.command(name="example", description="範例指令")
async def example_command(interaction: discord.Interaction):
    await interaction.response.send_message("回應內容")
```

### 指令註冊表
位置：`config/commands_registry.json`
```json
{
  "commands": [
    {
      "name": "example",
      "description": "範例指令",
      "category": "general"
    }
  ]
}
```

## 權限和角色系統

### VIP 角色系統
```python
# 購買 VIP 角色
await save_role_purchase(user_id, role_name, duration)

# 自動清理過期角色
await cleanup_expired_roles_loop()

# 手動授予角色
@bot.tree.command(name="grant_temporary_role")
async def grant_temporary_role(interaction, user: discord.Member, role_name: str, duration: str):
    # 實作邏輯
```

### 權限檢查
```python
# 檢查用戶權限
def has_permission(user: discord.Member, required_role: str) -> bool:
    return any(role.name == required_role for role in user.roles)
```

## 訊息處理

### 靜音訊息
使用 `ephemeral=True` 參數：
```python
await interaction.response.send_message("私人訊息", ephemeral=True)
```

### 嵌入式訊息
```python
embed = discord.Embed(
    title="標題",
    description="描述",
    color=discord.Color.blue()
)
embed.add_field(name="欄位名稱", value="欄位值", inline=False)
await interaction.response.send_message(embed=embed)
```

## 事件處理

### 常用事件
```python
@bot.event
async def on_ready():
    print(f"Bot 已登入: {bot.user}")

@bot.event
async def on_member_join(member):
    # 新成員加入處理
    pass

@bot.event
async def on_message(message):
    # 訊息處理
    pass
```

## 錯誤處理

### 全域錯誤處理
```python
@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message("指令冷卻中", ephemeral=True)
    else:
        await interaction.response.send_message("發生錯誤", ephemeral=True)
```

## 效能優化

### 非同步處理
- 所有 I/O 操作使用 `async/await`
- 避免阻塞操作
- 使用 `asyncio.gather()` 並行處理

### 快取機制
```python
# Discord URL 快取
discord_url_cache = {}

def get_discord_url(user_id: str) -> str:
    if user_id not in discord_url_cache:
        discord_url_cache[user_id] = fetch_discord_url(user_id)
    return discord_url_cache[user_id]
```

## 部署配置

### 服務檔案
位置：`config/services/`
- `bot.service`: 主 Bot 服務
- `shopbot.service`: 商店 Bot 服務
- `kkgroup-api.service`: API 服務

### 啟動腳本
```bash
# 啟動所有服務
./config/scripts/bot_manager.sh start

# 重啟特定服務
sudo systemctl restart bot.service
```

## 監控和日誌

### 系統日誌
```bash
# 查看服務日誌
sudo journalctl -u bot.service -n 100 --no-pager

# 即時監控
sudo journalctl -u bot.service -f
```

### 狀態檢查
```python
# Bot 狀態檢查
@bot.tree.command(name="status")
async def status_command(interaction: discord.Interaction):
    embed = discord.Embed(title="系統狀態")
    embed.add_field(name="Bot 狀態", value="✅ 正常運行")
    await interaction.response.send_message(embed=embed)
```

## 安全考量

### Token 管理
- 使用環境變數儲存 Discord Token
- 定期更換 Token
- 限制 Token 權限範圍

### 資料保護
- 敏感資料加密儲存
- 用戶隱私保護
- 符合 Discord 服務條款

## 相關文檔

- [專案架構總覽](project-architecture.md)
- [Bot 服務詳情](../entities/bot-services.md)
- [編碼規則和路徑](coding-rules-and-paths.md)
- [Discord 靜音訊息寫法](discord-silent-messages.md)
