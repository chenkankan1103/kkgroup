# Graph Report - .  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 4072 nodes · 8357 edges · 214 communities (193 shown, 21 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 422 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `739dd895`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- WelcomeFlow
- LockerEventListenerCog
- db_adapter.py
- ui/uibody.py
- ScamParkEvents
- KKCoin
- SheetDrivenDB
- PersistentViewBase
- AnimeTracker
- Ai
- WelcomeFlow
- refresh_knowledge_base.py
- ScamParkEvents
- SheetSyncManagerV2
- bot.py
- NewYearRedEnvelope
- UserPanel
- AnnouncementButtonView
- AnimeDatabase
- Interaction
- AntiAdvertising
- backup_20260205_1242/db_adapter.py
- leaderboard_manager.py
- fortress_system.py
- RankingStats
- PersistentEmbedView
- MarketTrends
- update_user_kkcoin
- FortressEnemyView
- status_dashboard.py
- AnimeScheduleTracker
- UserPanel
- SheetSyncManager
- Interaction
- get_central_reserve
- ScamHub
- ui/utils/__init__.py
- SheetSyncManager
- FortressDefenseCog
- cannabis_merchant_view_v2.py
- get_user_kkcoin
- SheetDrivenDB
- ExploreView
- AnimeVoteView
- update_locker_message
- fortress_defense.py
- log_monitor.py
- .logmonitor
- ShellAgentRunner
- Interaction
- AnimePushCore
- KnowledgeBase
- agent_tools.py
- BytesIO
- HospitalMerchant
- PersonalLockerCog
- SheetDrivenDB
- AutoDebugSystem
- GameUserSync
- ingest_knowledge.py
- ingest_knowledge_chroma.py
- GameUserSync
- KKCoin
- AI.py
- mutual_rescue.py
- get_all_users
- encoding_handler.py
- AutoErrorDetector
- archive_old_versions/sheet_sync_api.py
- PaperDollPreviewView
- LockerPanelView
- rpg-game.js
- AutonomousAgent
- ButtonInteraction
- work_system.py
- SelectFertilizerView
- get_user_stocks
- get_user
- paperdoll_manager.py
- webhook.py
- Any
- shopbot.py
- update_dashboard_logs
- uibot.py
- KKBotAgent
- LogMonitorEngine
- EnhancedPaperDollSystem
- stock_market.py
- FixExecutor
- SheetSyncManager
- Any
- GoogleSheetsSync
- .locker_init
- LockerPanelCog
- UserRecoveryCog
- CommandsManager
- prompt_function_calling.py
- LiteLLMClient
- GoogleAIClient
- memory_manager.py
- RoleExpiryManager
- KnowledgeVectorIndex
- .grant_temporary_role
- PaperdollMerchantSystem
- button
- ThreadsCookieMonitor
- auto_self_heal.py
- LeaderboardURLMonitor
- backup_20260205_1242/sheet_sync_api.py
- RoleExpirationManager
- StockMarket
- update_restart.py
- _log
- feature_usage.py
- logger.py
- unified_api.py
- _get_project_root
- _require_leader
- .kkcoin_admin
- NicknameIDManager
- .admin_refresh_all_lockers
- L1Fixer
- game_api.py
- .manual_debug_latest_incident
- ._upsert_summary_message
- work_cog.py
- feedback_cog.py
- StockSelectionView
- CharacterSetupCog
- LockerMaintenanceCog
- LockerCache
- auto_update_webhook.py
- discord_auth.py
- backup_20260205_1242/database.py
- LLMClient
- .__init__
- auto_update_webhook_v2.py
- webhook_logger.py
- scan_vm_state.py
- sheets.py
- AdminBot
- RainbowRole
- bot_manager.sh
- .admin_refresh_all_paperdolls
- NicknameReset
- .__init__
- IDDiagnosisCog
- auto_update_config.py
- FileEventHandler
- FileEventHandler
- FileEventHandler
- .kkcoin_admin
- work_function/database.py
- MemberSync
- L2Fixer
- ._button_callback
- AvatarReset
- start_api.sh
- main.js
- get_kkcoin_balance
- weekly_backup.py
- .parse_records
- knowledge_api.py
- .on_message
- .before_auto_sync_loop
- cannabis_unified.py
- .before_refresh_weekly_schedule
- server.py
- trigger_locker_refresh
- test_github_access
- trigger_git_push
- deploy_gcp.sh
- start_api_server.sh
- start_flask_api.sh
- start_game_api.sh
- deploy_restructure.sh
- grant-github-actions-iap-access.sh
- install-mutual-rescue-sudoers.sh
- update_tunnel_url_event.sh
- .__init__
- .get_sheet_headers
- .clean_virtual_accounts
- .ensure_db_schema
- .get_sheet_data_rows

## God Nodes (most connected - your core abstractions)
1. `PersistentViewBase` - 130 edges
2. `AnimeTracker` - 59 edges
3. `LogMonitorEngine` - 51 edges
4. `ScamParkEvents` - 48 edges
5. `AnimeDatabase` - 42 edges
6. `ScamParkEvents` - 41 edges
7. `get_user()` - 38 edges
8. `KKCoin` - 37 edges
9. `get_user_plants()` - 33 edges
10. `get_user_kkcoin()` - 33 edges

## Surprising Connections (you probably didn't know these)
- `CannabisFarmingAdapter` --uses--> `SheetDrivenDB`  [INFERRED]
  cogs/shop/merchant/cannabis_unified.py → archive/backups/backup_20260205_1242/sheet_driven_db.py
- `SheetSyncManager` --uses--> `SheetDrivenDB`  [INFERRED]
  web/blueprints/sheet_sync_manager.py → archive/backups/backup_20260205_1242/sheet_driven_db.py
- `GoogleSheetsSync` --uses--> `SheetSyncManager`  [INFERRED]
  cogs/common/google_sheets_sync.py → archive/backups/backup_20260205_1242/sheet_sync_manager.py
- `ButtonInteraction` --uses--> `EquipmentPreviewView`  [INFERRED]
  archive/backups/backup_20260205_1242/shop.py → cogs/shop/merchant/views.py
- `ButtonInteraction` --uses--> `EquipmentShopView`  [INFERRED]
  archive/backups/backup_20260205_1242/shop.py → cogs/shop/merchant/views.py

## Import Cycles
- None detected.

## Communities (214 total, 21 thin omitted)

### Community 0 - "WelcomeFlow"
Cohesion: 0.05
Nodes (35): GenderSelectView, InterestOnboardingView, PersistentWelcomeView, button, command, describe, Embed, has_permissions (+27 more)

### Community 1 - "LockerEventListenerCog"
Cohesion: 0.05
Nodes (49): LockerEventListenerCog, Embed, listener, Message, User, Locker Event Listener Cog 監聽置物櫃事件，根據事件類型進行局部或完整 embed 更新, 裝備更新事件監聽器 觸發： - 紙娃娃 hash 改變 → 重新請求 MapleStory API - 更新 appearance embed 及紙娃娃圖片, KK幣/經驗值更新事件監聽器 觸發： - 只更新 summary embed 的 KK幣/經驗值欄位 - 不涉及圖片、不請求 API (+41 more)

### Community 2 - "db_adapter.py"
Cohesion: 0.07
Nodes (68): add_to_central_reserve_digital_usd(), add_user_field(), add_user_xp(), async_batch_set_users(), async_get_all_users(), async_get_user(), async_get_user_by_field(), async_set_user() (+60 more)

### Community 3 - "ui/uibody.py"
Cohesion: 0.11
Nodes (26): add_inventory(), apply_fertilizer(), get_inventory(), get_user_plants(), harvest_plant(), plant_cannabis(), remove_inventory(), sell_cannabis() (+18 more)

### Community 4 - "ScamParkEvents"
Cohesion: 0.08
Nodes (18): before_loop, Embed, loop, Member, Message, Thread, 隨機觸發園區事件 - 每個使用者獨立計算觸發時間, 更新使用者KKCoin - 使用 db_adapter (+10 more)

### Community 5 - "KKCoin"
Cohesion: 0.06
Nodes (31): get_from_env(), initialize_database(), KKCoin, make_leaderboard_image(), before_loop, Embed, listener, loop (+23 more)

### Community 6 - "SheetDrivenDB"
Cohesion: 0.06
Nodes (27): CannabisFarmingAdapter, add_field(), get_db_instance(), get_field(), get_user(), Any, Connection, Row (+19 more)

