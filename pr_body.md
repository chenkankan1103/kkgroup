## 修復內容

### 根因與修復

**BUG#3 (關鍵 - 重複推送舊番)**
- `save_weekly_schedule` 原本使用 `DELETE + INSERT`，導致每天 22:00 刷新週表時所有 `pushed=1` 重置為 0
- 造成補推機制每 5 分鐘重試同一時刻，重複推播已通知的舊集數
- **修復**: 改為逐筆 UPSERT，已推送 (`pushed=1`) 僅更新 `animeData` 保留狀態

**BUG#5 (關鍵 - 遺失 UI 介面)**
- `push_core.generate_anime_view()` 原本返回 `None` (佔位符)，導致推送訊息無投票/評論/連結按鈕
- **修復**: 新增 `view_factory` 回調機制，`AnimeTracker` 設置為自身的 `generate_anime_view`，正確生成 `AnimeVoteView` (神作/佳作/黑馬等 6 種投票 + 評論 + 動畫頁/觀看連結)

**API 防禦性修復**
- `send_anime_push` 中對 `video_sn`/`anime_sn` 加入 `int()` 轉換與驗證，防止 NOT NULL constraint 失敗

**速率限制 (已實作)**
- `_rate_limit_api()` 確保 API 呼叫間隔 ≥ 2 秒 (≤ 30 req/min)，防止被巴哈姆特 BAN

**靜默失敗排除**
- 所有 `print()` 錯誤已轉為 `logger.error(..., exc_info=True)`

### 測試
- 17 個測試全通過 (涵蓋資料庫、週表、啟動初始化、補標記、週期補推、排程派發、22:00 刷新、速率限制、時區邊界、完整生命週期)

### 影響檔案
- `cogs/ui/push_core.py`
- `cogs/ui/anime_tracker.py`
- `scripts/test_anime_tracker.py` (既有測試，全通過)