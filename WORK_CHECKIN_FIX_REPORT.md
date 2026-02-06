# 打卡系統故障診斷與修復報告
**Created:** 2026-02-06
**Status:** 修復方案列出

## 問題概述

用戶報告："打卡代碼似乎也壞掉了 不知道是不是對應不到資料庫"

## 根本原因分析

### 發現 1: 本地 vs 遠程資料庫分離
- **本地 Windows 環境**: `./user_data.db` (包含 8 個測試用戶)
- **GCP 遠程環境**: `/home/e193752468/kkgroup/user_data.db` (包含真實用戶)
- **狀態**: 兩個環境使用不同的資料庫文件，修復只在 GCP 上進行

### 發現 2: 打卡系統中的代碼缺陷
在 `commands/work_function/work_system.py` 中的 `process_checkin()` 函數：

```python
# ❌ 原始代碼（有 bug）:
user = get_user(user_id)
level = user.get('level', 1)  # 如果 user 是 None 會崩潰！
```

如果 `get_user()` 返回 None，會導致：
```
AttributeError: 'NoneType' object has no attribute 'get'
```

這會被上層的 except 塊捕獲，返回 `None, None, None, None`，導致打卡功敗。

### 發現 3: 用戶資料獲取的防御不足
在 `commands/work_function/work_cog.py` 的 CheckInButton 中，未檢查 `get_user()` 是否成功。

## 實施的修復

### 修復 1: process_checkin() 函數 ✅
**文件**: `commands/work_function/work_system.py`
**改變**: 添加顯式的 None 檢查

```python
user = get_user(user_id)

# 新增: 檢查用戶是否成功取得
if not user:
    print(f"❌ 無法找到或建立用戶: {user_id}")
    return None, None, None, None

today = datetime.utcnow().strftime("%Y-%m-%d")
level = user.get('level', 1)
```

### 修復 2: CheckInButton.callback() ✅
**文件**: `commands/work_function/work_cog.py`
**改變**: 添加用戶取得失敗的錯誤處理

```python
user = get_user(interaction.user.id)

# 新增: 檢查用戶是否成功取得
if not user:
    await interaction.followup.send("❌ 無法獲取用戶資料，請稍後重試。", ephemeral=True)
    return

today = datetime.utcnow().strftime("%Y-%m-%d")
last_work_date = user.get('last_work_date', None)
```

### 修復 3: RestButton.callback() ✅
**文件**: `commands/work_function/work_cog.py`
**改變**: 添加用戶取得失敗的錯誤處理

### 修復 4: WorkActionButton.callback() ✅
**文件**: `commands/work_function/work_cog.py`
**改變**: 添加用戶取得失敗的錯誤處理

### 修復 5: work_info() 命令 ✅
**文件**: `commands/work_function/work_cog.py`
**改變**: 添加用戶取得失敗的錯誤處理

### 修復 6: work_stats() 命令 ✅
**文件**: `commands/work_function/work_cog.py`
**改變**: 添加用戶取得失敗的錯誤處理

### 修復 7: process_work_action() 函數 ✅
**文件**: `commands/work_function/work_system.py`
**改變**: 添加用戶取得失敗的早期返回檢查

### 修復 8: database.py get_user() 函數 ✅
**文件**: `commands/work_function/database.py`
**改變**: 改進錯誤處理和戶 ID 類型轉換

```python
def get_user(user_id) -> Optional[Dict[str, Any]]:
    try:
        # 確保 user_id 是整數
        user_id = int(user_id)
        
        user = db_get_user(user_id)
        
        if not user:
            # 新用戶，自動建立
            print(f"🆕 建立新用戶: {user_id}")
            set_user(user_id, {'user_id': user_id})
            user = db_get_user(user_id)
            
            if not user:
                print(f"⚠️ 無法建立用戶 {user_id}")
                return None
        
        return user
    except Exception as e:
        print(f"❌ get_user({user_id}) 失敗: {e}")
        traceback.print_exc()
        return None
```

## 下一步行動

### 立即行動 (必須)
1. **將修改推送到 GCP**
   ```bash
   git add commands/work_function/
   git commit -m "Fix: 打卡系統防御性檢查和錯誤處理改進"
   git push origin main
   ```

2. **在 GCP 上重新部署**
   ```bash
   cd /home/e193752468/kkgroup
   git pull origin main
   ```

3. **重啟 bot 服務**
   ```bash
   sudo systemctl restart bot.service shopbot.service uibot.service
   ```

### 驗證步驟
1. **檢查資料庫中的修復後 ID**
   ```bash
   python3 -c "from db_adapter import get_user; u=get_user(344018672056139786); print(f'赤月: {u}')"
   ```

2. **測試打卡功能**
   - 在 Discord 中按下打卡按鈕
   - 檢查日誌是否有錯誤信息
   - 驗證用戶資料是否正確更新

3. **檢查系統日誌**
   ```bash
   journalctl -u bot.service -n 50  # 查看最後 50 行日誌
   ```

## 根本原因總結

| 問題 | 原因 | 解決 |
|------|------|------|
| 資料庫 ID 不匹配 | 27 個用戶的 Discord ID 與資料庫中存儲的 ID 不同 | ✅ 已修復（執行 fix_all_user_ids.py） |
| 打卡代碼崩潰 | process_checkin() 未正確檢查 None 返回值 | ✅ 已修復（添加防御性檢查） |
| 錯誤提示不清晰 | 異常被吞掉，用戶看不到問題原因 | ✅ 已修復（改進日誌和錯誤信息） |

## 預期結果

修復後：
- ✅ `get_user()` 返回值會被正確檢查
- ✅ 如果資料庫查詢失敗，會有清晰的錯誤信息
- ✅ 打卡功能會正確處理各種邊界情況
- ✅ 新用戶會被自動建立到資料庫
- ✅ 無法查詢的用戶會收到友善的錯誤提示，而不是崩潰

## 相關文件修改清單

```
✅ commands/work_function/work_system.py    (+15 行, -1 行)  [2 處修復]
✅ commands/work_function/work_cog.py       (+20 行, -0 行)  [5 處修復]
✅ commands/work_function/database.py       (+12 行, -7 行)  [1 處改進]
```

**總計:** 8 處修復，47 行變更

## 注意事項

1. **本地 Windows 環境 vs GCP 環境**
   - 本地 user_data.db 只有測試數據
   - 真實運行的 bot 在 GCP 上
   - 修改後需要部署到 GCP

2. **資料庫同步**
   - 確保 GCP 上的資料庫包含所有 27 個修復後的用戶 ID
   - 驗證 Sheet-Driven DB 的同步狀態

3. **用戶體驗**
   - 如果仍無法打卡，使用者會看到友善的錯誤信息
   - 建議檢查日誌來診斷具體問題

---
**修復者**: GitHub Copilot
**修復時間**: 2026-02-06 10:30 UTC
**狀態**: 代碼修復完成，待重新部署