### Community 7 - "PersistentViewBase"
Cohesion: 0.07
Nodes (21): KK園區 Shell Agent（ADK 架構 — Gemini Function Calling + Groq 備用）…, BuyFertilizerModal, BuySeedModal, CannabisMerchantView, FertilizerCategoryView, Interaction, Modal, SeedCategoryView (+13 more)

### Community 8 - "AnimeTracker"
Cohesion: 0.06
Nodes (17): AnimeTracker, error, loop, TextChannel, View, 包裝 _periodic_catchup_check，異常時自動重啟, 包裝 _schedule_dispatcher，異常時自動重啟, 檢查並發送動畫推送 - 委託給 PushCore (+9 more)

### Community 9 - "Ai"
Cohesion: 0.08
Nodes (22): Ai, Embed, listener, Member, 偷取使用者財物 - 包含 KKCoin 和物品, setup(), Ai, Embed (+14 more)

### Community 10 - "WelcomeFlow"
Cohesion: 0.09
Nodes (21): GenderSelectView, button, command, default_permissions, Embed, Interaction, listener, Member (+13 more)

### Community 11 - "refresh_knowledge_base.py"
Cohesion: 0.07
Nodes (43): acquire_lock(), get_taipei_timestamp(), get_webhook_url(), load_state(), main(), parse_analysis_sections(), release_lock(), run_step() (+35 more)

### Community 12 - "ScamParkEvents"
Cohesion: 0.09
Nodes (12): before_loop, command, has_permissions, loop, Member, Thread, 隨機觸發園區事件 - 每個使用者獨立計算觸發時間, 使用 Pollinations.ai 生成圖片 (+4 more)

### Community 13 - "SheetSyncManagerV2"
Cohesion: 0.06
Nodes (32): clean_virtual_accounts(), get_schema(), get_stats(), health_check(), internal_error(), not_found(), errorhandler, route (+24 more)

### Community 14 - "bot.py"
Cohesion: 0.07
Nodes (45): before_cleanup_expired_roles(), before_update_status(), _check_ready_timeout(), cleanup_expired_roles_loop(), _delete_stale_entry_point_commands_sync(), file_log(), find_and_load_extensions(), _get_memory_usage() (+37 more)

### Community 15 - "NewYearRedEnvelope"
Cohesion: 0.10
Nodes (28): _async_load_storage(), _async_save_storage(), _load_storage(), NewYearRedEnvelope, Bot, command, Embed, GuildChannel (+20 more)

### Community 16 - "UserPanel"
Cohesion: 0.09
Nodes (16): LockerPanelView, before_loop, button, Embed, Interaction, listener, loop, Member (+8 more)

