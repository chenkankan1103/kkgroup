# 🚀 部署清單 - SHEET 主導架構

## ✅ 完成項目

### 1. 核心代碼完成
- ✅ `sheet_sync_manager.py` - SheetSyncManager 類（149 行）
  - ✅ 動態表頭提取
  - ✅ 自動 schema 遷移（ALTER TABLE ADD COLUMN）
  - ✅ 動態記錄解析
  - ✅ 欄位排除列表
  - ✅ 語法驗證通過

- ✅ `commands/google_sheets_sync.py` - 簡化的同步命令
  - ✅ 集成 SheetSyncManager
  - ✅ 移除 150+ 行硬編碼欄位邏輯
  - ✅ 新增簡潔的 5 行同步邏輯
  - ✅ 語法驗證通過

### 2. 文檔完成
- ✅ [SHEET_DRIVEN_ARCHITECTURE.md](SHEET_DRIVEN_ARCHITECTURE.md) - 完整架構說明
- ✅ [SHEET_ARCHITECTURE_CHEATSHEET.md](SHEET_ARCHITECTURE_CHEATSHEET.md) - 快速參考卡
- ✅ [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md) - 實施總結
- ✅ [SYNC_FIX_REPORT.md](SYNC_FIX_REPORT.md) - 修復報告

### 3. 診斷工具完成
- ✅ [diagnose_sync.py](diagnose_sync.py) - 同步診斷工具
- ✅ [test_sync_logic.py](test_sync_logic.py) - 邏輯測試（已驗證 ✅）
- ✅ [check_db.py](check_db.py) - DB 結構檢查

### 4. Git 提交完成
```
fabc7bd - 📋 實施完成：SHEET 主導架構總結
f6c3b0e - 快速參考：SHEET 主導架構使用指南
fb34b68 - 文檔：SHEET 主導架構詳細說明和部署指南
bc6057c - 重構：實施 SHEET 主導的動態同步架構 🎯
06ef541 - 新增：同步修復報告和診斷工具
97dd6be - 修復：不試圖同步 nickname 欄位（DB 無此欄位）
```

---

## 🚀 GCP 伺服器部署步驟

### 前置檢查
```bash
# 確認 SSH 連接正常
ssh your-gcp-instance
```

### 步驟 1: 拉取最新代碼
```bash
cd /path/to/discord-bot
git status  # 確認沒有未提交的改動
git pull    # 拉取最新代碼

# 應該看到以下新文件/修改:
# - sheet_sync_manager.py (新)
# - commands/google_sheets_sync.py (修改)
# - SHEET_DRIVEN_ARCHITECTURE.md (新)
# - 其他文檔文件 (新)
```

### 步驟 2: 重啟 bot
```bash
# 方法 1: 使用 systemd（推薦）
sudo systemctl restart discord-bot.service

# 驗證狀態
sudo systemctl status discord-bot.service
# 應該看到: Active (running)

# 或者使用指令:
sudo systemctl restart shopbot.service  # shop bot
sudo systemctl restart uibot.service    # UI bot
```

### 步驟 3: 驗證部署
```bash
# 查看最新的日誌（等待 ~30 秒）
sudo journalctl -u discord-bot.service -f

# 應該看到以下日誌:
# 📋 SHEET 表頭 (第 2 行，共 24 列): ['user_id', 'nickname', ...]
# 🔧 檢查並自動同步 DB schema...
# ✅ [SHEET→DB 同步] 更新=50, 新增=4, 錯誤=0

# 按 Ctrl+C 退出日誌
```

### 步驟 4: Discord 中測試
在 Discord 伺服器執行命令：
```
/sync_from_sheet         # 手動觸發同步
```

預期回應：
```
✅ Google Sheet 同步完成
📊 更新: 50 | 新增: 0 | 錯誤: 0
⏰ 同步時間: 2026-02-05 10:30:45
```

---

## 🔍 故障排查

### 問題 1: 重啟後 bot 沒有上線
```bash
# 查看詳細錯誤
sudo journalctl -u discord-bot.service -n 100
# 查找 ERROR, Traceback, exception 等關鍵字
```

### 問題 2: 同步命令返回錯誤
```bash
# 檢查錯誤日誌
sudo journalctl -u discord-bot.service | grep -E "錯誤|ERROR|Failed"

# 運行診斷工具
python /path/to/diagnose_sync.py
```

### 問題 3: 新欄位未被添加到 DB
```bash
# 檢查 SHEET 的第 2 行是否有新欄位
# 檢查日誌是否有 "➕ 添加欄位: new_field" 的信息

# 手動驗證 DB
sqlite3 /path/to/user_data.db "PRAGMA table_info(users);"
# 應該看到新欄位在列表中
```

---

## 📊 驗證清單

部署後請驗證以下項目：

- [ ] Bot 成功啟動（查看日誌）
- [ ] 看到 "🔧 檢查並自動同步 DB schema..." 日誌
- [ ] 每 1 分鐘看到一次同步檢查日誌
- [ ] `/sync_from_sheet` 命令有效
- [ ] `/export_to_sheet` 命令有效
- [ ] SHEET 與 DB 記錄數相同（運行 diagnose_sync.py）
- [ ] 沒有 ERROR 或 Traceback 日誌

---

## 🎯 預期結果

部署成功後的狀態：

```
✅ SHEET 是真實數據源
✅ DB 自動根據 SHEET 適應
✅ 新增欄位時完全自動化
✅ 無需代碼修改
✅ 一勞永逸
```

### 日誌示例
```
[Bot Startup]
📑 打開試算表，工作表清單: ['玩家資料', '「工作表1」的副本']
✅ Google Sheets 連接成功

[1-minute sync check]
📋 SHEET 表頭 (第 2 行，共 24 列): ['user_id', 'nickname', 'level', ...]
🔧 檢查並自動同步 DB schema...
✅ 新增 0 個欄位  (或者 ✅ 新增 1 個欄位: new_field)
📊 SHEET 數據行: 54 筆
✅ 解析完成: 54 筆有效記錄
🔍 記錄 1: user_id=123456789, kkcoin=1000, level=1
✅ [SHEET→DB 同步] 更新=50, 新增=0, 錯誤=0 (14:30:45)
```

---

## 📞 部署支援

如遇到問題，提供以下信息：
1. 完整的錯誤日誌（`journalctl` 輸出）
2. `diagnose_sync.py` 的運行結果
3. `sqlite3 user_data.db "PRAGMA table_info(users);"` 的輸出

---

## 🎉 部署完成確認

部署成功的標誌：
- ✅ Bot 在線
- ✅ 能看到完整的同步日誌
- ✅ 所有命令有效
- ✅ 無 ERROR 日誌

**完成！🎯 一勞永逸的 SHEET 主導架構現已上線**

---

**部署日期**: 2026-02-05  
**版本**: 1.0  
**部署者**: System Administrator  
**狀態**: ⏳ 待部署到 GCP 伺服器
