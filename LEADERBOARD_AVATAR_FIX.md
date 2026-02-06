# KK幣排行榜頭像全白問題修復

## 🔍 問題診斷

### 症狀
排行榜圖片上的玩家頭像全白，而不是顯示 Discord 預設頭像

### 根本原因分析

**三個可能的原因**：

1. **🌐 網絡請求超時**
   - Discord 頭像 CDN 連接慢或不穩定
   - 舊超時設置（5 秒）太短
   - 結果：頭像加載失敗→留白→看起來全白

2. **🖼️ 無效的圖片數據**
   - Discord 返回損壞或空的圖片
   - 圖片尺寸異常（1x1 像素）
   - 結果：無法正確轉換為 Image 對象

3. **❌ FallbackMember 沒有默認頭像**
   - DB 中的用戶在 Guild 不存在時，使用 FallbackMember
   - 原來的實現：沒有為失敗的頭像加載提供灰色占位圖
   - 結果：空白區域在白色背景上看不見

## ✅ 修復方案

### 1️⃣ 添加灰色 Placeholder 頭像
```python
def create_placeholder_avatar():
    """創建灰色占位圖像（當頭像加載失敗時使用）"""
    placeholder = Image.new('RGBA', (48, 48), (200, 200, 200, 255))
    return placeholder
```

**效果**：即使頭像加載失敗，也會顯示灰色圓形，而不是白色空白

### 2️⃣ 改進 fetch_avatar() 錯誤檢查

**改進前**:
```python
async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
    if resp.status != 200:
        return None
    data = await resp.read()
    if len(data) == 0:
        return None
    return Image.open(io.BytesIO(data)).convert("RGBA")
```

**改進後**:
```python
async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:  # 增加超時
    if resp.status != 200:
        print(f"⚠️ 頭像 URL 返回 {resp.status}")  # 詳細日誌
        return None
    data = await resp.read()
    if len(data) == 0:
        print(f"⚠️ 頭像數據為空")
        return None
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    
    # 驗證圖片尺寸（避免 1x1 空圖）
    if img.size[0] < 16 or img.size[1] < 16:
        print(f"⚠️ 頭像尺寸過小: {img.size}")
        return None
    
    return img
```

**改進明細**:
- ✅ 超時時間：5 秒 → 10 秒（給予更多時間）
- ✅ 圖片驗證：新增尺寸檢查（避免 1x1 像素的無效圖）
- ✅ 詳細日誌：現在能精確診斷失敗原因
- ✅ ErrorType 識別：顯示具體的異常類型

### 3️⃣ 改進頭像顯示邏輯

**改進前**:
```python
if avatar:
    avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
    img.paste(avatar, (rank_x + 40, y), avatar)
# 如果 avatar 為 None，就不貼圖→留白
```

**改進後**:
```python
# 預先創建灰色占位圖
placeholder_avatar = create_placeholder_avatar()

# 嘗試加載真實頭像
avatar = None
try:
    avatar_url = getattr(member.display_avatar, 'url', None) if hasattr(member, 'display_avatar') else None
    if avatar_url:
        avatar = await fetch_avatar(session, avatar_url)
except Exception as e:
    print(f"❌ 頭像加載異常: {e}")

# 使用真實頭像或灰色占位圖
display_avatar = avatar if avatar else placeholder_avatar
display_avatar = display_avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
img.paste(display_avatar, (rank_x + 40, y), display_avatar)
```

**效果**:
- ✅ 所有排行位置都會顯示頭像（灰色或真實）
- ✅ 不再出現白色空白
- ✅ 失敗時優雅降級

### 4️⃣ 簡化 FallbackMember 

**改進前**:
```python
class FallbackMember:
    def __init__(self, user_id, nickname):
        self.id = user_id
        self.display_name = nickname or f"Unknown ({user_id})"
        self.display_avatar = type('obj', (object,), {'url': None})()  # 複雜的 None 設置
```

**改進後**:
```python
class FallbackMember:
    def __init__(self, user_id, nickname):
        self.id = user_id
        self.display_name = nickname or f"未知玩家 ({user_id})"
        # 不設置 display_avatar，讓 hasattr() 自然返回 False
        # 然後代碼會使用灰色 placeholder
```

## 📊 修復效果簡明對比

| 項目 | 修復前 | 修復後 |
|------|-------|-------|
| 頭像加載超時 | 5 秒 | 10 秒 |
| 加載失敗時顯示 | 白色空白 | 灰色圓形 |
| 圖片驗證 | 無 | 尺寸 + 數據檢查 |
| 診斷日誌 | 無 | 詳細（失敗原因) |
| 視覺效果 | 不完整 | 總是有頭像 |

## 🔧 如何驗證修復

### 在 Discord 執行
```
/kkcoin_rank
```

或（如果已設定頻道）：
```
/kkcoin_force_refresh
```

### 預期結果
- ✅ 所有排行位置都有頭像（真實的或灰色占位圖）
- ✅ 沒有白色空白區域
- ✅ 如果某個玩家頭像加載失敗，會顯示灰色圓形代替
- ✅ GCP 日誌中會顯示詳細的加載狀態

### 日誌示例
```
✅ 頭像加載成功: 玩家名
⚠️ 頭像 URL 返回 404: https://...
⏱️ 頭像加載超時: ...
❌ 頭像加載失敗 (urllib...): ...
```

## 💾 Git 提交

```
Commit 39094fc: 修復排行榜頭像全白問題
  - 添加灰色 fallback 頭像
  - 改進超時設置（5秒 → 10秒）
  - 添加圖片尺寸驗證
  - 改進錯誤日誌和診斷
  - 簡化 FallbackMember 實現
```

## 🚀 部署到 GCP

```bash
# SSH 到 GCP
ssh kkbot@35.201.232.62

# 更新代碼
cd kkgroup
git pull origin main

# 重啟 Bot
supervisorctl restart sheet_sync_api

# 驗證
tail -f /var/log/bot.log
```

## 📝 相關的修復歷史

- **LEADERBOARD_COMPLETE_FIX.md** - 排行榜讀取 DB 問題修復
- **LEADERBOARD_FIX_REPORT.md** - 排行榜圖片更新診斷

---

**修復完成** ✅ 代碼已推送至 GitHub
