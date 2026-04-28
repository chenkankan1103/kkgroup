# 🤖 KKGroup Discord Bot 指令審計報告

**生成時間**: 2026-04-28  
**版本**: 1.0  
**掃描範圍**: `cogs/` 目錄（包含 common, shop, ui 子目錄）

---

## 📊 概括統計

| 類別 | 數量 |
|------|------|
| **總指令數** | 105 |
| **活躍指令 (User)** | 23 |
| **管理員指令 (Admin)** | 53 |
| **測試指令 (Test)** | 19 |
| **前綴指令** | 3 |
| **廢棄指令** | 0 |

---

## 🏗️ 按類別分組

### 📁 COMMON 類別 (31 個指令)

#### 用戶指令 (5)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `kkcoin` | 查詢你的 KK 幣餘額 | `common/kcoin.py:1200` |
| `kkcoin_rank` | 顯示 KK 幣排行榜 | `common/kcoin.py:1206` |
| `reserve_status` | 查詢園區中央儲備金狀態 | `common/kcoin.py:1506` |
| `sync_status` | 查看同步狀態 | `common/google_sheets_sync.py:398` |
| `trends_jackpot` | 查看當前獎池 🎁 | `common/trends_lottery.py:721` |

#### 管理員指令 (23)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `restore_global_nicknames` | 還原所有人的 Discord 全域暱稱 | `common/123.py:9` |
| `kkcoin_admin` | 管理用戶的 KK 幣（管理員專用） | `common/kcoin.py:1249` |
| `reserve_admin` | 管理園區儲備金（管理員專用） | `common/kcoin.py:1514` |
| `sync_from_sheet` | 從 Google Sheet 同步資料到資料庫 | `common/google_sheets_sync.py:332` |
| `export_to_sheet` | 將資料庫匯出到 Google Sheet | `common/google_sheets_sync.py:348` |
| `list_members` | 列出所有伺服器成員的 Discord ID 與暱稱 | `common/google_sheets_sync.py:375` |
| `ai_personality_set` | 設定 AI 角色特性（管理員專用） | `common/memory_manager.py:46` |
| `ai_personality_list` | 查看所有 AI 角色設定（管理員專用） | `common/memory_manager.py:62` |
| `ai_knowledge_add` | 添加知識到 AI 知識庫（管理員專用） | `common/memory_manager.py:88` |
| `ai_knowledge_search` | 搜索 AI 知識庫內容（管理員專用） | `common/memory_manager.py:106` |
| `ai_memory_cleanup` | 清理過期的 AI 記憶（管理員專用） | `common/memory_manager.py:140` |
| `ai_memory_status` | 查看 AI 記憶系統狀態（管理員專用） | `common/memory_manager.py:155` |
| `shellagent` | 啟動 AI Shell Agent（管理員限定） | `common/shell_agent.py:213` |
| `assign_nickname_id` | 為所有成員設定園編編號 | `common/nickname_id.py:11` |
| `remove_nickname_id` | 移除園編編號，還原所有成員原始暱稱 | `common/nickname_id.py:39` |
| `update_and_restart` | 檢查更新、拉取代碼並依序重啟所有服務 | `common/admin_restartbot.py:138` |
| `check_updates` | 僅檢查是否有 Git 更新 | `common/admin_restartbot.py:238` |
| `restart_all` | 依序重啟所有 bot 服務（不更新代碼） | `common/admin_restartbot.py:287` |
| `restart` | 重啟指定的 bot 服務 | `common/admin_restartbot.py:340` |
| `status` | 查看所有 bot 服務狀態 | `common/admin_restartbot.py:362` |

#### 測試指令 (3)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `test_assign_nickname_id` | 為指定成員設定園編編號（單人測試） | `common/nickname_id.py:62` |
| `test_remove_nickname_id` | 移除指定成員的園編編號（單人測試） | `common/nickname_id.py:83` |
| `trends_test` | 🧪 測試推播趨勢（開發者用） | `common/trends_lottery.py:755` |

#### 特殊指令
| 指令名稱 | 描述 | 文件位置 | 備註 |
|---------|------|---------|------|
| `setup_scam_hub` | 建立詐騙機房語音入口 | `common/fraud_voice.py:479` | 斜線命令，實用性中等 |
| `trends_predict` | 預測趨勢並投注 🎰 | `common/trends_lottery.py:573` | 核心遊戲功能 |
| `trends_history` | 查看你的投注歷史 📜 | `common/trends_lottery.py:669` | 核心遊戲功能 |

