# 動畫推播系統修復 - 2026-05-03

## 問題概述
- 動畫通知延遲（最後一次檢查 19 分鐘前）
- 某些動畫集落下未推播
- 檢查頻率不規則（24 小時內僅 24 筆記錄，遠低於預期的 ~1440 筆）

## 根本原因分析
@tasks.loop(minutes=1) 任務在執行一次後停止運行，未持續重新執行。根本原因是：
1. **無 error handler** - 任務拋出異常時無法被捕獲，導致任務停止
2. **異常處理不完善** - 個別操作的異常未被隔離，導致整個任務崩潰
3. **無心跳日誌** - 缺少運行證明，難以診斷問題

## 實施的修復

### 修復 1：添加 Error Handler for check_new_anime
**文件**: cogs/ui/anime_tracker.py
**修改**: 添加 @check_new_anime.error 裝飾器
**作用**:
- 捕獲任務拋出的所有異常
- 記錄詳細的錯誤信息
- 自動重新啟動任務（5 秒延遲）
- 防止任務因異常而停止

```python
@check_new_anime.error
async def check_new_anime_error(self, error):
    """處理 check_new_anime 任務的異常"""
    logger.error(f"❌ [check_new_anime] 任務異常: {error}", exc_info=True)
    logger.warning(f"⚠️ [check_new_anime] 嘗試重啟任務...")
    try:
        await asyncio.sleep(5)
        if not self.check_new_anime.is_running():
            logger.info(f"🔄 [check_new_anime] 重新啟動任務...")
            self.check_new_anime.restart()
            logger.info(f"✅ [check_new_anime] 任務已重新啟動")
    except Exception as restart_error:
        logger.error(f"❌ [check_new_anime] 重啟失敗: {restart_error}", exc_info=True)
```

### 修復 2：添加 Error Handler for send_weekly_stats
**文件**: cogs/ui/anime_tracker.py
**修改**: 添加 @send_weekly_stats.error 裝飾器
**作用**: 與 check_new_anime 相同，確保週統計任務也能自我修復

### 修復 3：添加心跳日誌
**文件**: cogs/ui/anime_tracker.py
**修改**: check_new_anime 方法開始處添加心跳日誌
**作用**:
- 每分鐘記錄一次心跳
- 便於監控任務是否還在運行
- 快速定位問題時間點

```python
logger.info(f"💓 [check_new_anime] 心跳 - {now.strftime('%Y-%m-%d %H:%M:%S')}")
```

### 修復 4：改進 check_new_anime 內部異常處理
**文件**: cogs/ui/anime_tracker.py
**修改**: 封閉每個操作步驟的異常處理
**作用**:
- 數據庫查詢失敗時允許重試
- 檢查執行失敗時不標記為已檢查
- 單個集的失敗不影響其他集的發送

```python
# 檢查該時刻今日是否已檢查過
try:
    already_checked = self.db.is_time_checked_today(scheduled_time_str, scheduled_date)
except Exception as db_err:
    logger.error(f"❌ [check_new_anime] 資料庫查詢失敗: {db_err}", exc_info=True)
    already_checked = False  # 發生錯誤時，假設未檢查過（允許重試）
    continue  # 跳過本次檢查，防止數據庫問題堆積
```

### 修復 5：改進 _check_and_send_anime 異常處理
**文件**: cogs/ui/anime_tracker.py
**修改**: 
- 集檢查時添加異常處理
- 消息發送失敗時不中斷流程
- 數據庫保存失敗時允許繼續發送其他集
- 詳細計數已發送/總數

**作用**:
- 一個集的失敗不影響其他集的發送
- 一個 Discord 消息的失敗不影響整個推播流程
- 詳細的發送日誌便於排查問題

```python
# 集級別的異常處理
try:
    # ... 發送邏輯
except Exception as send_err:
    logger.error(f"❌ [_check_and_send_anime] 發送集異常 (video_sn={ep.get('videoSn')}): {send_err}", exc_info=True)
    await asyncio.sleep(1)
    continue  # 繼續發送其他集
```

### 修復 6：改進 cog_load 啟動邏輯
**文件**: cogs/ui/anime_tracker.py
**修改**:
- 啟動失敗時添加重試邏輯
- 添加任務狀態檢查日誌
- 詳細記錄啟動過程

**作用**:
- 初始啟動失敗時自動重試
- 詳細的啟動日誌便於診斷啟動問題

```python
try:
    self.check_new_anime.start()
    logger.info(f"✅ [AnimeTracker.cog_load] check_new_anime 已啟動 (is_running={self.check_new_anime.is_running()})")
except Exception as start_err:
    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 check_new_anime 失敗: {start_err}", exc_info=True)
    # 重試一次
    try:
        await asyncio.sleep(1)
        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 check_new_anime...")
        self.check_new_anime.start()
        logger.info("✅ [AnimeTracker.cog_load] 重試成功，check_new_anime 已啟動")
    except Exception as retry_err:
        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
```

## 預期效果

### 立即效果
1. ✅ 異常不再導致任務停止
2. ✅ 任務自動重啟能力
3. ✅ 每分鐘心跳日誌可驗證任務運行

### 調查効果
1. ✅ 詳細的日誌便於排查原始異常
2. ✅ 任務狀態可實時監控
3. ✅ 發送統計更精確

## 驗證步驟

1. **推送代碼到 GitHub**
   ```bash
   git add cogs/ui/anime_tracker.py
   git commit -m "fix: 修復動畫推播任務持續性 - 添加 error handler 和異常隔離"
   git push
   ```

2. **等待 webhook 觸發重啟**（自動）

3. **檢查日誌驗證修復**
   ```bash
   sudo journalctl -u bot.service -f | grep -i anime
   ```
   應該看到：
   - 每分鐘一次的心跳日誌：`💓 [check_new_anime] 心跳`
   - 預定時刻檢查日誌：`🔍 [check_new_anime] 開始檢查`
   - 新集發現日誌：`🆕 [...] 發現 N 個新集`

4. **監控數據庫**
   ```bash
   sqlite3 kkgroup.db "SELECT COUNT(*) as total_checks, COUNT(DISTINCT scheduled_time) as unique_times FROM anime_check_history WHERE check_date = '2026-05-03'"
   ```
   應該看到記錄數量持續增加（每分鐘增加）

5. **24 小時後對比**
   - 修復前：~24 筆記錄
   - 修復後：應該有 ~1440 筆記錄（每分鐘一筆）

## 相關文件修改
- cogs/ui/anime_tracker.py：添加 error handler、改進異常處理、添加心跳日誌

## 後續監控
建議持續監控以下指標：
1. 每分鐘心跳日誌（證明任務運行）
2. 推播延遲（預定時刻與實際推播時間差）
3. 推播成功率（新集數 vs 推播成功數）
4. 異常日誌頻率（是否有特定的異常模式）

## 已知限制
- 如果 Discord API 完全無響應，任務仍可能失敗，但會被記錄並重啟
- 如果數據庫完全損壞，異常隔離無法救援，需要人工介入
