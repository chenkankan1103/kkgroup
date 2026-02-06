【大麻系統數據庫分析報告】

✅ 表結構狀態：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. cannabis_plants（種植記錄表）✅ 存在
   - 12 個欄位（ID、user_id、guild_id、channel_id、seed_type 等）
   - 已自動創建於 cannabis_cog.py 後台初始化

2. cannabis_inventory（庫存表）✅ 存在
   - 5 個欄位（ID、user_id、item_type、item_name、quantity）
   - 已自動創建於 cannabis_cog.py 後台初始化 

❌ 數據狀態：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- cannabis_plants：0 條記錄
- cannabis_inventory：0 條記錄

🔍 根本原因：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
大麻系統 **NOT** 是 Sheet-Driven（不依賴 Google Sheets）

與 users 表相比：
  users 表：
  ├─ 由 sheet_driven_db.py 管理
  ├─ 從 Google Sheets 同步
  └─ 表頭在 SHEET 中定義

  cannabis 表：
  ├─ 獨立自治系統
  ├─ 由 cannabis_farming.py 定義
  ├─ 由 cannabis_cog.py 自動初始化
  └─ 無需 Sheet 配置

✅ 解決方案：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【選項 A】推薦 - 直接向數據庫添加初始數據
✔️ 優點：
  - 無需 Sheet 配置
  - 用戶購買種子時自動添加庫存
  - 系統獨立，不依賴 Sheet

✔️ 步驟：
  1. 用戶使用 /種植 命令
  2. 購買種子 → 自動插入 cannabis_inventory
  3. 開始種植 → 自動插入 cannabis_plants
  4. 完全自動化，無需預初始化

❌ 缺點：
  - 用戶必須先有 KKcoin 購買種子
  - 沒有免費種子贈送機制

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【選項 B】集成 Sheet 同步
✔️ 優點：
  - 可在 Google Sheets 預設初始數據
  - 方便管理多個玩家的初始庫存
  - 與 users 表統一管理

✔️ 步驟：
  1. 在 google_sheets 中創建 'cannabis_plants' 和 'cannabis_inventory' 標籤
  2. 添加表頭和初始數據
  3. 修改 sheet_driven_db.py 支持多表管理
  4. 修改 sheet_sync_manager.py 添加同步邏輯

❌ 缺點：
  - 需要修改现有同步邏輯（相對複雜）
  - 維護成本增加

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【建議】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
選項 A（直接數據驅動）

原因：
1. 大麻系統是獨立購物系統，不是玩家屬性
2. 無需預初始化，用戶使用時自動生成
3. 無需修改 Sheet 驅動引擎

只需要：新增「初始贈送」功能
  - 新用戶加入時贈送 5 個基礎種子
  - 或者提供教學任務獲得首個種子

實現代碼位置：
  → sheet_sync_manager.py add_new_user() 函數
  → 添加：await add_inventory(user_id, '種子', '常規種', 5)
