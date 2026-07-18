## 修復內容

### 根因
`AnimePushCore.__init__` 未初始化 `self.db`，導致 `set_bot_and_db` 呼叫前若有排程任務執行，`mark_time_pushed` 會靜默失敗（`AttributeError: 'NoneType' object has no attribute 'mark_time_pushed'` 被 try/except 吞掉），資料庫 `pushed` 欄位永遠維持 0，造成：
- 21:30 等時刻推播不觸發
- Catchup 每 5 分鐘重試同一時刻
- Bot 重啟後無法正確恢復狀態

### 修復
1. **push_core.py**: `AnimePushCore.__init__` 直接 `self.db = AnimeDatabase(db_path)`，移除對 `set_bot_and_db` 的依賴
2. **push_core.py**: 移除 `mark_time_pushed` 周圍的靜默 try/except，讓異常浮出
3. **push_core.py**: `TW_TZ = ZoneInfo('Asia/Taipei')` 取代 `pytz`，修正台灣時區
4. **schedule_tracker.py**: `_get_expected_check_times` 使用日期過濾而非 1 小時窗口，修正跨午夜問題

### 測試
- 新增 `scripts/test_anime_tracker.py`：17 測試全通過
- 模擬 Discord 環境（Mock Bot/Channel/Message）
- Mock Bahamut API 回應
- 使用 `freezegun` + `ZoneInfo` 凍結時間驗證邏輯
- 覆蓋：資料庫、週表、啟動初始化、補標記、週期補推、排程派發、22:00 刷新、速率限制、時區邊界、完整生命週期

### 影響檔案
- cogs/ui/push_core.py
- cogs/ui/schedule_tracker.py
- cogs/ui/anime_tracker.py (間接)
- scripts/test_anime_tracker.py (新增)
- cogs/ui/cogs/locker_event_test.py (既有)