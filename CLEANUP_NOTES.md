# Bot 代碼清理報告

## 📝 深度檢查結果

### 1. ✅ 日誌配置已修復
- **問題**: 三個 bot 都輸出到 `/tmp/` 檔案而不是 systemd journalctl
- **解決**: 已更改 service 文件改用 `StandardOutput=journal` / `StandardError=journal`
- **狀態**: 完成並已部署

### 2. 🔍 多餘邏輯識別

#### A. 安全可移除（零風險）
- [ ] `file_log()` 函數定義和所有調用 → 改用標準 logging
- [ ] 被註解的 `observer` 檔案監控系統（~20 行 × 3 個 bots）

#### B. 待驗證（低風險但需測試）
- [ ] `_check_ready_timeout()` 邏輯 - 驗證 Discord on_ready 是否穩定
- [ ] `_get_memory_usage()` - 確認不再需要內存監控

#### C. 必須保留（高風險）
- [x] `anime_tracker` 特殊卸載-重載邏輯 - 重要用於確保新修改生效
- [x] DB migration 代碼 - 置物櫃事件驅動系統必需
- [x] `on_voice_state_update()` - 可能有用途

## 📊 代碼規模統計
- **bot.py**: 682 行 (包含 GCP Metrics 停用代碼 + 複雜調試)
- **shopbot.py**: 446 行 (相對簡潔)
- **uibot.py**: 437 行 (相對簡潔)

## 🛡️ 保守策略
由於 `bot.py` 複雜度較高，採用分階段清理：
1. ✅ 已完成: 修復日誌配置 (service 文件)
2. 待做: 移除被註解的檔案監控代碼 (~20 行)
3. 待驗證: 評估 `_check_ready_timeout` 是否仍必需

## ✨ 當前狀態
- 服務已配置使用 systemd journal
- file_log() 輸出同時到 stdout（被 journalctl 捕獲）和本地檔案
- Bot 啟動安全，無破壞性修改
