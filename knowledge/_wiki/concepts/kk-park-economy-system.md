# KK 園區經濟系統

## 系統定位

KK 園區的經濟系統不是單一 Cog，而是跨 Bot、跨資料層、跨互動入口的共享機制。

核心貨幣是 `kkcoin`，但實際行為分散在：

- 餘額查詢與排行榜
- 商店消費與購買效果
- UI 事件獎勵
- 小遊戲或活動獎懲
- 中央儲備與總量觀察

因此查經濟問題時，不要只看 [cogs/shop](../../../cogs/shop)，還要一起看 [cogs/common](../../../cogs/common)、[cogs/ui](../../../cogs/ui)、[shared/db](../../../shared/db)、[config/discord_commands_registry.json](../../../config/discord_commands_registry.json)。

## 核心代碼入口

### 1. 指令與可見入口

- [cogs/common/kcoin.py](../../../cogs/common/kcoin.py)
  - KK 幣查詢、排行榜、中央儲備金狀態
  - 對使用者來說，這是最直接的經濟資訊入口
- [config/discord_commands_registry.json](../../../config/discord_commands_registry.json)
  - 把經濟系統拆成 `KK幣系統`、`儲備金系統`、`購物系統`
  - 可用來快速追查某個 slash command 對應哪個檔案

### 2. 實際資料寫入入口

- [shared/db/db_adapter.py](../../../shared/db/db_adapter.py)
  - `get_user_kkcoin(user_id)`
  - `update_user_kkcoin(user_id, amount)`
  - 這裡是大量舊代碼共用的向後相容入口
- [shared/db/sheet_driven_db.py](../../../shared/db/sheet_driven_db.py)
  - `kkcoin` 是資料欄位的一部分
  - 說明經濟數值不是孤立表，而是玩家主資料的一部分
- [shared/db/database_schema.py](../../../shared/db/database_schema.py)
  - schema 層定義 `kkcoin`

### 3. 消費與產出邏輯

- [cogs/shop/shop.py](../../../cogs/shop/shop.py)
  - `/shopping`、拉霸、角色與裝備購買
  - 會讀取餘額、驗證是否足夠、再寫回 KK 幣
- [cogs/shop/cannabis_cog.py](../../../cogs/shop/cannabis_cog.py)
  - 種子/肥料購買、收成出售
  - 是獨立商品循環與收入來源
- [cogs/shop/merchant](../../../cogs/shop/merchant)
  - 多個商家 view 與交易流程都會直接影響 KK 幣
- [cogs/shop/HospitalMerchant.py](../../../cogs/shop/HospitalMerchant.py)
  - 特定商家消費流程

### 4. 非商店的經濟流入

- [cogs/ui/anime_tracker.py](../../../cogs/ui/anime_tracker.py)
  - 投票、留言會發放 KK 幣獎勵
  - 說明 UI 互動本身也會改動經濟
- [shared/utils/fortress_system.py](../../../shared/utils/fortress_system.py)
  - 有付費行為成本與勝利獎勵
  - 代表活動玩法也會進入經濟回路

## 經濟系統的實際關聯圖

可以把它理解成這樣：

`Discord 指令 / UI 互動 / 活動系統`
-> `cogs/common | cogs/shop | cogs/ui`
-> `shared/db/db_adapter.py`
-> `sheet-driven 使用者資料`

其中最常見的控制流是：

1. 入口指令或按鈕先決定規則
2. 用 `get_user_kkcoin()` 讀餘額
3. 執行資格檢查或獎勵計算
4. 用 `update_user_kkcoin()` 或 `set_user_field()` 寫回
5. 再由排行榜、面板、訊息 embed 顯示結果

## 查問題時的閱讀順序

### 情境 1：使用者說 KK 幣數字不對

先看：

1. [cogs/common/kcoin.py](../../../cogs/common/kcoin.py)
2. [shared/db/db_adapter.py](../../../shared/db/db_adapter.py)
3. 觸發該數值變更的功能檔

### 情境 2：某個功能沒有扣款或沒發獎

先看：

1. 對應功能的 Cog 或 View
2. 是否呼叫 `update_user_kkcoin()` / `set_user_field()`
3. 是否有重複獎勵防護或條件判斷

### 情境 3：經濟指令找不到在哪

先看：

1. [config/discord_commands_registry.json](../../../config/discord_commands_registry.json)
2. 對應的 `file` 欄位
3. 再進對應 Cog

## 功能對應檔案速查

### 1. KK 幣查詢 / 排行榜 / 儲備資訊

- 知識頁: [Discord Bot 系統詳解](discord-bot-system.md)
- 主要檔案:
  - [cogs/common/kcoin.py](../../../cogs/common/kcoin.py)
  - [shared/db/db_adapter.py](../../../shared/db/db_adapter.py)
  - [config/discord_commands_registry.json](../../../config/discord_commands_registry.json)

### 2. 商店購買 / 拉霸 / 裝備與身份

- 主要檔案:
  - [cogs/shop/shop.py](../../../cogs/shop/shop.py)
  - [cogs/shop/merchant](../../../cogs/shop/merchant)
  - [config/shop_config.backup.py](../../../config/shop_config.backup.py)

### 3. 大麻種植與商家循環

- 主要檔案:
  - [cogs/shop/cannabis_cog.py](../../../cogs/shop/cannabis_cog.py)
  - [cogs/shop/merchant/cannabis_config.py](../../../cogs/shop/merchant/cannabis_config.py)
  - [cogs/shop/merchant/cannabis_farming.py](../../../cogs/shop/merchant/cannabis_farming.py)
  - [cogs/shop/merchant/cannabis_merchant_view_v2.py](../../../cogs/shop/merchant/cannabis_merchant_view_v2.py)

### 4. UI 互動獎勵

- 主要檔案:
  - [cogs/ui/anime_tracker.py](../../../cogs/ui/anime_tracker.py)
  - [shared/db/db_adapter.py](../../../shared/db/db_adapter.py)

### 5. 活動成本與戰鬥獎勵

- 主要檔案:
  - [shared/utils/fortress_system.py](../../../shared/utils/fortress_system.py)
  - [shared/db/db_adapter.py](../../../shared/db/db_adapter.py)

### 6. 指令入口定位

- 先查 [config/discord_commands_registry.json](../../../config/discord_commands_registry.json)
- 再跳到對應 `file` 欄位
- 若要看 bot 分工，再回看 [Discord Bot 系統詳解](discord-bot-system.md)

## 與其他知識頁的關係

- 這一頁負責回答「經濟系統跨哪些代碼層」
- `discord-bot-system.md` 負責回答「Bot 與 Cog 如何分工」
- `project-architecture.md` 負責回答「整個 repo 模組怎麼分區」
- `command-registry.md` 負責回答「維運命令怎麼找」

## 相關文檔

- [Discord Bot 系統詳解](discord-bot-system.md)
- [專案架構總覽](project-architecture.md)
- [KK 園區系統地圖](kk-park-system-map.md)
- [開發工具和流程](development-tools-and-workflow.md)
- [Command Registry](../entities/command-registry.md)
- [Bot Services](../entities/bot-services.md)
