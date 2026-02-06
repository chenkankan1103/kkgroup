# 🚀 GCP 執行指南 - 凱文修復完整流程

## 現狀報告
✅ **代碼修改已完成**
- `sheet_driven_db.py`: 修復整數轉換時返回 None 而不是 0
- `sheet_sync_manager.py`: 添加 user_id=0 的驗證和過濾
- `fix_kevin_duplicate.py`: 自動清理虛擬人物腳本已創建

⏳ **待執行**: GCP 上的實際修復操作

---

## 🎯 執行方式 (任選一種)

### 方式 A: 完全自動 (推薦)
```bash
# 1. SSH 連接到 GCP
ssh e193752468@34.80.205.45

# 2. 複製粘貼以下命令
bash /home/e193752468/kkgroup/execute_gcp_fix.sh

# 完成！腳本會自動執行所有步驟
```

---

### 方式 B: 分步手動執行
如果自動腳本有問題，可以分步執行：

```bash
# 【步驟1】進入目錄
cd /home/e193752468/kkgroup

# 【步驟2】提交代碼修改
git add sheet_driven_db.py sheet_sync_manager.py
git commit -m "Fix: 修復虛擬人物 bug"
git push origin main

# 【步驟3】備份資料庫
mkdir -p backups
cp user_data.db backups/user_data.db.backup.$(date +%Y%m%d_%H%M%S)

# 【步驟4】運行清理腳本
python3 fix_kevin_duplicate.py

# 【步驟5】驗證修復（查看凱文記錄數應為 1）
sqlite3 user_data.db "SELECT COUNT(*) as kevin_count FROM users WHERE user_id = 776464975551660123;"

# 【步驟6】檢查虛擬人物（應為 0）
sqlite3 user_data.db "SELECT COUNT(*) as virtual_count FROM users WHERE user_id = 0;"

# 【步驟7】重啟 Bot 服務
sudo systemctl restart bot.service shopbot.service uibot.service

# 【步驟8】檢查服務狀態
sudo systemctl status bot.service shopbot.service uibot.service

# 【步驟9】查看日誌
journalctl -u bot.service -n 50 -f
```

---

## 📋 執行前檢查清單

- [ ] 確認能夠 SSH 連接到 GCP
- [ ] 確認 `/home/e193752468/kkgroup` 目錄存在
- [ ] 確認以下文件存在:
  - [ ] `sheet_driven_db.py`
  - [ ] `sheet_sync_manager.py`
  - [ ] `fix_kevin_duplicate.py`
  - [ ] `user_data.db` (資料庫)

---

## 🔍 執行中會看到的輸出

### 步驟 2: Git 提交
```
[main abc1234] Fix: 修復虛擬人物 bug
 2 files changed, 20 insertions(+), 5 deletions(-)
```

### 步驟 3: 備份
```
✅ 備份完成: /home/e193752468/kkgroup/backups/user_data.db.backup.20260206_HHMMSS
-rw-r--r-- 1 e193752468 e193752468 1024000 Feb  6 15:30 ...
```

### 步驟 4: 清理腳本
```
================================================================================
凱文重複和虛擬人物修復工具
================================================================================

✅ 備份完成: ...

診斷凱文重複問題
...
【記錄 1】
  user_id: 776464975551660123
  nickname: 凱文
  ...

修復凱文重複問題
刪除 N 個虛擬人物凱文...
  ✓ 刪除 user_id ...
  
恢復原始凱文的正確資料...
  ✓ 恢復 user_id 776464975551660123

✅ 修復完成
✅ 所有操作完成
```

### 步驟 5-6: 驗證
```
============================================================
驗證凱文修復
============================================================

✅ 凱文記錄數: 1
✅ 正確: 只有 1 個凱文

凱文詳細信息:
  user_id: 776464975551660123
  nickname: 凱文
  level: 4
  kkcoin: 111340
  ...

✅ 虛擬人物 (user_id=0): 0
✅ 正確: 已清理所有虛擬人物

✅ 異常昵稱記錄: 0
✅ 正確: 已清理所有異常昵稱

============================================================
✅ 驗證完成
============================================================
```

### 步驟 7: 重啟服務
```
Restarting bot.service...
Restarting shopbot.service...
Restarting uibot.service...
[OK]
```

---

## ⚠️ 如果出現錯誤

### 錯誤 1: Permission denied (publickey)
❌ **原因**: SSH 密鑰認證失敗
✅ **解決**: 確認你已連接到正確的 GCP 實例，或使用 gcloud CLI

### 錯誤 2: fix_kevin_duplicate.py not found
❌ **原因**: 文件未在 GCP 上
✅ **解決**: 
```bash
# 將文件複製到 GCP
scp -r c:\Users\88697\Desktop\kkgroup\fix_kevin_duplicate.py e193752468@34.80.205.45:/home/e193752468/kkgroup/
```

### 錯誤 3: sudo: systemctl not found
❌ **原因**: systemctl 不可用（可能在非 systemd 系統）
✅ **解決**:
```bash
# 如果使用其他服務管理器，調整命令
# 例如 service 而不是 systemctl
sudo service bot restart
sudo service shopbot restart
sudo service uibot restart
```

### 錯誤 4: Database is locked
❌ **原因**: 有其他進程正在訪問資料庫
✅ **解決**: 
```bash
# 先停止 Bot 服務，再運行清理
sudo systemctl stop bot.service shopbot.service uibot.service
# 等待 5 秒
sleep 5
# 再運行清理腳本
python3 fix_kevin_duplicate.py
# 最後重啟服務
sudo systemctl start bot.service shopbot.service uibot.service
```

---

## ✅ 執行完成後

### 驗收標準
1. ✅ 凱文記錄數為 1
   ```bash
   sqlite3 user_data.db "SELECT user_id, nickname, kkcoin FROM users WHERE user_id = 776464975551660123;"
   # 應顯示: 776464975551660123|凱文|111340
   ```

2. ✅ 虛擬人物已清理
   ```bash
   sqlite3 user_data.db "SELECT COUNT(*) FROM users WHERE user_id = 0;"
   # 應顯示: 0
   ```

3. ✅ Bot 服務正常運行
   ```bash
   sudo systemctl status bot.service --no-pager | grep Active
   # 應顯示: Active: active (running)
   ```

4. ✅ 日誌無錯誤
   ```bash
   journalctl -u bot.service -n 50 | grep -i error
   # 應該沒有 ERROR 信息
   ```

### 用戶驗證
1. 在 Discord 中查看凱文的昵稱和頭像
2. 嘗試與 Bot 互動，確保功能正常
3. 檢查 SHEET 同步是否正常

---

## 📞 需要幫助?

如果執行過程中遇到問題：
1. 查看日誌: `journalctl -u bot.service -n 100`
2. 檢查資料庫: `sqlite3 user_data.db ".tables"`
3. 檢查傳播修改: `git log --oneline -5`

---

**狀態**: 準備就緒 ✅
**下一步**: 複製粘貼執行命令到 GCP
**預計時間**: 5-10 分鐘