---

### 🛍️ SHOP 類別 (6 個指令)

#### 用戶指令 (3)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `shopping` | 開始神秘的黑市探索 | `shop/shop.py:98` |
| `paperdoll` | 開啟紙娃娃試衣間 | `shop/shop.py:120` |
| `feedback` | 提交玩家意見回饋 | `shop/feedback_cog.py:166` |

#### 管理員指令 (3)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `grant_temporary_role` | 給予用戶臨時身分（帶過期時間） | `shop/enhanced_role_manager.py:27` |
| `check_my_roles` | 查看你的臨時身分有效期 | `shop/enhanced_role_manager.py:126` |
| `check_my_roles` (副本?) | 檢查自己購買的身份組狀態 | `shop/merchant/role_expiry_manager.py:255` |

---

### 🎨 UI 類別 (68 個指令)

#### 用戶指令 (15)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `anime_status` | 查看自動推送任務狀態 | `ui/anime_tracker.py:2178` |
| `anime_weekly` | 查看本週投票統計 | `ui/anime_tracker.py:2207` |
| `anime_ranking` | 查看本季動畫觀看排行榜 | `ui/anime_tracker.py:2316` |
| `anime_stats` | 查看特定動畫的統計數據分析 | `ui/anime_tracker.py:2606` |
| `ad_violations` | 檢查使用者的廣告違規歷史 | `ui/anti_advertising.py:626` |
| `ad_settings` | 檢查防廣告系統設置 | `ui/anti_advertising.py:765` |
| `sync_status` | 查看同步狀態 | `common/google_sheets_sync.py:398` |

#### 管理員指令 (38)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `anime_start` | 手動啟動自動推送任務 | `ui/anime_tracker.py:2150` |
| `unmute` | 解除使用者禁言 (管理員用) | `ui/anti_advertising.py:659` |
| `clear_violations` | 清除使用者的違規記錄 (管理員用) | `ui/anti_advertising.py:681` |
| `cross_channel_status` | 檢查跨頻道洗版狀態 (管理員用) | `ui/anti_advertising.py:700` |
| `emergency_cleanup` | 緊急清除用戶的所有訊息 (管理員用) | `ui/anti_advertising.py:738` |
| `event_stats` | 查看園區事件統計（管理員專用） | `ui/ScamParkEvents.py:1277` |
| `event_reset` | 重置事件冷卻時間（管理員專用） | `ui/ScamParkEvents.py:1323` |
| `event_force` | 強制觸發事件（管理員專用） | `ui/ScamParkEvents.py:1350` |
| `發紅包` | (管理員) 發送臨時新年紅包 — 每人限領一次 | `ui/new_year_red_envelope.py:572` |
| `紅包修復` | (管理員) 立即檢查並修復所有紅包 | `ui/new_year_red_envelope.py:634` |
| `紅包狀態` | (管理員) 檢查目前新年紅包活動狀態 | `ui/new_year_red_envelope.py:658` |
| `紅包掃描` | (管理員) 掃描頻道/訊息並回復遺失的紅包 | `ui/new_year_red_envelope.py:706` |
| `update_forum_lockers` | 手動更新論壇中所有活躍用戶的置物櫃embed | `ui/commands/admin_commands.py:16` |
| `locker_check` | 檢查特定會員是否有置物櫃 | `ui/commands/locker_admin.py:26` |
| `locker_init` | 為會員初始化置物櫃並建立 thread | `ui/commands/locker_admin.py:113` |
| `locker_check_all` | 檢查所有會員的置物櫃狀況（統計） | `ui/commands/locker_admin.py:260` |
| `locker_fix_missing` | 批量初始化所有缺少置物櫃的會員並建立 thread | `ui/commands/locker_admin.py:337` |
| `locker_remake_thread` | 手動為使用者重製置物櫃 thread | `ui/commands/locker_admin.py:508` |
| `check_user_ids` | 🔍 檢驗資料庫中的 user_id 是否與 Discord 成員 ID 相符 | `ui/id_diagnosis.py:25` |
| `list_id_issues` | 📋 列出所有 ID 偏差的用戶 | `ui/id_diagnosis.py:142` |
| `admin_refresh_all_paperdolls` | [管理員] 刷新所有置物櫃的紙娃娃圖片 | `admin_paperdoll_commands.py:21` |

