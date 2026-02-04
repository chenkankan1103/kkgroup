# ⚡ SHEET 主導架構 - 快速參考

## 🎯 核心概念
**SHEET 是主導者，DB 自動適應** ✅

```
SHEET Row 2（標題行） → SheetSyncManager → DB Schema（自動遷移）
```

## 🔄 新增欄位流程（3 秒搞定）

### 步驟 1: 在 SHEET 中添加新列
```
SHEET: ... | level | kkcoin | ✨ new_field | ...
```

### 步驟 2: 完成！🎉
```
下次同步時自動:
✅ 讀取新欄位
✅ ALTER TABLE ADD COLUMN new_field
✅ 同步數據
```

**無需修改代碼！** 🚀

## 📝 常見場景

### 場景 1: 新增玩家屬性（例如親密度）
```
1. SHEET 添加列: intimacy_level
2. 同步時自動:
   - 從 SHEET 讀取 intimacy_level
   - 自動執行: ALTER TABLE users ADD COLUMN intimacy_level TEXT
   - 同步所有玩家的 intimacy_level
```

### 場景 2: 修改欄位類型（例如統計字段改為數字）
```
1. 編輯 FIELD_TYPES (在 sheet_sync_manager.py):
   FIELD_TYPES = {
       'stat_count': 'INTEGER DEFAULT 0',  # 從 TEXT 改為 INTEGER
   }
2. 重啟 bot
3. 下次新增記錄時自動使用新類型
```

### 場景 3: 隱藏某個欄位不同步
```
編輯 EXCLUDE_FIELDS (在 sheet_sync_manager.py):
EXCLUDE_FIELDS = {'nickname', 'temp_field', 'internal_data'}
```

## 🚨 故障排查

### 問題: 同步失敗，欄位未添加
```bash
# 檢查日誌
sudo journalctl -u discord-bot.service | grep -E "添加欄位|ERROR|失敗"
```

### 問題: SHEET 與 DB 記錄數不一致
```bash
# 運行診斷工具
python diagnose_sync.py

# 手動同步
/sync_from_sheet  # Discord 指令
```

### 問題: 新欄位的值都是 NULL/空
```
檢查:
1. SHEET 中該欄位是否有數據
2. 欄位名稱是否正確拼寫（大小寫敏感）
3. 數據格式是否正確
```

## 📊 日誌信息解讀

```
✅ SHEET 表頭 (第 2 行，共 24 列): ['user_id', 'nickname', ...]
   ↑ 已成功讀取 SHEET 標題

🔧 檢查並自動同步 DB schema...
   ↑ 檢查 DB 是否需要添加新欄位

➕ 添加欄位: new_field
✅ 新增 1 個欄位
   ↑ 成功添加 1 個欄位（如果沒有這行，代表沒有新欄位）

📊 SHEET 數據行: 54 筆
   ↑ SHEET 中有效數據行數

✅ 解析完成: 54 筆有效記錄
   ↑ 成功解析的記錄數（如果小於數據行數，代表有記錄被跳過）

🔍 記錄 1: user_id=123456789, kkcoin=1000, level=1
   ↑ 前 3 筆記錄的預覽

✅ [SHEET→DB 同步] 更新=50, 新增=4, 錯誤=0
   ↑ 同步統計（更新了 50 筆，新增 4 筆，無錯誤 ✅）
```

## 🎛️ 配置文件位置

| 文件 | 位置 | 用途 |
|------|------|------|
| 同步管理器 | `sheet_sync_manager.py` | 核心邏輯 |
| 同步命令 | `commands/google_sheets_sync.py` | Discord 指令 |
| 欄位類型 | `FIELD_TYPES` | 新欄位的 SQL 類型 |
| 排除列表 | `EXCLUDE_FIELDS` | 不同步的欄位 |

## 🚀 生產部署

### 1. 拉取最新代碼
```bash
cd /bot/path
git pull
```

### 2. 重啟 bot
```bash
sudo systemctl restart discord-bot.service
```

### 3. 驗證
```bash
# 檢查日誌輸出（應該看到自動 schema 同步的日誌）
sudo journalctl -u discord-bot.service -n 50 | tail -20
```

## ✨ 架構優勢

| 功能 | 舊架構 | 新架構 |
|------|-------|-------|
| 新增欄位 | ❌ 需改代碼 | ✅ 自動 |
| Schema 遷移 | ❌ 手動執行 | ✅ 自動 |
| 維護成本 | ❌ 高 | ✅ 低 |
| 出錯風險 | ❌ 高 | ✅ 低 |
| **一勞永逸** | ❌ 否 | ✅ **是** |

## 📞 需要幫助？

查看詳細文檔：
- [SHEET_DRIVEN_ARCHITECTURE.md](SHEET_DRIVEN_ARCHITECTURE.md) - 完整說明
- [SYNC_FIX_REPORT.md](SYNC_FIX_REPORT.md) - 修復報告
- [sheet_sync_manager.py](sheet_sync_manager.py) - 源代碼

---
**記住：SHEET 是主導，DB 跟著走** 🎯
