# 凱文重複問題執行計畫

## 已完成的修復 ✅

### 修復 1: sheet_driven_db.py - 整數轉換 bug
**問題**: 空值被轉換為 0，導致虛擬人物產生
**修改**:
```python
# 修改前: except: return 0
# 修改後: except: return None

# 添加特殊處理: user_id 不能為 0
if 'id' in header_lower and result == 0:
    return None
```

### 修復 2: sheet_sync_manager.py - user_id 驗證
**問題**: 沒有驗證 user_id=0 的無效記錄
**修改**:
```python
# 添加驗證
if user_id == 0:
    error_msg = f"user_id 為 0，無效的用戶"
    print(f"⏭️ 記錄 {i}: {error_msg}")
    stats['errors'] += 1
    continue
```

---

## 於 GCP 上執行的操作

### 步驟 1️⃣: 提交修改

```bash
cd /home/e193752468/kkgroup

# 檢查修改
git diff sheet_driven_db.py sheet_sync_manager.py | head -50

# 提交修改
git add sheet_driven_db.py sheet_sync_manager.py
git commit -m "Fix: 修復虛擬人物 bug - 空值處理和 user_id 驗證"
git push origin main
```

### 步驟 2️⃣: 備份資料庫

```bash
cd /home/e193752468/kkgroup
mkdir -p backups
cp user_data.db backups/user_data.db.backup.$(date +%Y%m%d_%H%M%S)
```

### 步驟 3️⃣: 清理虛擬人物和凱文重複

```bash
cd /home/e193752468/kkgroup

# 運行清理腳本
python3 fix_kevin_duplicate.py
```

**預期輸出**:
```
================================================================================
凱文重複和虛擬人物修復工具
================================================================================

✅ 備份完成: /home/e193752468/kkgroup/backups/user_data_backup_kevin_fix_20260206_HHMMSS.db

================================================================================
診斷凱文重複問題
================================================================================

找到 2 個凱文相關記錄:

【記錄 1】
  user_id: 776464975551660123
  nickname: 凱文
  level: 4
  kkcoin: 111340
  ... 

【記錄 2】
  user_id: (某個虛擬ID)
  nickname: 凱文 或 虛擬人物
  ... (不完整的數據)
  👤 虛擬人物 (ID 不匹配) 或 ⚠️ 同步後覆蓋的凱文

================================================================================
修復凱文重複問題
================================================================================

刪除 1 個虛擬人物凱文...
  ✓ 刪除 user_id (虛擬ID)

恢復原始凱文的正確資料...
  ✓ 恢復 user_id 776464975551660123

✅ 修復完成
✅ 所有操作完成
```

### 步驟 4️⃣: 驗證修復

```bash
# 連接資料庫並驗證
cd /home/e193752468/kkgroup
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect('user_data.db')
c = conn.cursor()

print("=" * 60)
print("驗證凱文修復")
print("=" * 60)

# 1. 查詢凱文數量
c.execute("SELECT COUNT(*) FROM users WHERE user_id = 776464975551660123")
count = c.fetchone()[0]
print(f"\n凱文記錄數: {count}")
if count != 1:
    print("⚠️ 警告: 應該只有 1 個凱文記錄!")
else:
    print("✅ 正確")

# 2. 顯示凱文的詳細信息
c.execute("""
    SELECT user_id, nickname, level, xp, kkcoin, title, hp, stamina, equipment
    FROM users WHERE user_id = 776464975551660123
""")
kevin = c.fetchone()
if kevin:
    print(f"\n凱文詳細信息:")
    print(f"  user_id: {kevin[0]}")
    print(f"  nickname: {kevin[1]}")
    print(f"  level: {kevin[2]}")
    print(f"  xp: {kevin[3]}")
    print(f"  kkcoin: {kevin[4]}")
    print(f"  title: {kevin[5]}")
    print(f"  hp: {kevin[6]}")
    print(f"  stamina: {kevin[7]}")
    print(f"  equipment: {kevin[8]}")

# 3. 檢查虛擬人物（user_id=0）
c.execute("SELECT COUNT(*) FROM users WHERE user_id = 0")
virtual_count = c.fetchone()[0]
print(f"\n虛擬人物 (user_id=0): {virtual_count}")
if virtual_count > 0:
    print("⚠️ 警告: 仍有虛擬人物記錄!")
else:
    print("✅ 正確")

# 4. 檢查有問題的昵稱
c.execute("""
    SELECT COUNT(*) FROM users 
    WHERE nickname LIKE 'Unknown_%' OR nickname LIKE '虛擬%'
""")
bad_count = c.fetchone()[0]
print(f"\n異常昵稱記錄: {bad_count}")
if bad_count > 0:
    print("⚠️ 警告: 仍有異常昵稱的虛擬人物!")
else:
    print("✅ 正確")

print("\n" + "=" * 60)
print("驗證完成")
print("=" * 60)

conn.close()
EOF
```