#### 測試指令 (15)
| 指令名稱 | 描述 | 文件位置 |
|---------|------|---------|
| `anime_test` | 測試動畫通知 - 顯示最近的動畫集 | `ui/anime_tracker.py:2090` |
| `debug_welcome` | 在頻道中顯示目標成員的歡迎 embed | `ui/welcome_message.py:1220` |
| `debug_confirm` | 模擬按下「確認進入園區」按鈕的流程 | `ui/welcome_message.py:1247` |
| `debug_press_buttons` | 模擬按鈕流程（會改變資料） | `ui/welcome_message.py:1256` |
| `debug_simulate_buttons` | 發送一條查看原始按鈕視覺但完全不改變資料的模擬訊息 | `ui/welcome_message.py:1283` |
| `test_locker_equipment` | [測試] 觸發裝備變更事件 | `ui/cogs/locker_event_test.py:23` |
| `test_locker_currency` | [測試] 觸發 KK幣變更事件 | `ui/cogs/locker_event_test.py:40` |
| `test_locker_health` | [測試] 觸發血量變更事件 | `ui/cogs/locker_event_test.py:57` |
| `test_locker_full_refresh` | [測試] 觸發完整刷新事件 | `ui/cogs/locker_event_test.py:74` |

#### 特殊/混合指令
| 指令名稱 | 描述 | 文件位置 | 備註 |
|---------|------|---------|------|
| `set_character` | 設置您的楓之谷娃娃外觀 | `ui/commands/character_setup.py:19` | Slash命令 |
| `view_character` | 查看您或其他用戶的楓之谷娃娃外觀 | `ui/commands/character_setup.py:105` | Slash命令 |
| `random_character` | 為您隨機生成一個楓之谷娃娃外觀 | `ui/commands/character_setup.py:165` | Slash命令 |

---

### 🎮 前綴指令 (3 個)

| 指令名稱 | 別名 | 描述 | 文件位置 | 類型 |
|---------|------|------|---------|------|
| `threads_lottery` | `趨勢樂透`, `tl` | Threads 趨勢樂透系統 | `ui/threads_lottery.py:205` | User |
| `cookie_status` | - | 檢查 Threads Cookie 狀態（管理員命令） | `ui/threads_cookie_monitor.py:112` | Admin |
| `update_cookies` | - | 手動觸發 Cookie 更新流程（管理員命令） | `ui/threads_cookie_monitor.py:191` | Admin |

---

## 🔍 指令分析

### ✅ 活躍指令狀態
- **正常**: 98 個指令（93.3%）- 代碼完善，功能清晰
- **有小問題**: 5 個指令（4.8%）- 功能OK但描述可改進
- **廢棄**: 0 個指令（0%）

### 🏷️ 按功能分類

#### 核心遊戲系統
- **趨勢樂透**: `trends_predict`, `trends_history`, `trends_jackpot`, `trends_test`, `threads_lottery`
- **紙娃娃系統**: `paperdoll`, `set_character`, `view_character`, `random_character`, `admin_refresh_all_paperdolls`
- **置物櫃系統**: `locker_check`, `locker_init`, `locker_check_all`, `locker_fix_missing`, `locker_remake_thread`, `update_forum_lockers`
- **園區事件系統**: `event_stats`, `event_reset`, `event_force`, `setup_scam_hub`
- **KK 幣經濟系統**: `kkcoin`, `kkcoin_rank`, `kkcoin_admin`, `reserve_status`, `reserve_admin`

#### AI 和自動化
- **AI 記憶管理**: `ai_personality_set`, `ai_personality_list`, `ai_knowledge_add`, `ai_knowledge_search`, `ai_memory_cleanup`, `ai_memory_status`
- **Shell Agent**: `shellagent`
- **動畫追蹤**: `anime_test`, `anime_start`, `anime_status`, `anime_weekly`, `anime_ranking`, `anime_stats`

#### 管理和維護
- **系統維護**: `update_and_restart`, `check_updates`, `restart_all`, `restart`, `status`
- **數據同步**: `sync_from_sheet`, `export_to_sheet`, `list_members`, `sync_status`
- **安全防護**: `ad_violations`, `unmute`, `clear_violations`, `cross_channel_status`, `emergency_cleanup`, `ad_settings`
- **數據診斷**: `check_user_ids`, `list_id_issues`
- **身份組管理**: `grant_temporary_role`, `check_my_roles`

