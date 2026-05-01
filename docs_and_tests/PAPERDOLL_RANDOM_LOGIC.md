# 紙娃娃隨機造型系統 (2026-05-01)

## 修復內容
新用戶加入時現在會獲得隨機造型，而不是固定的預設造型。

### 修改位置
**文件**: `cogs/ui/welcome_message.py`  
**方法**: `WelcomeFlow.create_user_data()`  
**Commit**: `47b30914`

## 實現邏輯

### ✅ 新用戶加入 → 隨機造型
```python
def create_user_data(self, user_id: int) -> bool:
    # 生成隨機造型（男/女各占 50%）
    random_appearance = paperdoll_manager.get_random()
    
    user_data = {
        'user_id': user_id,
        'face': int(random_appearance['face']),
        'hair': int(random_appearance['hair']),
        'skin': int(random_appearance['skin']),
        'top': int(random_appearance['top']),
        'bottom': int(random_appearance['bottom']),
        'shoes': int(random_appearance['shoes']),
        'gender': random_appearance['gender'],
        # ...其他欄位
    }
```

### ✅ 用戶選擇性別 → 再次隨機造型
在 `PersistentWelcomeView.gender_select()` 中：
```python
# 保持性別不變，生成符合該性別的隨機造型
selected_gender = select.values[0]  # 'male' 或 'female'
appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)
await self.cog.update_user_data(user_id, appearance)
```

## 核心規則

### ❌ 不要硬編碼
```python
# ❌ 錯誤做法（舊版）
'face': 20005,
'hair': 30120,
'top': 1040014,
# ...硬編碼的預設值
```

### ✅ 要調用 get_random()
```python
# ✅ 正確做法
random_appearance = paperdoll_manager.get_random()
# 或指定性別
random_appearance = paperdoll_manager.get_random(preserve_gender='female')
```

## 資料來源

### 有效物品 ID
- **來源**: `twms_fashion_db.json` - 楓之谷台灣伺服器物品資料庫
- **性別分類**: `CHARACTER_VARIATIONS` 字典
  - `face_male` / `face_female` - 男/女臉型
  - `hair_male` / `hair_female` - 男/女髮型
  - `top_male` / `top_female` - 男/女上衣
  - `bottom_male` / `bottom_female` - 男/女下裝
  - `shoes` - 鞋子（無性別分類）

### 性別一致性
- **男性角色**: 選擇 `face_male` / `hair_male` / `top_male` 等
- **女性角色**: 選擇 `face_female` / `hair_female` / `top_female` 等
- **中性部件**: 衣服無性別標籤時，男女都可使用

## 部署流程

### 1. 代碼修改
修改 `create_user_data()` 調用 `get_random()`

### 2. Git 提交與推送
```bash
git add cogs/ui/welcome_message.py
git commit -m "fix: 新用戶加入時生成隨機造型"
git push origin main
```

### 3. Webhook 自動觸發
- GitHub push → Cloudflare 隧道 → kkgroup-api
- webhook.py 驗證並觸發 `git pull` 和服務重啟
- 所有 Bot (bot.service, shopbot.service, uibot.service) 自動重啟

### 4. 驗證
- 新成員加入 Discord 伺服器
- 檢查歡迎訊息中的紙娃娃是否為隨機造型（非預設）
- 確認用戶選擇性別後顯示新的隨機造型

### 5. 刷新（如需整體更新）
執行指令刷新所有用戶：
```bash
/admin_refresh_all_lockers
```

## API URL 構建

**重要**: 所有紙娃娃 API URL 必須透過 `paperdoll_manager.build_api_url()` 構建

```python
# ✅ 正確做法
character_image_url = paperdoll_manager.build_api_url(user_data)

# ❌ 不要手動組合 URL
url = f"https://maplestory.io/api/character/..."  # 這會被 Discord 擋住
```

**原因**: MapleStory API 要求 User-Agent header，Discord 沒有發送 → 403 Forbidden  
**解決**: 代理 URL 轉發請求並添加必要的 header

## 常見問題

### Q: 新用戶造型還是預設的？
A: 檢查 `create_user_data()` 是否調用 `get_random()`；  
如果看到硬編碼值（如 `'face': 20005`），則需要修復。

### Q: 如何確認修改已生效？
A: 1. Git log 確認 commit  
   2. 新成員加入測試  
   3. 檢查日誌：`sudo journalctl -u bot.service -n 50 | grep "paperdoll"`

### Q: 性別一致性檢查失敗？
A: 確認 `twms_fashion_db.json` 中物品名稱包含正確的性別標籤（"(男)"/"(女)"）

---

**最後更新**: 2026-05-01  
**相關 Commit**: 47b30914  
**相關檔案**: cogs/ui/welcome_message.py, cogs/ui/utils/paperdoll_manager.py