### 步驟 5️⃣: 重啟 Bot 服務

```bash
# 重啟所有 bot 服務以加載新代碼
sudo systemctl restart bot.service shopbot.service uibot.service

# 檢查服務狀態
sudo systemctl status bot.service shopbot.service uibot.service

# 查看日誌
journalctl -u bot.service -n 50 -f
```

### 步驟 6️⃣: 測試 SHEET 同步

```bash
# 執行一次 SHEET 同步，確保新邏輯有效
curl -X POST http://localhost:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{
    "headers": ["user_id", "nickname", "level"],
    "rows": [
      ["776464975551660123", "凱文", "4"],
      ["", "虛擬凱文", ""]
    ]
  }'

# 預期: 虛擬凱文被跳過，只同步真實凱文
```

---

## 檢查清單

- [ ] **代碼修改**已推送到 GCP
- [ ] **資料庫備份**已完成
- [ ] **清理腳本**已執行
- [ ] **凱文記錄數**驗證為 1
- [ ] **虛擬人物**已清理（count=0）
- [ ] **Bot 服務**已重啟
- [ ] **SHEET 同步**測試通過
- [ ] **用戶確認**修復有效

---

## 其他需要檢查的事項

### ✅ SHEET 中凱文的數據
確認 SHEET 中凱文的信息正確：
1. user_id: 776464975551660123
2. nickname: 凱文
3. level: 應該有值
4. equipment: 應該有值或為空（不能是虛擬值）
5. 確保沒有多行重複的凱文

### ✅ 虛擬人物的來源
如果 SHEET 中仍有不完整的數據，修復後的代碼會：
- 跳過 user_id 為空或為 0 的記錄
- 記錄在日誌中，便於追蹤
- 不會產生虛擬人物

### ✅ 回溯到正確數據
原始凱文資料：
- user_id: 776464975551660123
- nickname: 凱文
- level: 1 (或應該是的等級)
- xp: 0 (或應該是的經驗值)
- kkcoin: 10000 (原始值 - 可能已更新)
- title: (根據實際情況)
- hp: 100
- stamina: 100
- equipment: (根據實際情況)

如果修復後資料不對，可以手動更新：
```sql
UPDATE users SET 
  level=1, 
  xp=0, 
  kkcoin=10000, 
  title=NULL, 
  hp=100, 
  stamina=100,
  equipment=NULL
WHERE user_id=776464975551660123;
```

---

## 預期結果

修復後：
✅ 資料庫中只有**一個**凱文 (user_id=776464975551660123)
✅ 凱文的資料是**原始正確的** No.60123 凱文
✅ **虛擬人物** bug 被修復，不會再產生 user_id=0 的幽靈記錄
✅ SHEET 同步時，空值或無效值會被跳過，不會創建虛擬人物
✅ 系統清潔，準備再次同步 SHEET

---

## 如果修復後仍有問題

1. **檢查備份**: `ls -lah /home/e193752468/kkgroup/backups/`
2. **恢復備份**: 
   ```bash
   cp backups/user_data.db.backup.TIMESTAMP user_data.db
   sudo systemctl restart bot.service
   ```
3. **檢查日誌**: `journalctl -u bot.service -n 100 | grep -i error`
4. **聯繫支持**: 提供錯誤日誌和修復過程的截圖

---

**預計執行時間**: 15-20 分鐘
**風險等級**: 低（有完整備份）
**重要性**: 🔴 高（修復數據完整性）
**狀態**: 準備就緒，awaiting GCP execution
