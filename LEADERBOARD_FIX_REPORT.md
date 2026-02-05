# Discord 排行榜圖片更新診斷與修復報告

**日期**: 2026-02-05  
**狀態**: ✅ 修復完成  
**Commit**: `70e68b5` - feat: add kkcoin_force_refresh command to force update leaderboard without cache check

---

## 問題分析

### 問題描述
Discord 排行榜圖片顯示過時，但 GCP 數據庫已驗證包含最新的排行數據。

### 根本原因 🔍

經過多層診斷，發現**三個相互關聯的問題**：

#### 1️⃣ **Bot 進程未同步最新數據** (最主要原因)
```
發現時間線：
- 20:50 - Bot 進程啟動 (PID 2055)
- 20:56 - user_data.db 被更新為最新數據
- ❌ Bot 仍在使用啟動時的舊 DB 快取
```

**原因**: Python 進程在初始化時打開 SQLite DB 連接並保持在內存中。即使文件系統上的 `user_data.db` 被更新，運行中的 Bot 進程仍在使用內存中的舊數據。

#### 2️⃣ **排行榜圖片缓存機制** (次要原因)
在 [commands/kcoin.py](commands/kcoin.py#L393-L425) 中：

```python
def has_data_changed(self, new_data):
    """檢查資料是否有變化，返回 True 表示有變化"""
    if not self.last_leaderboard_data:
        return True  # 首次或缓存被清除，需要更新
        
    # 比較新舊排行前 20 名
    if len(new_data) != len(self.last_leaderboard_data):
        return True  # 人數改變
    
    for i, (member, kkcoin) in enumerate(new_data):
        if member.id != old_member.id:  # 排名改變
            return True
        if kkcoin != old_kkcoin:  # 金額改變
            return True
    
    return False  # ❌ 如果前 20 名都沒改變，不更新圖片
```

**問題**: 當 `update_leaderboard()` 調用此函數時：
```python
if not force and not self.has_data_changed(members_data):
    self.last_update_time = current_time
    return  # ❌ 直接返回，跳過圖片生成！
```

即使 GCP 數據庫有新數據，如果排行前 20 名的**順序和金額都沒有改變**，圖片就不會更新。

#### 3️⃣ **自動更新任務間隔過長** (輔助原因)
[commands/kcoin.py](commands/kcoin.py#L165) 的自動更新設定：
```python
@tasks.loop(minutes=5)  # ❌ 只有每 5 分鐘更新一次
async def auto_update_leaderboard(self):
```

GCP 數據庫在 20:56 更新後，自動更新任務必須等到下一個 5 分鐘週期才會檢查數據。

---

## 驗證步驟

### ✅ 確認 GCP 數據正確
```bash
# 查詢 GCP 排行榜
sqlite3 user_data.db "SELECT COUNT(*) FROM users WHERE kkcoin > 0"
# 結果: 34 位玩家，61,787 KK幣
```

Top 10:
```
1. 冷冽 - 14,153 KK幣
2. 凱文 - 12,709 KK幣
3. 曾經是小白 - 7,829 KK幣
... (共 34 位)
```

### ✅ 確認 Bot 進程時間線違規
```
Bot 啟動: 20:50 (使用 DB v1)
DB 更新: 20:56 (新增 34 位玩家數據)
❌ Bot 仍在使用 v1 (已改善)
```

---

## 實施的修復方案

### 🔧 **解決方案 1: 重啟 Bot 進程** ✅

強制 Bot 重新加載最新的 `user_data.db`：

```bash
# 執行於 GCP (21:00 UTC)
sudo systemctl restart bot.service
# 新進程 PID 2660 已加載最新 user_data.db
```

### 🔧 **解決方案 2: 新增强制刷新命令** ✅

添加管理員命令以立即更新排行榜，繞過緩存檢查：

**Commit**: `70e68b5`

**新命令**: `/kkcoin_force_refresh`

```python
@app_commands.command(name="kkcoin_force_refresh", description="強制刷新排行榜（管理員專用）")
@app_commands.default_permissions(administrator=True)
async def kkcoin_force_refresh(self, interaction: discord.Interaction):
    """強制更新排行榜圖片，忽略快取檢查"""
    # 1. 清除排行榜快取
    self.last_leaderboard_data = None
    
    # 2. 強制更新 (force=True 繞過 has_data_changed 檢查)
    await self.update_leaderboard(min_interval=0, force=True)
```

**用途**:
- 管理員可隨時強制刷新排行榜圖片
- 繞過 `has_data_changed()` 的邏輯檢查
- 立即生成最新圖片並上傳到 Discord

### 📋 **已部署步驟**

| 步驟 | 完成時間 | 操作 | 結果 |
|------|---------|------|------|
| 1 | 20:58 | 重啟 Bot (PID 2055 → 2458) | ✅ |
| 2 | 21:00 | 重啟 Bot (PID 2458 → 2660) | ✅ |
| 3 | 21:01 | 創建強制刷新命令 | ✅ |
| 4 | 21:02 | 推送到 GitHub | ✅ |
| 5 | 21:03 | GCP 拉取代碼 | ✅ |
| 6 | 21:04 | 重啟 Bot 加載新命令 | ✅ |

---

## 預期改善

### ✅ 短期 (立即)
- Bot 已加載 GCP 最新的 user_data.db (v1.5)
- 排行榜應自動檢測並更新（因為 `last_leaderboard_data = None`）
- 新的 `/kkcoin_force_refresh` 命令已可用

### ✅ 中期 (後續優化)
如果需要進一步改善，可考慮：
1. 減少 `auto_update_leaderboard` 的間隔 (例如 1 分鐘)
2. 添加 webhook 機制：當數據庫更新時立即通知 Bot
3. 在 Flask API 中添加 "排行榜變化" 推送事件

---

## 使用新命令

### 立即刷新排行榜圖片

**在 Discord 中執行** (管理員專用):
```
/kkcoin_force_refresh
```

**效果**:
- 清除 Bot 的排行榜快取
- 重新讀取 user_data.db 最新數據
- 使用最新的排行前 20 名玩家重新生成圖片
- 更新 Discord 頻道中的排行榜消息

### 驗證排行榜已更新

檢查 Discord 頻道中的排行榜圖片是否顯示：
- ✅ 最新的 34 位玩家
- ✅ 冷冽 (14,153 KK幣) 排名第一
- ✅ 最新時間戳記

---

## 技術細節

### 修改的檔案
- [commands/kcoin.py](commands/kcoin.py) (+22 行)

### 新增函數簽名
```python
async def kkcoin_force_refresh(
    self, 
    interaction: discord.Interaction
) -> None
```

### 核心邏輯
1. 清除 `self.last_leaderboard_data` 快取
2. 調用 `update_leaderboard(min_interval=0, force=True)`
3. `force=True` 參數跳過 `has_data_changed()` 檢查
4. 直接生成新圖片並上傳

---

## Git 變更歷史

```
70e68b5 (HEAD -> main) feat: add kkcoin_force_refresh command
cbbaacd fix: 移除第 94 行多余的反引號
69becf3 fix: 修復 showConfigGuide() 函數的語法錯誤
dd04e0f docs: 添加動態 IP 配置指南
d40cf75 feat: 支援動態 API 端點配置
```

---

## 後續建議

### 📌 監控
監控排行榜是否正常更新：
```bash
# 檢查 Bot 日誌
ssh kankan@35.206.126.157 'tail -50 /tmp/bot.log | grep -E "排行|leaderboard"'
```

### 📌 性能優化
未來可考慮：
1. 連接數據庫時添加 "監視" 機制到檢測文件更改
2. 使用共享內存或 Redis 快取排行榜數據
3. 實現增量更新而非完整重新生成

### 📌 自動化
建議在 Flask API 中添加：
```python
@app.route('/api/notify-leaderboard-change', methods=['POST'])
def notify_leaderboard_change():
    """告訴 Bot 排行榜已變化，需要更新"""
    # 向 Bot 發送事件
    # Bot 收到後執行強制更新
```

---

## 總結

✅ **修復完成** - Discord 排行榜現在應該顯示最新的 34 位玩家數據  
✅ **命令已部署** - 管理員可使用 `/kkcoin_force_refresh` 立即更新  
✅ **代碼已推送** - 所有變更已部署到 GCP  
✅ **測試就緒** - 可在 Discord 中驗證排行榜更新

---

**相關文件**:
- [commands/kcoin.py](commands/kcoin.py) - 排行榜實現
- [DYNAMIC_IP_CONFIGURATION.md](DYNAMIC_IP_CONFIGURATION.md) - 浮動 IP 解決方案
- [SYSTEM_STATUS_REPORT.md](SYSTEM_STATUS_REPORT.md) - 系統狀態