### Community 17 - "AnnouncementButtonView"
Cohesion: 0.07
Nodes (19): Announcement, AnnouncementButtonView, FeedbackModal, Embed, Interaction, Modal, 更新紀錄按鈕回調 - 在公告區域顯示最近的 Git commits, 讀取最近的 git commits 返回格式: [ { 'hash': 'abc123...', 'author': 'John Doe', 'date':… (+11 more)

### Community 18 - "AnimeDatabase"
Cohesion: 0.08
Nodes (15): AnimeDatabase, datetime, 記錄匿名投票/評論 Args: video_sn: 集數序號 anime_sn: 動畫序號 message_id: Discord 訊息 ID（用於關聯統計）…, 獲取本週投票統計（按 animeSn 分組）, 根據時程表發送動畫推送（含時段匹配 + 並發鎖） 核心修復 (2026-07-25)： 1. 從週表取得該時段預期的 videoSn（而非…, Add missing columns to existing tables (schema migration), 獲取未設置視圖的消息（用於 bot 重啟時恢復）, 保存週表數據 - 先刪後插，保留已推送狀態 (pushed=1) 修復 (2026-07-28)：舊版 UPSERT 在 DB 已存在重複記錄時只更新… (+7 more)

### Community 19 - "Interaction"
Cohesion: 0.09
Nodes (12): ConfirmView, DressingRoomView, EditView, PreviewView, button, Interaction, 從允許的類別中隨機挑選一套裝備並直接顯示預覽, 更新並（重新）建立本頁的按鈕（名稱、分頁、搜索、返回）。 (+4 more)

### Community 20 - "AntiAdvertising"
Cohesion: 0.07
Nodes (20): AntiAdvertising, before_loop, listener, loop, Member, Message, 防廣告系統 Cog - 預防不當廣告和邀請連結 監聽消息，檢測廣告內容，並採取相應措施（刪除、禁言、踢出）, 檢測消息中的廣告內容 返回: (檢測到的類型, 匹配的內容) 或 None (+12 more)

### Community 21 - "backup_20260205_1242/db_adapter.py"
Cohesion: 0.09
Nodes (40): add_user_field(), add_user_xp(), batch_set_users(), count_users(), delete_user(), export_to_json(), export_to_sheet_format(), get_all_users() (+32 more)

### Community 22 - "leaderboard_manager.py"
Cohesion: 0.08
Nodes (32): fetch_avatar(), get_user_balance(), Message, 嘗試加載用戶頭像 成功: 返回 Image 對象 失敗: 返回 None（調用者應使用 placeholder）, setup(), update_user_balance(), _calculate_stock_value(), create_placeholder_avatar() (+24 more)

### Community 23 - "fortress_system.py"
Cohesion: 0.10
Nodes (35): _enemy_progress_index(), append_wave(), apply_defense_action(), apply_fortress_damage(), assign_tower_slot(), calculate_player_damage(), calculate_police_hp(), DefenseAction (+27 more)

### Community 24 - "RankingStats"
Cohesion: 0.07
Nodes (18): Embed, RankingStats, 每 6 小時從 Bahamut index API 同步一次 episode 統計數據， 確保 episode_statistics…, 每日直接從 API 檢查新番（取代週表模式）, 在預定時刻推送動畫通知 - 查詢真實 API 確認已上架集, 從 Bahamut API 獲取所有最近的動畫集（不限於今天的） 用於排行榜顯示 Returns: 所有最近的集列表，或 None 如果失敗, 直接從 index API (v3/index.php) 的 episode 物件中提取觀看/人氣數， 不需額外調用 video.php。 Bahamut…, 定時從 Bahamut index API 獲取最新的動畫列表， 記錄 per-episode 統計數據到 episode_statistics 表，… (+10 more)

### Community 25 - "PersistentEmbedView"
Cohesion: 0.07
Nodes (26): ButtonStyle, create_embed_with_view(), EmbedViewManager, PersistentEmbedView, Bot, Color, Embed, Enum (+18 more)

### Community 26 - "MarketTrends"
Cohesion: 0.08
Nodes (27): MarketTrends, before_loop, command, has_permissions, loop, 台灣 Google Trends 市場趨勢, 查詢當前台灣 Google Trends 熱門話題, 定時推送台灣 Google Trends 時間表： - 每小時自動推送一次 - 推送到 TRENDS_CHANNEL_ID (+19 more)

### Community 27 - "update_user_kkcoin"
Cohesion: 0.08
Nodes (16): CannabisBuyView, CannabisCog, CannabisPlantsView, CannabisSellView, PlantActionButton, Interaction, SeedButton, SeedSelectView (+8 more)

### Community 28 - "FortressEnemyView"
Cohesion: 0.09
Nodes (17): build_status_embed(), FortressEnemyView, InterestManageView, button, command, default_permissions, Embed, has_permissions (+9 more)

### Community 29 - "status_dashboard.py"
Cohesion: 0.07
Nodes (23): button, Interaction, LockerMaintenanceCog, before_loop, command, default_permissions, Interaction, loop (+15 more)

### Community 30 - "AnimeScheduleTracker"
Cohesion: 0.07
Nodes (20): Bot, Bahamut 動畫追蹤 Cog - 自動通知新上架集數 已重構為三個模組：Push/Core、Schedule Tracker、Ranking Stats, Setup 函數供 Discord.py 加載 Cog, setup(), Bahamut 動畫追蹤 - Push/Core 模組 負責通知發送、嵌入生成、視圖管理、訊息持久化, Bot, datetime, Discord.py 2.0+ 加載方式 - cog_load() 會自動被調用 (+12 more)

### Community 31 - "UserPanel"
Cohesion: 0.09
Nodes (14): before_loop, Embed, listener, loop, Member, Thread, User, 獲取角色圖片URL，委派給 paperdoll_manager (+6 more)

### Community 32 - "SheetSyncManager"
Cohesion: 0.08
Nodes (15): Any, 改進的 Google Sheets 同步系統 - 完全 SHEET 驅動 架構： 1. SHEET Row 1 = 完整欄位定義 (真實來源) 2.…, 從 SHEET 數據同步到數據庫 (主方法) Args: headers: SHEET 表頭 (Row 1 或 Row 2) rows: SHEET 數據行…, 將 SHEET 數據轉換為記錄字典列表 (向後相容版本), 內部方法：將 SHEET 數據轉換為記錄字典列表 流程： 1. 自動偵測 user_id 欄位 (如果尚未識別) 2. 逐行處理，跳過無效 user_id…, 將記錄同步到 DB Returns: {'inserted': n, 'updated': n, 'errors': n, 'total_parsed': n}, 舊版本的 sync_records 方法 (向後相容) Returns: (updated, inserted, errors), 自動偵測哪一欄最有可能是 user_id (Discord 用戶 ID) 啟發式方法： - Discord user_id 通常是 18-20 位的數字 -… (+7 more)

### Community 33 - "Interaction"
Cohesion: 0.12
Nodes (7): EquipmentPreviewView, ProductCategoryView, PurchaseConfirmView, button, Interaction, SlotMachineView, TryOnResultView

### Community 34 - "get_central_reserve"
Cohesion: 0.10
Nodes (30): _generate_hex_noise(), MoneyLaunderingView, 生成虛構的十六進制位址，營造資產拆分效果 Args: count: 生成數量 Returns: 十六進制位址列表, 顯示金流斷點的進度動畫 - 傳輸鏈UI設計, 創建傳輸鏈進度embed - 色彩策略 + 視覺增強, add_to_central_reserve(), get_central_reserve(), get_dynamic_fee_rate() (+22 more)

### Community 35 - "ScamHub"
Cohesion: 0.10
Nodes (16): _get_db_connection(), command, datetime, has_permissions, Interaction, listener, 從 cache 或 API 還原語音頻道對象。, 返回頻道中的成員清單。 注意：使用 fetch_channel 確保獲取最新狀態，避免依賴過期緩存。 (+8 more)

### Community 36 - "ui/utils/__init__.py"
Cohesion: 0.09
Nodes (28): calculate_harvest_value(), create_plant_embed(), format_plant_progress(), 創建植物狀態的embed字段 Args: plant (dict): 植物數據 idx (int, optional): 植物編號 Returns:…, 計算收割價值 Args: plant (dict): 植物數據 Returns: dict: 包含數量、單價、總價的字典, 格式化植物成長進度 Args: plant (dict): 植物數據 Returns: str: 格式化的進度字符串, 驗證植物操作 Args: user_id (int): 用戶ID plant_id (int): 植物ID operation_type (str):…, validate_plant_operation() (+20 more)

### Community 37 - "SheetSyncManager"
Cohesion: 0.08
Nodes (14): Any, 從 SHEET 數據同步到數據庫 (主方法) Args: headers: SHEET 表頭 (Row 1 或 Row 2) rows: SHEET 數據行…, 將 SHEET 數據轉換為記錄字典列表 (向後相容版本), 內部方法：將 SHEET 數據轉換為記錄字典列表 流程： 1. 自動偵測 user_id 欄位 (如果尚未識別) 2. 逐行處理，跳過無效 user_id…, 將記錄同步到 DB（支援去重） Returns: {'inserted': n, 'updated': n, 'errors': n,…, 初始化同步管理器 Args: db_path: SQLite 數據庫文件路徑, 舊版本的 sync_records 方法 (向後相容) Returns: (updated, inserted, errors), 自動偵測哪一欄最有可能是 user_id (Discord 用戶 ID) 啟發式方法： - Discord user_id 通常是 18-20 位的數字 -… (+6 more)

### Community 38 - "FortressDefenseCog"
Cohesion: 0.11
Nodes (14): AppCommandError, _clear_battle_message_state(), _clear_env_message_state(), _clear_settlement_message_state(), FortressDefenseCog, before_loop, datetime, error (+6 more)

### Community 39 - "cannabis_merchant_view_v2.py"
Cohesion: 0.12
Nodes (14): FertilizerSelectView, button, Exception, Interaction, QuantitySelectView, 黑市商人 - 大麻系統整合版（在同一個embed中編輯）, 出售大麻 - 使用 Select Menu, 上報用戶交互中的錯誤到 logging 系統（會自動轉發到 Discord） (+6 more)

### Community 40 - "get_user_kkcoin"
Cohesion: 0.11
Nodes (9): get_user_equipment(), get_user_kkcoin(), ItemDetailView, View, ButtonInteraction, command, File, 處理拉霸機下注 - 統一更新同一個 Embed（作為 ButtonInteraction 的方法） (+1 more)

### Community 41 - "SheetDrivenDB"
Cohesion: 0.11
Nodes (12): Connection, Row, 確保系統列存在（只在初始化時調用，在同一連接中使用）, 確保表中存在所有欄位 如果 SHEET 中有新欄位，自動添加到 DB Args: headers: SHEET 表頭列表 (來自 Row 1), 根據欄位名推測 SQL 類型 Args: header: 欄位名稱 Returns: SQL 類型字符串, 獲取用戶完整數據 Args: user_id: 用戶 ID Returns: 用戶數據字典，或 None 如果用戶不存在, 更新用戶數據 (INSERT OR REPLACE) Args: user_id: 用戶 ID data: 要更新的數據 {'field': value,…, 初始化數據庫引擎 Args: db_path: SQLite 數據庫文件路徑 (+4 more)

### Community 42 - "ExploreView"
Cohesion: 0.15
Nodes (12): CannabisMerchantViewV2, get_role_id(), 獲取角色ID，優先使用環境變數，否則使用預設值, update_user_equipment(), process_slot_machine_bet(), 處理拉霸機下注 返回: (結果列表, 淨變化, 消息, 流入金庫的金額) 金庫流入邏輯： - 玩家虧損 100% 流入金庫 - 玩家盈利時，金庫不扣費, CustomAmountModal, EquipmentShopView (+4 more)

### Community 43 - "AnimeVoteView"
Cohesion: 0.08
Nodes (14): AnimeVoteView, datetime, Embed, Interaction, Message, 生成動畫 embed - 委託給 PushCore, 記錄投票 - 委託給 RankingStats, 獲取投票統計 - 委託給 RankingStats (+6 more)

### Community 44 - "update_locker_message"
Cohesion: 0.11
Nodes (24): AdminCommands, command, has_permissions, Interaction, 管理員命令：手動更新論壇中所有活躍用戶的置物櫃embed, setup(), _build_locker_view(), generate_canonical_locker_embed() (+16 more)

### Community 45 - "fortress_defense.py"
Cohesion: 0.16
Nodes (24): build_battle_embed(), _build_enemy_status_field(), build_settlement_embed(), _build_td_map(), _chunk_lines_for_embed(), _find_slot_owner_name(), _get_fortress_channel_id(), _get_map_layout() (+16 more)

### Community 46 - "log_monitor.py"
Cohesion: 0.13
Nodes (17): _build_incident_signature(), _build_local_fallback_summary(), _current_tw_datetime(), _estimate_severity_from_lines(), _extract_relevant_journal_lines(), _extract_relevant_lines(), _extract_severity(), _format_tw_time() (+9 more)

### Community 47 - ".logmonitor"
Cohesion: 0.12
Nodes (15): _has_admin_access(), _load_known_debugs(), LogMonitor, LogMonitorSummaryView, Bot, button, choices, Color (+7 more)

### Community 48 - "ShellAgentRunner"
Cohesion: 0.11
Nodes (15): ConfirmCommandView, Bot, command, describe, Interaction, TextChannel, ADK 風格 Shell Agent 執行器。 Agentic Loop： Think（LLM 決定指令） → Act（確認 + 執行） →…, 只取 run_terminal 的工具規格，給 Gemini 使用。 (+7 more)

### Community 49 - "Interaction"
Cohesion: 0.17
Nodes (12): defer_ephemeral_or_ignore(), Embed, Interaction, Acknowledge the interaction unless Discord has already expired it., 股票詳細視圖 - 有買入、賣出、返回按鈕及時間框架選擇, 使用 followup 發送商品選擇視圖（用於已 defer 的情況）, 無 interaction 情境下直接更新操盤室 embed（例如交易完成後刷新）, 更新操盤室 Embed（交易後刷新，使用 stored message） (+4 more)

### Community 50 - "AnimePushCore"
Cohesion: 0.09
Nodes (13): AnimePushCore, Any, Embed, Path, TextChannel, View, Bahamut 動畫追蹤 - Push/Core 核心功能, 設定 View 生成工廠函數 Args: factory: async function(episode: dict) -> discord.ui.View (+5 more)

### Community 51 - "KnowledgeBase"
Cohesion: 0.13
Nodes (15): Cursor, build_memory_context(), _content_hash(), ensure_db_exists(), _ensure_knowledge_schema(), estimate_tokens(), initialize_memory_system(), KnowledgeBase (+7 more)

### Community 52 - "agent_tools.py"
Cohesion: 0.11
Nodes (23): batch_replace_code(), clear_maplestory_equipment(), get_bot_status(), get_maplestory_equipment(), get_maplestory_total_power(), get_top_kkcoin_leaderboard(), list_maplestory_equipment_slots(), query_vm_logs() (+15 more)

### Community 53 - "BytesIO"
Cohesion: 0.09
Nodes (21): BytesIO, create_chart_image(), create_colorful_leaderboard_image(), create_comprehensive_dashboard(), create_weekly_mvp_image(), create_weekly_stats_image(), KK幣排行榜視覺化增強模組 支援：多種模式、彩色排名、圖表展示, 創建圖表（長條圖或圓餅圖） Args: members_data: [(member, kkcoin), ...] chart_type: 'bar' or… (+13 more)

### Community 54 - "HospitalMerchant"
Cohesion: 0.17
Nodes (8): HospitalMerchant, PersistentStaminaView, Embed, Interaction, listener, 監聽用戶完全恢復（來自 recovery_loop 的自動恢復）, setup(), StaminaItemView

### Community 55 - "PersonalLockerCog"
Cohesion: 0.11
Nodes (10): PersonalLockerCog, before_loop, datetime, Embed, listener, loop, User, 個人置物櫃 - 大麻種植管理 + 伺服器面板 (+2 more)

### Community 56 - "SheetDrivenDB"
Cohesion: 0.13
Nodes (10): Connection, Row, 根據欄位名推測 SQL 類型 Args: header: 欄位名稱 Returns: SQL 類型字符串, 獲取用戶完整數據 Args: user_id: 用戶 ID Returns: 用戶數據字典，或 None 如果用戶不存在, 更新用戶數據 (INSERT OR REPLACE) Args: user_id: 用戶 ID data: 要更新的數據 {'field': value,…, 初始化數據庫引擎 Args: db_path: SQLite 數據庫文件路徑, 導出數據庫數據為 SHEET 格式 Returns: (headers, rows) 元組, 將 SQLite Row 轉換為字典，解析 JSON 字段 (+2 more)

### Community 57 - "AutoDebugSystem"
Cohesion: 0.15
Nodes (13): _artifact_key_from_signature(), AutoDebugSystem, _build_incident_signature(), _infer_service_hint(), main(), _normalize_incident_signature(), 自動 Debug 系統 監控系統錯誤，自動觸發 GitHub Actions 進行 AI 分析和修復, GitHub Actions 只做升級處理，而不是主處理路徑。 (+5 more)

### Community 58 - "GameUserSync"
Cohesion: 0.14
Nodes (8): GameUserSync, main(), parse_datetime_to_timestamp(), any, 找到 user_id 對應的 Sheet 行號, 基於 sync_flag 標記的遊戲用戶資料同步, 將時間戳轉換為 ISO 字串格式，修復類型檢查問題, timestamp_to_iso_string()

### Community 59 - "ingest_knowledge.py"
Cohesion: 0.19
Nodes (24): build_markdown_chunks(), build_python_chunks(), derive_category(), derive_topic(), discover_markdown_files(), discover_python_files(), extract_related_topics(), get_chroma_client() (+16 more)

### Community 60 - "ingest_knowledge_chroma.py"
Cohesion: 0.19
Nodes (24): build_markdown_chunks(), build_python_chunks(), derive_category(), derive_topic(), discover_markdown_files(), discover_python_files(), extract_related_topics(), get_chroma_client() (+16 more)

### Community 61 - "GameUserSync"
Cohesion: 0.14
Nodes (8): GameUserSync, main(), parse_datetime_to_timestamp(), any, 找到 user_id 對應的 Sheet 行號, 基於 sync_flag 標記的遊戲用戶資料同步, 將時間戳轉換為 ISO 字串格式，修復類型檢查問題, timestamp_to_iso_string()

### Community 62 - "KKCoin"
Cohesion: 0.15
Nodes (13): fetch_avatar(), get_from_env(), initialize_database(), KKCoin, make_leaderboard_image(), before_loop, loop, 等待 bot 準備完成，並在啟動時查找/創建排行榜 (+5 more)

### Community 63 - "AI.py"
Cohesion: 0.12
Nodes (14): AIResponse, build_memory_context(), DialogueMemory, initialize_memory_system(), KnowledgeBase, KnowledgeVectorIndex, Bot, listener (+6 more)

### Community 64 - "mutual_rescue.py"
Cohesion: 0.16
Nodes (16): 收集 systemd/journal 異常，並優先嘗試本地自癒。, CompletedProcess, _artifact_key_from_signature(), _attempt_local_service_heal(), _decide_repair_action(), _dispatch_repair_request(), ensure_mutual_rescue_monitor(), _extract_target_file() (+8 more)

### Community 65 - "get_all_users"
Cohesion: 0.12
Nodes (15): get_all_users(), 取得所有用戶資料（用於重建持久化 View）, LockerTasks, 置物櫃相關的後台任務（事件驅動型增量同步）, 初始化回填 locker_message_id, batch_fill_missing_fields(), convert_default_to_random_characters(), find_users_with_missing_character_data() (+7 more)

### Community 66 - "encoding_handler.py"
Cohesion: 0.11
Nodes (21): Logger, get_taiwan_time(), init_all(), initialize_encoding(), json_dumps_console_safe(), print_json_safe(), print_safe(), 自定義日誌格式化器，支持台灣時區和 UTF-8 編碼 (+13 more)

### Community 67 - "AutoErrorDetector"
Cohesion: 0.17
Nodes (7): _artifact_key_from_signature(), AutoErrorDetector, main(), _normalize_incident_signature(), 標準化時間戳，避免非 ISO 格式導致冷卻判斷失敗, 觸發 GitHub Actions 進行分析、修復與推送。, 單次檢查，適合 GitHub Actions 或一次性任務。

### Community 68 - "archive_old_versions/sheet_sync_api.py"
Cohesion: 0.17
Nodes (22): api_add_field(), api_clean_virtual(), api_export_db(), api_get_field(), api_get_user(), api_health(), api_set_field(), api_stats() (+14 more)

### Community 69 - "PaperDollPreviewView"
Cohesion: 0.12
Nodes (4): CategoryItemSelectView, ItemIDInputModal, PaperDollPreviewView, select

### Community 70 - "LockerPanelView"
Cohesion: 0.14
Nodes (12): LockerPanelView, button, Interaction, 從永久置物櫃面板打開性別選擇（立即 defer，避免 3 秒超時）, 根據 self.user_id 或 thread_id 獲取置物櫃所有者 user_id - 使用非同步 DB 查詢避免阻塞, 返回到主選項 - 如果正在編輯的是論壇中的永久置物櫃訊息（DB 中的 locker_message_id）， 使用…, button, Interaction (+4 more)

### Community 71 - "rpg-game.js"
Cohesion: 0.18
Nodes (19): attachEventListeners(), buyItem(), changePaperdollPart(), formatNumber(), loadPaperdollShop(), loadUserData(), loadUserInventory(), openBattle() (+11 more)

### Community 72 - "AutonomousAgent"
Cohesion: 0.14
Nodes (7): _AgentMemory, AutonomousAgent, DiscordNotifier, Simple JSON‑based short‑term + long‑term memory., ReAct‑style loop: Observation → LLM (thought+tool+args) → Execute → Observation…, Return a prompt that asks the LLM to output a JSON action., error_batch: list of dicts as returned by collect_errors(). We process the…

### Community 73 - "ButtonInteraction"
Cohesion: 0.15
Nodes (6): ButtonInteraction, command, File, Interaction, 處理拉霸機下注 - 統一更新同一個 Embed（作為 ButtonInteraction 的方法）, setup()

### Community 74 - "work_system.py"
Cohesion: 0.19
Nodes (19): 更新用戶多個欄位 示例: update_user(user_id, xp=100, level=5, title='武士'), update_user(), assign_role(), check_level_up(), create_level_up_embed(), create_progress_bar(), create_work_embed(), generate_daily_checkin_story() (+11 more)

### Community 75 - "SelectFertilizerView"
Cohesion: 0.15
Nodes (6): 創建作物資訊embed和view（CropOperationView 類方法）, HarvestResultView, button, Interaction, SelectFertilizerView, SelectPlantForFertilizerView

### Community 76 - "get_user_stocks"
Cohesion: 0.17
Nodes (20): add_stock_position(), close_stock_position(), get_user_stocks(), 獲取使用者持有的股票列表 Args: user_id: 用戶 ID Returns: [{'symbol': '2330.TW', 'shares': 10,…, 增加或更新使用者的股票持倉（買入） Args: user_id: 用戶 ID symbol: 股票代號（例如 '2330.TW'） shares: 買入數量…, 減少或平掉使用者的股票持倉（賣出） Args: user_id: 用戶 ID symbol: 股票代號 shares: 賣出數量 price: 賣出價格…, execute_trade(), fetch_price() (+12 more)

### Community 77 - "get_user"
Cohesion: 0.18
Nodes (10): get_user(), Any, 獲取用戶完整資料 Args: user_id: 用戶 ID Returns: 用戶資料字典，或 None, get_bot_type(), log_error(), command, Interaction, Unified error logging function that logs to both console and Discord channel.… (+2 more)

### Community 78 - "paperdoll_manager.py"
Cohesion: 0.15
Nodes (19): _apply_preview_item(), build_api_url(), _extract_gender_from_name(), get_defaults(), get_random(), infer_gender_from_appearance(), _load_fashion_db(), Any (+11 more)

### Community 79 - "webhook.py"
Cohesion: 0.15
Nodes (19): check_rate_limit(), execute_git_pull(), github_webhook(), github_webhook_head(), log_audit(), notify_discord(), route, 驗證 GitHub webhook 簽名 (強制檢查版本) Args: payload_body (bytes): webhook 的原始 body… (+11 more)

### Community 80 - "Any"
Cohesion: 0.20
Nodes (13): add_field(), get_db_instance(), get_field(), get_user(), Any, Sheet-Driven Database Engine - 完全以 SHEET 為主導的數據庫系統 核心概念： 1. SHEET Row 1 =…, 獲取用戶特定欄位的值 Args: user_id: 用戶 ID field: 欄位名 default: 預設值 Returns: 欄位值, 更新用戶特定欄位 Args: user_id: 用戶 ID field: 欄位名 value: 新值 Returns: 是否成功 (+5 more)

### Community 81 - "shopbot.py"
Cohesion: 0.18
Nodes (17): before_update_status(), _check_ready_timeout(), file_log(), find_and_load_extensions(), main(), on_connect(), on_disconnect(), on_interaction() (+9 more)

### Community 82 - "update_dashboard_logs"
Cohesion: 0.12
Nodes (19): loop, update_status(), loop, update_status(), clamp_embed_description(), create_logs_embed(), get_message_id(), get_systemd_logs() (+11 more)

### Community 83 - "uibot.py"
Cohesion: 0.18
Nodes (17): before_update_status(), _check_ready_timeout(), file_log(), find_and_load_extensions(), main(), on_connect(), on_disconnect(), on_interaction() (+9 more)

### Community 84 - "KKBotAgent"
Cohesion: 0.15
Nodes (8): AgentSession, KKBotAgent, 管理每個用戶的短期 Session 記憶（最近 N 輪，滑動窗口）。, 組合歷史對話 + 新訊息，返回 Gemini contents 格式。, ADK 風格 Agent。 Agentic Loop（官方 Sequential Workflow）： Think → Act（工具）→…, 主入口：給定用戶 ID 和訊息，回傳 AI 回應文字。, 官方 Agentic Loop：Think → Act → Observe → Think... → Reply, 判斷是否需要工具（避免普通聊天帶上工具規格浪費 token）。

### Community 85 - "LogMonitorEngine"
Cohesion: 0.20
Nodes (4): _artifact_key_from_signature(), LogMonitorEngine, journalctl -f 事件驅動引擎。 - 持續讀取日誌流（asyncio subprocess） - Debounce 累積後呼叫 LLM 分析 -…, _truncate_text()

### Community 86 - "EnhancedPaperDollSystem"
Cohesion: 0.20
Nodes (7): EnhancedPaperDollSystem, Embed, File, Interaction, 構建 API URL，現已委派給 paperdoll_manager, 創建對比效果的 embed（當前 vs 試穿）, 構建角色裝備列表 - 支援所有 25 個部件類別

### Community 87 - "stock_market.py"
Cohesion: 0.15
Nodes (16): AssetClass, _create_progress_bar(), _get_system_log(), Enum, 創建科技感進度條 Args: percent: 進度百分比 (0-100) width: 進度條寬度 Returns: 格式化的進度條字符串, 根據進度百分比生成擬真的系統日誌 Args: percent: 進度百分比 amount: 金額 dynamic_fee_rate: 動態手續費率…, build_quickchart_url(), create_quickchart_short_url() (+8 more)

### Community 88 - "FixExecutor"
Cohesion: 0.15
Nodes (12): backup_file(), FixExecutor, list_backups(), Path, Thin wrapper around _restart_service for the agent., Thin wrapper around _run_command for the agent (whitelisted inside)., 執行修復操作（備份 → 修復 → 驗證 → 回滾）, 套用代碼修復（含完整檔案 AST 校驗：AI 給片段會被拒並還原） (+4 more)

### Community 89 - "SheetSyncManager"
Cohesion: 0.17
Nodes (6): Any, 從 SHEET 數據同步到數據庫 (主方法) Args: headers: SHEET 表頭 (Row 1 或 Row 2) rows: SHEET 數據行…, 將記錄同步到 DB（支援去重） Returns: {'inserted': n, 'updated': n, 'errors': n,…, 舊版本的 sync_records 方法 (向後相容) Returns: (updated, inserted, errors), 生成 SHEET 內容的 hash (用於檢測變化) 只對關鍵欄位計算, SheetSyncManager

### Community 90 - "Any"
Cohesion: 0.20
Nodes (13): add_field(), get_db_instance(), get_field(), get_user(), Any, Sheet-Driven Database Engine - 完全以 SHEET 為主導的數據庫系統 核心概念： 1. SHEET Row 1 =…, 獲取用戶特定欄位的值 Args: user_id: 用戶 ID field: 欄位名 default: 預設值 Returns: 欄位值, 更新用戶特定欄位 Args: user_id: 用戶 ID field: 欄位名 value: 新值 Returns: 是否成功 (+5 more)

### Community 91 - "GoogleSheetsSync"
Cohesion: 0.15
Nodes (9): GoogleSheetsSync, loop, 每 24 小時將資料庫匯出到 SHEET（供管理員查閱）, 內部同步方法：Google Sheet → 資料庫（SHEET 主導） 使用 SheetSyncManager 自動化： 1. 讀取 SHEET 表頭（第 2…, Google Sheets 與 SQLite 資料庫雙向同步工具 (Slash 指令版本), 內部匯出方法：資料庫 → Google Sheet, 初始化 Google Sheets 連接（同步版本，用於非異步上下文）, 每 24 小時檢查 SHEET 是否有手動編輯，若有則同步到資料庫 (+1 more)

### Community 92 - ".locker_init"
Cohesion: 0.22
Nodes (11): LockerAdminCog, command, describe, has_permissions, Interaction, User, 置物櫃管理員命令 - 檢查和初始化會員置物櫃 功能： 1. /locker_check <user> - 檢查特定會員是否有置物櫃 2.…, 為沒有置物櫃的會員初始化，並自動建立 thread 和置物櫃頁面 (+3 more)

### Community 93 - "LockerPanelCog"
Cohesion: 0.16
Nodes (7): LockerPanelCog, before_loop, datetime, Embed, loop, 置物櫃實時面板系統 - 自動更新的置物櫃概況 功能： 1. 維護一個實時更新的「置物櫃概況」訊息 2. 每30分鐘自動更新一次統計 3.…, setup()

### Community 94 - "UserRecoveryCog"
Cohesion: 0.15
Nodes (7): before_loop, listener, loop, 處理所有用戶的自動回復（優化版本 - 使用批量操作）, 確保資料庫結構正確 - db_adapter 會自動管理欄位, setup(), UserRecoveryCog

### Community 95 - "CommandsManager"
Cohesion: 0.22
Nodes (5): CommandsManager, main(), Any, 解析可供 subprocess 使用的 gcloud 執行命令。, resolve_gcloud_command()

### Community 96 - "prompt_function_calling.py"
Cohesion: 0.14
Nodes (16): dispatch_tool(), get_gemini_tools_spec(), 自動生成 Gemini Function Calling 所需的工具清單 JSON。 只要在此文件用 @register_tool 新增函數， Gemini…, 工具分發器：根據名稱執行對應工具函數，並注入 caller_id。 此函數由 AI.py 的工具分發邏輯呼叫， 不應由外部直接使用（請透過 AI.py 的…, build_system_prompt_with_tools(), execute_extracted_calls(), extract_function_calls(), extract_response_without_calls() (+8 more)

### Community 97 - "LiteLLMClient"
Cohesion: 0.18
Nodes (8): get_usage_stats(), LiteLLMClient, LLMClient, Any, KK園區 AI Client (LiteLLM 版本) =============================================== 使用…, 降級到傳統 API 呼叫 - 直接實現避免循環導入, 統一的 AI 客戶端，使用 LiteLLM 管理多個提供商, test_ai_client()

### Community 98 - "GoogleAIClient"
Cohesion: 0.16
Nodes (11): call_google_ai(), get_google_client(), GoogleAIClient, Google Generative AI API 封装模块 提供與 Groq OpenAI 相容的介面, Google Generative AI 用戶端, 簡便函數：調用 Google Generative AI, 使用 Google AI 翻譯文本 Args: text: 要翻譯的文本 Returns: 翻譯結果或原文本, 使用指定 key 呼叫 Google Generative AI。 (+3 more)

### Community 99 - "memory_manager.py"
Cohesion: 0.15
Nodes (8): DialogueMemory, initialize_memory_system(), KnowledgeBase, MemoryManager, PersonalityMemory, AI 記憶管理指令 允許用戶設置 AI 角色、添加知識、管理記憶, setup(), PersonalityMemory

### Community 100 - "RoleExpiryManager"
Cohesion: 0.14
Nodes (6): before_loop, loop, 移除到期的身份組 Returns: bool: 是否成功移除, 記錄身份組購買 Args: user_id: 用戶 ID guild_id: 伺服器 ID role_id: 身份組 ID role_name: 身份組名稱…, RoleExpiryManager, setup()

### Community 101 - "KnowledgeVectorIndex"
Cohesion: 0.26
Nodes (4): KnowledgeVectorIndex, Any, Path, 使用 TF-IDF 建立本地語意檢索索引。

### Community 102 - ".grant_temporary_role"
Cohesion: 0.20
Nodes (9): EnhancedRoleExpirationManager, Bot, command, describe, Interaction, Role, User, 給予用戶臨時身分 Args: user: 目標用戶 role: 要給予的身分 duration_days: 持續天數 (+1 more)

### Community 103 - "PaperdollMerchantSystem"
Cohesion: 0.17
Nodes (8): PaperdollMerchantCog, PaperdollMerchantSystem, 穿著紙娃娃部位 返回: (成功, 訊息), 保存紙娃娃搭配方案 items: 包含 face, hair, skin, top, bottom, shoes 的字典, 購買紙娃娃部位 返回: (成功, 訊息), setup(), get_user_inventory(), 獲取用戶的紙娃娃部位庫存 返回格式： { "user_id": "user_id", "inventory": { "face": [20000,…

### Community 104 - "button"
Cohesion: 0.23
Nodes (4): AssetClassSelectionView, PortfolioDetailView, button, TradeModal

### Community 105 - "ThreadsCookieMonitor"
Cohesion: 0.16
Nodes (10): CookieExpireNotifier, command, has_permissions, 監控 Threads Cookie 狀態的 Cog, 檢查 Threads Cookie 狀態（管理員命令） Usage: /cookie_status, 手動觸發 Cookie 更新流程（管理員命令） Usage: /update_cookies, 初始化通知器 Args: bot_token: Discord Bot Token admin_channel_id: 管理員頻道 ID (整數), 發送 Cookie 失效警告到 Discord Args: status: 失效狀態 ("EXPIRED", "MISSING",… (+2 more)

### Community 106 - "auto_self_heal.py"
Cohesion: 0.18
Nodes (12): collect_errors(), _extract_file_path_from_traceback(), GitManager, _is_noise(), _load_env(), _load_state(), _normalize_timestamp(), datetime (+4 more)

### Community 107 - "LeaderboardURLMonitor"
Cohesion: 0.15
Nodes (8): after_loop, LeaderboardURLMonitor, before_loop, loop, 提交 config.json 變更到 Git 需要在 .env 中設置 ENABLE_LEADERBOARD_GIT_COMMIT=true, 自動監控排行榜 Discord CDN URL 並更新到 config.json, 每小時檢查一次 Discord CDN URL 只在 URL 改變時才輸出日誌, setup()

### Community 108 - "backup_20260205_1242/sheet_sync_api.py"
Cohesion: 0.21
Nodes (14): api_add_field(), api_clean_virtual(), api_get_field(), api_get_user(), api_health(), api_set_field(), api_stats(), api_sync_sheet() (+6 more)

### Community 109 - "RoleExpirationManager"
Cohesion: 0.17
Nodes (8): get_manager(), Client, 角色過期管理系統 - 持久化存儲購買的臨時角色 - 機器人啟動時自動清理過期角色 - 定期檢查（每小時）並自動移除已過期角色 重要說明： -…, 獲取所有已過期的角色 Returns: 列表，每項為 (user_id, guild_id, role_id, role_name), 標記角色過期記錄已處理（不會禁止用戶重新購買） 此方法只是在數據庫中標記 is_active=0，表示該過期記錄已被清理。…, 清理所有過期的角色 Args: bot: Discord bot 客戶端 Returns: 已移除的角色數量, 保存臨時角色購買記錄 - 支持時間疊加 如果用戶已擁有該角色且未過期，新購買的時間會疊加到現有期限 如果角色已過期或不存在，則以購買時間作為起點 Args:…, RoleExpirationManager

### Community 110 - "StockMarket"
Cohesion: 0.22
Nodes (10): GuildChannel, listener, 保存市場 message ID 數據 同時嘗試同步更新環境變數（.env 文件），讓部署環境可以直接讀取。, 設置市場消息（在 setup() 中由異步任務調用）, 嘗試取得市場頻道：先用緩存，沒有再發 API 請求, 更新市場主 Embed（編輯現有訊息或發送新訊息）, save_market_message_data(), setup() (+2 more)

### Community 111 - "update_restart.py"
Cohesion: 0.30
Nodes (14): check_git_updates(), get_git_update_details(), log(), main(), pull_git_updates(), 拉取 git 更新（保留本地 user_data.db）, 檢查是否應該執行更新檢查（輕量檢查，5 分鐘間隔）, 檢查是否應該執行 git fetch（重型 API 調用，30 分鐘間隔以減少出站流量） (+6 more)

### Community 112 - "_log"
Cohesion: 0.33
Nodes (6): classify_error(), _log(), main(), 把單一修復檔提交到 auto-self-heal 分支並開 PR。, 分類錯誤等級。 Returns: (level, error_type, description) level: "L1", "L2", "L3", SelfHealDaemon

### Community 113 - "feature_usage.py"
Cohesion: 0.29
Nodes (13): main(), build_usage_markdown(), _component_type_name(), ensure_feature_usage_db(), extract_interaction_event(), InteractionEvent, normalize_feature_name(), _normalize_token() (+5 more)

### Community 114 - "logger.py"
Cohesion: 0.20
Nodes (12): discord_print(), discord_sender(), DiscordLoggingHandler, handle_exception(), hash_error(), 背景執行緒:發送訊息 (錯誤優先, 正常訊息次之), 模擬 print(),加上 BOT 標籤,同時送出, 自定義 logging handler，將日誌發送到 Discord (+4 more)

### Community 115 - "unified_api.py"
Cohesion: 0.22
Nodes (14): handle_bad_request(), handle_exception(), handle_not_found(), health_check(), index(), proxy_paperdoll(), errorhandler, route (+6 more)

### Community 116 - "_get_project_root"
Cohesion: 0.14
Nodes (14): analyze_code_changes(), _build_local_code_index(), diagnose_problem(), generate_fix_suggestion(), get_git_status(), _get_project_root(), Any, 🚀 建立本地代碼索引 - 快速搜尋專用 在 GCP VM 上首次運行時建立，後續使用快取。 包含：文件位置、關鍵詞、函數/類名稱、導入關係等 (+6 more)

### Community 117 - "_require_leader"
Cohesion: 0.14
Nodes (14): automate_workflow(), get_operation_log(), 讀取專案目錄下的 .py 檔案內容。支持多種搜尋方式： 1. 完整路徑：'commands/AI.py' 2. 檔名：'shop.py' 或…, 修改專案檔案、語法檢查、提交到 Git。 執行流程： 1️⃣ 權限驗證（已透過裝飾器檢查） 2️⃣ 路徑安全檢查 3️⃣ Python…, 查詢操作日誌（審計用） Args: limit (int): 最近多少條日誌 caller_id (int): 呼叫者 ID Returns: str:…, 智能代碼搜尋 - 精準定位相關代碼，避免誤觸。 特點： 1️⃣ 精準搜索：支持正則表達式，過濾無關行 2️⃣ 上下文限制：按功能模塊縮小搜尋範圍 3️⃣…, 工作流自動化 - 自主完成完整開發任務。 支持的 workflow_type： • fix-bug - 修復 Bug • update-constant -…, 裝飾器：檢查是否為管理員，非管理員直接返回拒絕訊息。 自動記錄嘗試訪問的操作。 使用方式： @_require_leader def… (+6 more)

### Community 118 - ".kkcoin_admin"
Cohesion: 0.27
Nodes (8): get_user_balance(), choices, command, default_permissions, describe, Interaction, Member, TextChannel

### Community 119 - "NicknameIDManager"
Cohesion: 0.27
Nodes (8): NicknameIDManager, Bot, command, describe, has_permissions, Interaction, Member, setup()

### Community 120 - ".admin_refresh_all_lockers"
Cohesion: 0.18
Nodes (9): AdminLockerCommands, command, default_permissions, Interaction, listener, 刷新所有用戶的置物櫃 效果： - 更新所有用戶的置物櫃訊息 - 重新渲染紙娃娃圖片 - 更新置物櫃統計數據 耗時：大約 10 秒（取決於用戶數量）, 核心置物櫃刷新邏輯 (可被 slash command 或 webhook 觸發) 回傳 (success_count, fail_count, total), 監聽 cron 腳本發送的觸發訊息。 觸發訊息由 cron 腳本用 Bot Token 透過 REST API 發送（靜音）， 因此 author 為… (+1 more)

### Community 121 - "L1Fixer"
Cohesion: 0.15
Nodes (7): L1Fixer, 修復 ImportError - 嘗試 pip install 缺少的模組, 修復 NameError - 記錄但通常需要人工確認, 修復 FileNotFoundError - 嘗試建立目錄, 修復 PermissionError - 嘗試修正權限, 修復 Discord NotFound - 通常是暫時性問題，記錄即可, Benign pattern matched - log and ignore with backoff

### Community 122 - "game_api.py"
Cohesion: 0.19
Nodes (13): change_paperdoll_part(), get_leaderboard(), get_paperdoll_image(), get_user_paperdoll(), get_user_stats(), init_game_api(), route, 遊戲 API 端點 提供紙娃娃遊戲所需的數據接口 (+5 more)

### Community 123 - ".manual_debug_latest_incident"
Cohesion: 0.21
Nodes (3): _clear_message_state(), _format_debug_analysis_text(), _load_message_state()

### Community 124 - "._upsert_summary_message"
Cohesion: 0.31
Nodes (6): _clear_thread_state(), _load_thread_state(), Thread, _save_message_state(), _save_thread_state(), ForumChannel

### Community 125 - "work_cog.py"
Cohesion: 0.28
Nodes (6): CheckInView, 註冊並重建所有持久化 View - 改善版, 部署工作系統到指定頻道（優先編輯現有訊息）, setup(), WorkCog, required_days_for_level()

### Community 126 - "feedback_cog.py"
Cohesion: 0.23
Nodes (7): FeedbackCog, FeedbackModal, FeedbackView, Interaction, Modal, 玩家意見回饋系統 (Feedback System) - 玩家點击按鈕 → 彈出 Modal 表單 → 輸入反饋 → 發送到管理員頻道, setup()

### Community 127 - "StockSelectionView"
Cohesion: 0.19
Nodes (6): CustomStockModal, PortfolioManageView, 用戶持倉管理視圖 - 显示持仓并提供买卖选项, StockSelectionView, StockSelectMenu, SelectOption

### Community 128 - "CharacterSetupCog"
Cohesion: 0.23
Nodes (8): CharacterSetupCog, command, describe, Interaction, User, 角色配置命令 - 用戶可以自定義楓之谷娃娃外觀, 設置您的楓之谷娃娃外觀 提示：可在線上楓之谷裝備網站查詢 ID, setup()

### Community 129 - "LockerMaintenanceCog"
Cohesion: 0.18
Nodes (7): LockerMaintenanceCog, before_loop, loop, 置物櫃自動診斷和清理 Cog - 每天自動檢查並清理孤立數據 在 uibot.py 中自動加載作為 uicommands 模塊, 置物櫃自動維護 - UIBot 集成（每天執行）, 清理孤立數據 返回清理的項目計數, setup()

### Community 130 - "LockerCache"
Cohesion: 0.17
Nodes (6): LockerCache, Locker Cache System 管理紙娃娃圖片快取，避免短時間內重複請求 MapleStory API, 置物櫃快取管理器 - paperdoll_image_cache: { paperdoll_hash → (image_url, timestamp) } -…, 根據紙娃娃相關欄位產生 hash 包括：face, hair, skin, 以及所有裝備欄位 (equip_*), 獲取紙娃娃圖片 URL 邏輯： 1. 計算當前 paperdoll_hash 2. 若 force_refresh=False 且快取存在且未過期 →…, 手動清除指定 hash 的快取（若紙娃娃欄位在 DB 直接被改寫時使用）

### Community 131 - "auto_update_webhook.py"
Cohesion: 0.24
Nodes (12): find_webhook_id(), get_current_tunnel_url(), get_github_webhooks(), load_webhook_config(), main(), 使用 requests 獲取 GitHub webhook 列表, 在 webhook 列表中查找目標 webhook ID, 使用 requests 更新 GitHub webhook URL (+4 more)

### Community 132 - "discord_auth.py"
Cohesion: 0.26
Nodes (12): auth_status(), get_user(), get_user_info(), login(), logout(), oauth_callback(), route, Discord OAuth 2.0 認證系統 支持用戶登錄、會話管理、用戶信息獲取 (+4 more)

### Community 133 - "backup_20260205_1242/database.py"
Cohesion: 0.17
Nodes (5): create_temp_roles_table(), get_expired_roles(), 商店系統數據庫適配層 - 使用 Sheet-Driven DB, 更新用戶KKcoin數量 正數 = 增加，負數 = 減少, update_user_kkcoin()

### Community 134 - "LLMClient"
Cohesion: 0.29
Nodes (3): LLMClient, 呼叫 Gemini generateContent，回傳第一個 candidate 或 None。 caller 透過…, 統一的 LLM API 客戶端 (使用 LiteLLM)。 - gemini()：呼叫 Gemini generateContent，支援原生…

### Community 135 - ".__init__"
Cohesion: 0.20
Nodes (5): load_market_message_data(), Bot, 載入市場 message ID 數據 優先使用環境變數（例如 .env 中的 MARKET_EMBED_MESSAGE_ID），若不存在則退回到本地檔案。, TimeframeButton, UpdateChartButton

### Community 136 - "auto_update_webhook_v2.py"
Cohesion: 0.30
Nodes (11): get_current_tunnel_url(), git_commit_changes(), load_webhook_config(), log_discord(), main(), 使用 GitHub API 更新 webhook（帶重試邏輯）, git commit 和 push config.json, 從 cloudflared 日誌提取當前隧道 URL - 改進版本 (+3 more)

### Community 137 - "webhook_logger.py"
Cohesion: 0.33
Nodes (9): delete_old_webhook_message(), load_bots_info(), log_webhook(), 統一的啟動資訊發送器 - 使用 Webhook, 統一發送啟動資訊 只有 bot 會實際發送訊息，其他機器人只更新資訊, save_bots_info(), send_new_webhook_message(), send_or_update_startup_info() (+1 more)

### Community 138 - "scan_vm_state.py"
Cohesion: 0.33
Nodes (11): derive_expansion_suggestions(), get_disk_summary(), get_git_status(), get_recent_commits(), get_repo_hotspots(), get_systemctl_statuses(), main(), parse_args() (+3 more)

### Community 139 - "sheets.py"
Cohesion: 0.30
Nodes (11): api_clean_virtual(), api_export_db(), api_get_user(), api_sync_sheet(), api_update_user(), get_db(), get_sync_manager(), route (+3 more)

### Community 141 - "RainbowRole"
Cohesion: 0.22
Nodes (5): before_loop, loop, Role, RainbowRole, setup()

### Community 142 - "bot_manager.sh"
Cohesion: 0.44
Nodes (10): check_service_exists(), export_logs(), force_update(), manage_service(), monitor_bots(), run_update(), bot_manager.sh script, show_help() (+2 more)

### Community 143 - ".admin_refresh_all_paperdolls"
Cohesion: 0.22
Nodes (7): command, default_permissions, Interaction, 【UI 模組】管理員命令 負責置物櫃、紙娃娃等 UI 相關的管理功能。 只在 UIBot 中載入。, 批量刷新所有用戶的紙娃娃 URL 生成 功能： - 驗證所有 254 個用戶的紙娃娃數據完整性 - 測試 paperdoll_manager 的 API…, setup(), UIAdminCommands

### Community 144 - "NicknameReset"
Cohesion: 0.25
Nodes (6): NicknameReset, Bot, command, has_permissions, Interaction, setup()

### Community 145 - ".__init__"
Cohesion: 0.31
Nodes (3): CheckInButton, RestButton, WorkActionButton

### Community 146 - "IDDiagnosisCog"
Cohesion: 0.33
Nodes (5): IDDiagnosisCog, command, has_permissions, Interaction, setup()

### Community 147 - "auto_update_config.py"
Cohesion: 0.47
Nodes (8): get_latest_tunnel_url(), git_commit_changes(), log(), main(), 從 cloudflared 日誌提取最新隧道 URL, 自動更新 GitHub Webhook URL 需要環境變數: - GITHUB_TOKEN: GitHub Personal Access Token（需要…, update_config_json(), update_github_webhook()

### Community 148 - "FileEventHandler"
Cohesion: 0.36
Nodes (3): FileEventHandler, FileSystemEventHandler, reload_extension_on_change()

### Community 149 - "FileEventHandler"
Cohesion: 0.36
Nodes (3): FileEventHandler, FileSystemEventHandler, reload_extension_on_change()

### Community 150 - "FileEventHandler"
Cohesion: 0.36
Nodes (3): FileEventHandler, FileSystemEventHandler, reload_extension_on_change()

### Community 151 - ".kkcoin_admin"
Cohesion: 0.39
Nodes (6): choices, command, default_permissions, describe, Interaction, Member

### Community 152 - "work_function/database.py"
Cohesion: 0.29
Nodes (5): DatabaseCog, init_db(), Work 系統數據庫適配層 - 使用新的 Sheet-Driven DB 該模塊提供了工作系統所需的所有數據庫操作， 使用新的 db_adapter (基於…, 初始化數據庫 (已遷移到 Sheet-Driven 系統) Schema 現在從 SHEET Row 1 自動讀取，無需手動管理, setup()

### Community 153 - "MemberSync"
Cohesion: 0.32
Nodes (4): delete_user(), MemberSync, listener, setup()

### Community 155 - "._button_callback"
Cohesion: 0.32
Nodes (6): _is_expired_interaction_error(), Exception, Interaction, 內部按鈕回調處理 Args: interaction: Discord 交互對象 button_id: 按鈕 ID, 添加按鈕到視圖 Args: label: 按鈕文本 callback: 按鈕點擊回調函數 (async def callback(interaction:…, _safe_defer()

### Community 157 - "start_api.sh"
Cohesion: 0.29
Nodes (6): API_HOST, API_PORT, FLASK_DEBUG, PYTHONPATH, PYTHONUNBUFFERED, start_api.sh script

### Community 158 - "main.js"
Cohesion: 0.33
Nodes (5): activity, balanceEl, betBtn, fetchBalance(), refresh()

### Community 159 - "get_kkcoin_balance"
Cohesion: 0.33
Nodes (6): get_kkcoin_balance(), get_user_stats(), 查詢指定用戶的 KK幣與數位美金餘額。⭐智能判斷：為空時自動使用 caller_id。 Args: user_id (str), caller_id…, 查詢指定用戶的完整遊戲數據。⭐智能判斷：為空時自動使用 caller_id。 Args: user_id (str), caller_id (int)…, 智能判斷用戶 ID，返回 (resolved_id, error_msg), _resolve_user_id()

### Community 160 - "weekly_backup.py"
Cohesion: 0.47
Nodes (5): backup_local(), backup_to_sheets(), main(), 備份 DB 至本機 backups/ 資料夾, 將 DB 用戶資料備份至 Google Sheets 的「DB備份」分頁

### Community 161 - ".parse_records"
Cohesion: 0.40
Nodes (3): 將 SHEET 數據轉換為記錄字典列表 (向後相容版本), 內部方法：將 SHEET 數據轉換為記錄字典列表 流程： 1. 自動偵測 user_id 欄位 (如果尚未識別) 2. 逐行處理，跳過無效 user_id…, 自動偵測哪一欄最有可能是 user_id (Discord 用戶 ID) 啟發式方法： - Discord user_id 通常是 18-20 位的數字 -…

### Community 162 - "knowledge_api.py"
Cohesion: 0.60
Nodes (4): knowledge_status(), route, recent_knowledge(), search_knowledge()

### Community 163 - ".on_message"
Cohesion: 0.50
Nodes (3): listener, Message, update_user_balance()

### Community 165 - "cannabis_unified.py"
Cohesion: 0.50
Nodes (3): 大麻系統統一適配器 - 自動將 JSON 欄位轉換為表操作 負責： - cannabis_plants 和 cannabis_inventory 的 JSON…, Discord 應用程序空 setup 函數 此模組不提供任何 Cog，只是提供工具函數。 由於加載系統會自動檢測並加載所有 Python 模組，…, setup()

### Community 167 - "server.py"
Cohesion: 0.67
Nodes (3): do_bet(), get_balance(), route

## Knowledge Gaps
- **18 isolated node(s):** `deploy_gcp.sh script`, `start_api.sh script`, `PYTHONUNBUFFERED`, `FLASK_DEBUG`, `API_HOST` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PersistentViewBase` connect `PersistentViewBase` to `WelcomeFlow`, `ui/uibody.py`, `.__init__`, `AnimeTracker`, `NewYearRedEnvelope`, `AnnouncementButtonView`, `.__init__`, `AnimeDatabase`, `update_user_kkcoin`, `FortressEnemyView`, `._button_callback`, `AnimeScheduleTracker`, `Interaction`, `get_central_reserve`, `FortressDefenseCog`, `cannabis_merchant_view_v2.py`, `get_user_kkcoin`, `ExploreView`, `AnimeVoteView`, `fortress_defense.py`, `ShellAgentRunner`, `Interaction`, `AnimePushCore`, `HospitalMerchant`, `PaperDollPreviewView`, `LockerPanelView`, `SelectFertilizerView`, `get_user`, `stock_market.py`, `button`, `StockMarket`, `work_cog.py`, `feedback_cog.py`, `StockSelectionView`?**
  _High betweenness centrality (0.217) - this node is a cross-community bridge._
- **Why does `LLMClient` connect `LLMClient` to `LiteLLMClient`, `KnowledgeVectorIndex`, `work_system.py`, `log_monitor.py`, `.logmonitor`, `KnowledgeBase`, `KKBotAgent`, `LogMonitorEngine`, `AI.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `get_user()` connect `get_user` to `CharacterSetupCog`, `LockerEventListenerCog`, `WelcomeFlow`, `ScamParkEvents`, `ui/utils/__init__.py`, `PaperdollMerchantSystem`, `get_user_kkcoin`, `Ai`, `work_system.py`, `PersistentViewBase`, `update_locker_message`, `.locker_init`, `HospitalMerchant`, `work_function/database.py`, `MemberSync`, `AvatarReset`, `work_cog.py`, `UserPanel`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 103 inferred relationships involving `PersistentViewBase` (e.g. with `Announcement` and `AnnouncementButtonView`) actually correct?**
  _`PersistentViewBase` has 103 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `AnimeTracker` (e.g. with `AnimeDatabase` and `AnimePushCore`) actually correct?**
  _`AnimeTracker` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `LogMonitorEngine` (e.g. with `LLMClient` and `GoogleAIClient`) actually correct?**
  _`LogMonitorEngine` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deploy_gcp.sh script`, `start_api.sh script`, `PYTHONUNBUFFERED` to the rest of the system?**
  _18 weakly-connected nodes found - possible documentation gaps or missing edges._