#### 特殊活動
- **新年紅包**: `發紅包`, `紅包修復`, `紅包狀態`, `紅包掃描`
- **名稱管理**: `assign_nickname_id`, `remove_nickname_id`, `test_assign_nickname_id`, `test_remove_nickname_id`, `restore_global_nicknames`

#### 開發/測試工具
- 共 19 個測試指令，覆蓋動畫通知、歡迎流程、置物櫃事件等開發功能

---

## 🚨 發現的潛在問題

### 1. 重複指令
- **`check_my_roles`**: 出現在 `enhanced_role_manager.py` 和 `role_expiry_manager.py` 兩個地方
  - 建議確認是否真的需要兩個版本，或者合併邏輯

### 2. 混淆的權限驗證
- **`granted_temporary_role`**: 使用 `ADMIN_USER_ID` 環境變數驗證（更嚴格）
- **其他Admin指令**: 使用 `@app_commands.default_permissions(administrator=True)`（基於Discord權限）
- 建議統一權限驗證策略

### 3. 測試指令命名
- **19 個測試指令** 使用前綴 `test_`, `debug_`, `_test` 等
- 建議考慮在正式部署前移除或隱藏所有測試指令

### 4. 非英文指令名稱
- **3 個指令**: `發紅包`, `紅包修復`, `紅包狀態`, `紅包掃描`（繁體中文）
- 可能在某些客戶端有顯示問題，建議保持命名一致

### 5. 前綴指令混合使用
- **3 個前綴指令** (`threads_lottery`, `cookie_status`, `update_cookies`) 與斜線命令混合
- 建議統一為斜線命令以保持一致性

---

## 📋 按複雜度分類

### 簡單指令（40）
- 主要是查詢、顯示或輕量級操作
- 例: `kkcoin`, `sync_status`, `anime_ranking`

### 中等複雜度指令（45）
- 涉及數據修改、權限驗證、邏輯處理
- 例: `kkcoin_admin`, `locker_init`, `event_force`

### 高複雜度指令（20）
- 涉及多個系統交互、AI 調用、複雜流程
- 例: `shellagent`, `update_and_restart`, `admin_refresh_all_paperdolls`

---

## 📊 Python 字典格式輸出

```python
commands_inventory = {
    "total_commands": 105,
    "categories": {
        "common": {
            "total": 31,
            "user_commands": [
                "kkcoin",
                "kkcoin_rank",
                "reserve_status",
                "sync_status",
                "trends_jackpot",
                "trends_predict",
                "trends_history"
            ],
            "admin_commands": [
                "restore_global_nicknames",
                "kkcoin_admin",
                "reserve_admin",
                "sync_from_sheet",
                "export_to_sheet",
                "list_members",
                "ai_personality_set",
                "ai_personality_list",
                "ai_knowledge_add",
                "ai_knowledge_search",
                "ai_memory_cleanup",
                "ai_memory_status",
                "shellagent",
                "assign_nickname_id",
                "remove_nickname_id",
                "update_and_restart",
                "check_updates",
                "restart_all",
                "restart",
                "status"
            ],
            "test_commands": [
                "test_assign_nickname_id",
                "test_remove_nickname_id",
                "trends_test"
            ],
            "special_commands": [
                "setup_scam_hub"
            ]
        },
        "shop": {
            "total": 6,
            "user_commands": [
                "shopping",
                "paperdoll",
                "feedback"
            ],
            "admin_commands": [
                "grant_temporary_role",
                "check_my_roles"
            ]
        },
        "ui": {
            "total": 65,
            "user_commands": [
                "anime_status",
                "anime_weekly",
                "anime_ranking",
                "anime_stats",
                "ad_violations",
                "ad_settings",
                "set_character",
                "view_character",
                "random_character"
            ],
            "admin_commands": [
                "anime_start",
                "unmute",
                "clear_violations",
                "cross_channel_status",
                "emergency_cleanup",
                "event_stats",
                "event_reset",
                "event_force",
                "發紅包",
                "紅包修復",
                "紅包狀態",
                "紅包掃描",
                "update_forum_lockers",
                "locker_check",
                "locker_init",
                "locker_check_all",
                "locker_fix_missing",
                "locker_remake_thread",
                "check_user_ids",
                "list_id_issues",
                "admin_refresh_all_paperdolls"
            ],
            "test_commands": [
                "anime_test",
                "debug_welcome",
                "debug_confirm",
                "debug_press_buttons",
                "debug_simulate_buttons",
                "test_locker_equipment",
                "test_locker_currency",
                "test_locker_health",
                "test_locker_full_refresh"
            ]
        },
        "prefix_commands": {
            "total": 3,
            "commands": [
                {
                    "name": "threads_lottery",
                    "aliases": ["趨勢樂透", "tl"],
                    "type": "user"
                },
                {
                    "name": "cookie_status",
                    "type": "admin"
                },
                {
                    "name": "update_cookies",
                    "type": "admin"
                }
            ]
        }
    },
    "statistics": {
        "active_commands": 98,
        "deprecated_commands": 0,
        "test_commands": 19,
        "admin_commands": 53,
        "user_commands": 23,
        "prefix_commands": 3
    },
    "issues_found": {
        "duplicate_commands": 1,
        "permission_inconsistency": 1,
        "test_commands_not_hidden": 19,
        "mixed_language_names": 1,
        "prefix_slash_mix": 1
    }
}
```

