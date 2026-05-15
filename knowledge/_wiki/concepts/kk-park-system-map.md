# KK 園區系統地圖

## 用途

這一頁不是單一主題說明，而是用來回答一個更實際的問題：

「某個功能到底橫跨哪些知識頁、哪些 Bot、哪些代碼入口？」

適合在不想重掃整個 repo 時，先定位閱讀路徑。

## 核心主題地圖

### 1. 經濟系統

- 知識頁: [KK 園區經濟系統](kk-park-economy-system.md)
- Bot / 功能頁: [Discord Bot 系統詳解](discord-bot-system.md)
- 代碼入口:
  - [cogs/common/kcoin.py](../../../cogs/common/kcoin.py)
  - [cogs/shop/shop.py](../../../cogs/shop/shop.py)
  - [cogs/ui/anime_tracker.py](../../../cogs/ui/anime_tracker.py)
  - [shared/db/db_adapter.py](../../../shared/db/db_adapter.py)

### 2. 角色與紙娃娃系統

- 知識頁: [Paperdoll Workflow](paperdoll-workflow.md)
- 結構頁: [專案架構總覽](project-architecture.md)
- 常見代碼入口:
  - [cogs/ui](../../../cogs/ui)
  - [cogs/shop](../../../cogs/shop)
  - [twms_fashion_db.json](../../../twms_fashion_db.json)

### 3. Discord 訊息與持久化

- 知識頁:
  - [Discord 靜音訊息寫法](discord-silent-messages.md)
  - [Discord 訊息 ID 持久化實踐](discord-message-id-persistence.md)
- 代碼入口:
  - [cogs/common/announcement.py](../../../cogs/common/announcement.py)
  - [cogs/common](../../../cogs/common)
  - [cogs/shop/merchant/views.py](../../../cogs/shop/merchant/views.py)

### 4. 部署、Webhook 與 VM 維運

- 知識頁:
  - [部署和維運指南](deployment-and-operations.md)
  - [Webhook and Tunnel](webhook-and-tunnel.md)
  - [VM Operations](../entities/vm-operations.md)
  - [VM 實際配置狀況](../entities/vm-actual-configuration.md)
- 代碼與配置入口:
  - [scripts/commands_manager.py](../../../scripts/commands_manager.py)
  - [config/commands_registry.json](../../../config/commands_registry.json)
  - [config/services](../../../config/services)

### 5. AI Debug / LogMonitor / 自動修復

- 知識頁:
  - [LogMonitor 與 Auto AI Fix 流程總覽](log_monitor_pipeline.md)
  - [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)
- 代碼與 workflow 入口:
  - [cogs/common/log_monitor.py](../../../cogs/common/log_monitor.py)
  - [scripts/auto_ai_fix.py](../../../scripts/auto_ai_fix.py)
  - [.github/workflows](../../../.github/workflows)

### 6. Web / API / 遊戲系統

- 知識頁: [Web API 和遊戲系統](web-api-and-game-system.md)
- 結構頁: [專案架構總覽](project-architecture.md)
- 代碼入口:
  - [web/api](../../../web/api)
  - [web/portal](../../../web/portal)
  - [game](../../../game)

### 7. 開發與知識維護

- 知識頁:
  - [開發工具和流程](development-tools-and-workflow.md)
  - [開發工作流程](development-workflow.md)
  - [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md)
  - [Knowledge Link Audit](knowledge-link-audit.md)

## 怎麼用這張圖

### 情境 1：功能壞了，但不知道要先看哪裡

先從這一頁找到對應主題，再跳到該主題頁的代碼入口。

### 情境 2：只知道功能名，不知道是誰在控制

先看 [Discord Bot 系統詳解](discord-bot-system.md) 或 [專案架構總覽](project-architecture.md)，確認它屬於哪個 Bot / 模組，再下鑽到對應概念頁。

### 情境 3：要補知識頁，但怕補成孤島

先看 [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md) 與 [Knowledge Link Audit](knowledge-link-audit.md)，再決定要掛到哪個主題下面。

## 相關文檔

- [AI Fast Read](ai-fast-read.md)
- [專案架構總覽](project-architecture.md)
- [Discord Bot 系統詳解](discord-bot-system.md)
- [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md)