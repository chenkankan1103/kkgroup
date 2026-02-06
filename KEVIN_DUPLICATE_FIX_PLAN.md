# 凱文重複和虛擬人物問題修復計畫

## 問題分析

### 1. 虛擬人物產生的根本原因
❌ **Bug 位置**: `sheet_driven_db.py` 的 `_convert_value()` 函數（第 688 行）

```python
# 當轉換失敗時，返回 0 而不是 None
except:
    return 0  # 這導致空值變成 user_id=0 或 level=0 等虛擬記錄
```

### 2. 為什麼會有兩個凱文
1. SHEET 中可能有兩行凱文：
   - 一行是原始的 No.60123 凱文 (完整數據)
   - 一行是不完整的凱文或虛擬版本
2. 同步時，不完整的版本因為 `_convert_value` 的 bug，字段轉換後（如 user_id=0, level=0），被當作新用戶插入
3. 或者 SHEET 中同一個 user_id 有多行，後一行覆蓋了前一行

### 3. 為什麼虛擬人物沒有頭像
當 SHEET 字段為空時：
- `_convert_value('equipment', '')` 返回 None ✅
- `_convert_value('level', '')` 返回 0 ❌（應該返回 None）
- `_convert_value('user_id', '')` 返回 0 ❌（這是最大的問題）

導致虛擬人物記錄被創建且無法正確識別和清理。

---

## 修復步驟

### 第一步：修復 sheet_driven_db.py 的 bug

**文件**: `sheet_driven_db.py`
**位置**: 第 688-690 行

```python
# 修改前
except:
    return 0

# 修改後
except:
    return None  # 轉換失敗時返回 None，而不是 0
```

或者更安全的做法：

```python
# 整數型
if any(word in header_lower for word in 
       ['id', 'level', 'xp', 'coin', 'kkcoin', 'hp', 'stamina', 
        'streak', 'count', 'num', 'amount', 'unlocked']):
    try:
        result = int(float(value))
        # user_id 不應該為 0
        if 'id' in header_lower and result == 0:
            return None
        return result
    except:
        return None  # 修改: 返回 None 而不是 0
```

### 第二步：修復 sheet_sync_manager.py 的同步邏輯

**文件**: `sheet_sync_manager.py`
**位置**: `_sync_records_to_db()` 函數

添加過濾，跳過無效記錄：

```python
# 在 _sync_records_to_db 中，增加驗證
for i, record in enumerate(records, 1):
    try:
        user_id = record.get('user_id')
        
        # ✅ 新增：跳過無效的 user_id
        if not user_id or user_id == 0:
            print(f"⏭️ 記錄 {i}: 跳過無效的 user_id={user_id}")
            stats['errors'] += 1
            continue
        
        # ... 其餘邏輯保持不變
```

### 第三步：清理資料庫中的虛擬人物

運行清理腳本（在 GCP）：

```bash
cd /home/e193752468/kkgroup

# 備份當前資料庫
cp user_data.db user_data.db.backup.$(date +%Y%m%d_%H%M%S)

# 運行修復腳本
python3 fix_kevin_duplicate.py
```

### 第四步：驗證修復

1. **檢查資料庫中凱文的記錄數**
   ```sql
   SELECT COUNT(*) FROM users WHERE user_id = 776464975551660123;
   -- 應該返回 1
   ```

2. **檢查虛擬人物**
   ```sql
   SELECT COUNT(*) FROM users WHERE user_id = 0 OR nickname = '虛擬人物';
   -- 應該返回 0
   ```

3. **驗證凱文的數據**
   ```sql
   SELECT user_id, nickname, level, xp, kkcoin, title, equipment 
   FROM users 
   WHERE user_id = 776464975551660123;
   ```

   應該返回：
   - user_id: 776464975551660123
   - nickname: 凱文
   - level: 必有
   - kkcoin: 10000 (或已正確更新的值)

---

## 代碼修改檢查表

- [ ] **sheet_driven_db.py** 修復整數轉換時返回 None 而不是 0
- [ ] **sheet_driven_db.py** 特別檢查 user_id，確保不會變成 0
- [ ] **sheet_sync_manager.py** 添加 user_id 驗證，跳過無效記錄
- [ ] 提交修改到 GCP
- [ ] 在 GCP 上運行 `fix_kevin_duplicate.py` 清理虛擬記錄
- [ ] 驗證數據庫中只有一個凱文
- [ ] SHEET 同步測試，確保不會再產生虛擬人物
- [ ] 重啟 bot 服務

---

## 長期改進建議

1. **添加數據驗證層**
   - 在入庫前驗證必需欄位（如 user_id 必須 > 0）
   - 記錄驗證失敗的原因以便調試

2. **添加虛擬人物監控**
   - 定期檢查 user_id=0 或 user_id=None 的記錄
   - 在日誌中警告並自動清理

3. **改進 SHEET 數據驗證**
   - 檢查 SHEET 中是否有空行或不完整的數據
   - 在同步前提示用戶修復

4. **測試覆蓋**
   - 為 `_convert_value()` 添加單元測試
   - 測試空值、無效值、邊界情況

---

## 修復前後對比

### 修復前
```
SHEET 中的凱文:
  row 1: user_id=776464975551660123, nickname=凱文, level=4, ...
  row 2: user_id=, nickname=凱文, level=, ... (不完整)

同步時:
  row 1 → 更新數據庫中的凱文
  row 2 → _convert_value 轉換為 user_id=0, level=0, ...
     → 產生虛擬人物記錄

結果: ❌ 兩個凱文 (776464975551660123 和 0)
```

### 修復後
```
SHEET 中的凱文:
  row 1: user_id=776464975551660123, nickname=凱文, level=4, ...
  row 2: user_id=, nickname=凱文, level=, ... (不完整)

同步時:
  row 1 → 更新數據庫中的凱文
  row 2 → _convert_value 轉換為 user_id=None, level=None, ...
     → skip: 無效的 user_id

結果: ✅ 只有一個凱文 (776464975551660123)
```

---

**優先級**: 🔴 高 - 虛擬人物問題會影響整個系統的數據完整性
**預計修復時間**: 30 分鐘（包括備份、修復、驗證、重啟）
**測試**: 修復後需要重新同步一次 SHEET 以確保修復有效