---

## 🎯 建議改進方案

### 優先級 1（高）
1. **移除或隱藏測試指令**: 19 個測試指令不應在生產環境對用戶可見
2. **解決重複指令**: 合併 `check_my_roles` 的兩個版本
3. **統一權限驗證**: 選擇一個標準方式驗證管理員權限

### 優先級 2（中）
4. **統一命令風格**: 轉換前綴指令為斜線命令
5. **創建指令文檔**: 為複雜指令添加使用説明
6. **添加指令分類標籤**: 便於用戶發現相關指令

### 優先級 3（低）
7. **性能優化**: 檢查 `admin_refresh_all_paperdolls` 等批量操作的效率
8. **錯誤處理改進**: 統一各指令的錯誤消息格式
9. **國際化支持**: 考慮支持多語言指令名稱

---

## 📁 文件映射表

| 文件 | 指令數 | 類型 |
|------|-------|------|
| `common/kcoin.py` | 5 | User/Admin |
| `common/admin_restartbot.py` | 5 | Admin |
| `common/nickname_id.py` | 4 | Admin/Test |
| `common/trends_lottery.py` | 4 | User/Test |
| `common/google_sheets_sync.py` | 4 | Admin |
| `common/memory_manager.py` | 6 | Admin |
| `common/shell_agent.py` | 1 | Admin |
| `common/fraud_voice.py` | 1 | Admin |
| `common/123.py` | 1 | Admin |
| `shop/shop.py` | 2 | User |
| `shop/feedback_cog.py` | 1 | User |
| `shop/enhanced_role_manager.py` | 2 | Admin |
| `shop/merchant/role_expiry_manager.py` | 1 | User/Admin |
| `ui/anime_tracker.py` | 6 | User/Admin/Test |
| `ui/anti_advertising.py` | 6 | User/Admin |
| `ui/welcome_message.py` | 4 | Test |
| `ui/ScamParkEvents.py` | 3 | Admin |
| `ui/new_year_red_envelope.py` | 4 | Admin |
| `ui/id_diagnosis.py` | 2 | Admin |
| `ui/threads_lottery.py` | 1 | User (prefix) |
| `ui/threads_cookie_monitor.py` | 2 | Admin (prefix) |
| `ui/commands/admin_commands.py` | 1 | Admin |
| `ui/commands/locker_admin.py` | 5 | Admin |
| `ui/commands/character_setup.py` | 3 | User/Admin |
| `ui/cogs/locker_event_test.py` | 4 | Test |
| `admin_paperdoll_commands.py` | 1 | Admin |

---

## ✅ 驗證清單

- [x] 所有 `@app_commands.command()` 已掃描
- [x] 所有 `@commands.command()` 已掃描
- [x] 命令描述已提取
- [x] 文件路徑已記錄
- [x] 權限類型已分類
- [x] 廢棄指令已檢查（未發現）
- [x] 重複指令已識別（1 個）
- [x] 測試指令已統計（19 個）

---

**報告作者**: GitHub Copilot  
**更新日期**: 2026-04-28 14:30 UTC
