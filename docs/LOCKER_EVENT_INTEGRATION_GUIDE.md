"""
置物櫃事件驅動系統 - 整合指南

系統概觀：
- 不再依賴全局後台任務定期覆蓋置物櫃 embed
- 改為事件驅動：使用者資料一變，立刻觸發對應事件
- 事件監聽器根據事件類型進行快速、局部的 embed 更新

核心事件：
1. EquipmentChangedEvent - 裝備/紙娃娃變更
2. CurrencyChangedEvent - KK幣/經驗值變更
3. HealthChangedEvent - 血量/體力變更
4. InventoryChangedEvent - 物品欄變更
5. FullRefreshEvent - 完整刷新（管理員）
6. SyncRequestedEvent - 同步請求（背景任務）

=================================
實施步驟
=================================

[步驟 1] 在 bot 啟動時執行 Migration
✅ 已完成：bot.py on_ready() 會自動執行 migrate_locker_event_system.py

[步驟 2] 在業務邏輯中觸發事件
=================================
例子 1: 當使用者獲得 KK幣時
=============================

原本代碼（舊）：
    user_data['kkcoin'] += amount
    set_user_field(user_id, 'kkcoin', user_data['kkcoin'])

新代碼（事件驅動）：
    user_data['kkcoin'] += amount
    set_user_field(user_id, 'kkcoin', user_data['kkcoin'])
    
    # ✅ 觸發事件（使用 bot.dispatch）
    from uicommands.events import CurrencyChangedEvent
    event = CurrencyChangedEvent(user_id=user_id, changed_fields={'kkcoin'})
    bot.dispatch('currency_changed', event)


例子 2: 當使用者換裝備時
=============================

原本代碼（舊）：
    user_data['equip_0'] = new_weapon_id
    set_user_field(user_id, 'equip_0', new_weapon_id)

新代碼（事件驅動）：
    user_data['equip_0'] = new_weapon_id
    set_user_field(user_id, 'equip_0', new_weapon_id)
    
    # ✅ 觸發事件（使用 bot.dispatch）
    from uicommands.events import EquipmentChangedEvent
    event = EquipmentChangedEvent(user_id=user_id, changed_fields={'equip_0'})
    bot.dispatch('equipment_changed', event)


例子 3: 當使用者回血/回體時
=============================

原本代碼（舊）：
    user_data['hp'] = min(100, user_data['hp'] + heal_amount)
    set_user_field(user_id, 'hp', user_data['hp'])

新代碼（事件驅動）：
    user_data['hp'] = min(100, user_data['hp'] + heal_amount)
    set_user_field(user_id, 'hp', user_data['hp'])
    
    # ✅ 觸發事件（使用 bot.dispatch）
    from uicommands.events import HealthChangedEvent
    event = HealthChangedEvent(user_id=user_id, changed_fields={'hp'})
    bot.dispatch('health_changed', event)


[步驟 3] 事件監聽器自動處理更新
=================================
每當事件被 dispatch，LockerEventListenerCog 會自動：

1. EquipmentChangedEvent 監聽器
   - 呼叫 locker_cache.get_paperdoll_image() 取得（或快取）紙娃娃圖
   - 生成新的 appearance embed（含圖片 + 裝備格子）
   - 編輯 Discord 訊息的 embeds[1]

2. CurrencyChangedEvent 監聽器
   - 生成新的 summary embed（只更新文字欄位，無圖片）
   - 編輯 Discord 訊息的 embeds[0]

3. HealthChangedEvent 監聽器
   - 生成新的 summary embed（只更新進度條欄位）
   - 編輯 Discord 訊息的 embeds[0]

4. FullRefreshEvent 監聽器
   - 清除該使用者的紙娃娃快取
   - 強制重新請求 MapleStory API
   - 同時更新 embeds[0] 和 embeds[1]


[步驟 4] 快取策略
=================================
LockerCache 會自動快取紙娃娃圖片：

快取 Key: SHA256 hash of (face, hair, skin, equip_0-19)
快取 TTL: 24 小時（可配置）

優點：
✅ API 請求大幅減少（帳號裝備通常不常改）
✅ 快取命中率高 → 只剩下 Discord message edit 的時間開銷
✅ 支援環境變數配置快取 TTL

查看快取統計：
    stats = locker_cache.get_stats()
    print(stats)
    # 輸出：{
    #   'cache_size': 100,           # 目前快取的不同紙娃娃配置數
    #   'hit_count': 5000,           # 快取命中次數
    #   'miss_count': 250,           # 快取未命中次數
    #   'hit_rate': 95.2,            # 命中率百分比
    # }


[步驟 5] 管理員指令
=================================

/refresh_all_lockers - 完整刷新所有人的置物櫃
  -> 觸發 FullRefreshEvent for 所有使用者
  -> 清除所有快取、重新請求 API、更新所有 embed

/test_locker_equipment - [開發用] 測試裝備事件
/test_locker_currency - [開發用] 測試 KK幣事件
/test_locker_health - [開發用] 測試血量事件
/test_locker_full_refresh - [開發用] 測試完整刷新事件


=================================
需要變更的檔案清單
=================================

1. shop_commands/ 中的各種獲得 KK幣 的地方
   - 麻藥、大麻收成等
   - 每個地方加上 bot.dispatch('currency_changed', ...)

2. 裝備系統
   - 穿戴/卸下裝備時
   - 加上 bot.dispatch('equipment_changed', ...)

3. 血量/體力系統
   - 血量改變時
   - 加上 bot.dispatch('health_changed', ...)

4. 物品欄系統
   - 物品欄變更時
   - 加上 bot.dispatch('inventory_changed', ...)

5. locker_tasks.py 背景任務
   - 改為只在 DB 中偵測變更（使用 last_* 欄位）
   - 若有變更則觸發 SyncRequestedEvent
   - 監聽器會比較 embed 是否需要更新，只更新必要的內容


=================================
測試流程
=================================

1. 執行 migration
   python tools/migrate_locker_event_system.py

2. 啟動 bot
   python bot.py

3. 在 Discord 使用管理員測試指令
   /test_locker_equipment - 檢查裝備 embed 是否更新
   /test_locker_currency - 檢查 KK幣 embed 是否更新
   /test_locker_health - 檢查血量進度條是否更新
   /test_locker_full_refresh - 檢查完整刷新是否工作

4. 檢查日誌輸出
   - 應該看到 ✅ [EventType] 已更新 user_id 的 ... embed
   - 應該看到快取統計資訊

5. 檢查快取效率
   多次觸發同一個使用者的公式變更事件，應該看到快取命中率提升


=================================
效能考量
=================================

舊系統（全局後台任務）：
- 每 30 分鐘掃一次所有 247 個使用者
- 每次都請求 MapleStory API（即使沒變更）
- 可能被多個背景任務重複覆蓋

新系統（事件驅動）：
- 只在資料實際變更時更新 embed
- 快取大幅減少 API 請求
- 單一事件路徑，無競爭問題
- 平均每個事件的開銷：0-50ms（取決於 Discord API 延遲）


=================================
後續改善方向
=================================

1. 批量事件合併
   - 短時間內多個事件 → 合併成一個 update
   - 例：3 秒內多個 currency_changed 事件 → 只 update 一次

2. 事件優先級
   - EquipmentChangedEvent 優先級高（需請求 API）
   - CurrencyChangedEvent 優先級低（只改文字）
   - 使用優先隊列管理

3. 事件持久化
   - 記錄所有事件到 audit log
   - 用於追蹤使用者活動、除錯等

4. 事件重試機制
   - 若 Discord message edit 失敗，自動重試
   - 最多 3 次重試，間隔遞增

5. 事件分布
   - 若有多個 bot 實例，可透過 Redis 共享事件隊列
"""

print(__doc__)
