# Discord OAuth 2.0 設置指南

## 📋 系統要求

- Discord OAuth 後端: ✅ 已設置 (`blueprints/discord_auth.py`)
- 前端集成: ✅ 已完成 (`docs/index.html`)
- 隧道 URL: ✅ https://katrina-brief-fish-educators.trycloudflare.com
- Flask API 服務: 需要在 GCP VM 上運行

---

## 🔐 Step 1: 設置 Discord Application

### 1.1 建立/編輯 Discord 應用

1. 前往 **[Discord Developer Portal](https://discord.com/developers/applications)**
2. 應用名稱: **KK 園區**
3. 應用 ID (Client ID): `1052577015221456694` ✅ (已配置)

### 1.2 獲取 Client Secret

1. 在應用頁面，進入 **"OAuth 2"** 分頁
2. 複製 **Client Secret** (這是所有設置中最重要的部分!)
3. ⚠️ **保密保管** - 不要上傳到 GitHub

### 1.3 設置 Redirect URI

在 OAuth 2 → Redirects 中添加:
```
https://katrina-brief-fish-educators.trycloudflare.com/api/auth/callback
```

### 1.4 設置 Scopes (權限)

勾選以下权限:
- `identify` - 獲取用戶 ID 和用戶名
- `email` - 獲取郵箱
- `guilds` - 查詢用戶的 Discord 伺服器列表
- `guilds.members.read` - 讀取伺服器成員信息

---

## 🛠️ Step 2: 更新 .env 配置

### 2.1 編輯 `.env` 文件

找到以下部分:
```env
# Discord OAuth 認證配置 (Web Portal)
DISCORD_CLIENT_ID=1052577015221456694
DISCORD_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE  # ← 改這裡!
DISCORD_REDIRECT_URI=https://katrina-brief-fish-educators.trycloudflare.com/api/auth/callback
SESSION_SECRET=kk_session_secret_2026_kkgroup
```

### 2.2 填入真實的 Client Secret

```bash
# 使用編輯器打開 .env，將 YOUR_CLIENT_SECRET_HERE 改為:
DISCORD_CLIENT_SECRET=你的真實密鑰
```

例如:
```env
DISCORD_CLIENT_SECRET=abc123xyz_your_real_secret_here
```

---

## ✅ Step 3: 驗證配置

### 3.1 檢查後端配置

```bash
# 確認 discord_auth.py 已創建
ls -la blueprints/discord_auth.py

# 確認 unified_api.py 已註冊 blueprint
grep -n "discord_auth_bp" unified_api.py
```

### 3.2 測試 OAuth 流程

**在本地測試** (需要在 GCP VM 上運行 Flask):

```bash
# 1. SSH 到 GCP VM
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 2. 啟動 Flask API
cd /root/kkgroup
python3 unified_api.py

# 3. 在瀏覽器中測試
# 打開: https://katrina-brief-fish-educators.trycloudflare.com/api/auth/login
# 應該返回 JSON 格式的 oauth_url
```

### 3.3 完整 OAuth 流程測試

```bash
# 方法 1: 使用 curl 測試
curl -X GET "https://katrina-brief-fish-educators.trycloudflare.com/api/auth/login"

# 方法 2: 打開前端頁面
# https://chenkankan1103.github.io/kkgroup/
# 點擊「登入 DC」按鈕，應該跳轉到 Discord 認證頁面
```

---

## 🎯 OAuth Flow 詳解

### 用戶登入流程:

1. **前端**: 用戶點擊「登入 DC」按鈕
   ```javascript
   → fetch('/api/auth/login')
   ```

2. **後端 `/api/auth/login`**: 返回 Discord OAuth URL
   ```json
   {
     "oauth_url": "https://discord.com/api/oauth2/authorize?client_id=...&scope=..."
   }
   ```

3. **Discord**: 用戶授權應用
   - 用戶看到 Discord 認證頁面
   - 授權後重定向回應用

4. **後端 `/api/auth/callback`**: 處理回調
   - 接收 `code` 參數
   - 發送 POST 請求到 Discord 取得 `access_token`
   - 使用 token 獲取用戶信息
   - 查詢用戶在 KK 園區伺服器的角色
   - 創建 session
   - 重定向到前端: `/?auth_token=xxx`

5. **前端**: 接收認證 token
   - 從 URL 提取 `auth_token`
   - 存儲到 localStorage
   - 調用 `/api/auth/verify` 驗證
   - 顯示用戶信息和登出按鈕

---

## 🐛 常見問題

### Q1: "INVALID_CLIENT" 錯誤

**原因**: Client Secret 不正確

**解決**:
```bash
# 確認 .env 中的 SECRET 與 Discord Portal 中相同
cat .env | grep DISCORD_CLIENT_SECRET
```

### Q2: "Redirect URI mismatch" 錯誤

**原因**: .env 中的 REDIRECT_URI 與 Discord Portal 中不匹配

**解決**:
```bash
# .env 中必須完全相同
DISCORD_REDIRECT_URI=https://katrina-brief-fish-educators.trycloudflare.com/api/auth/callback
```

### Q3: 隧道 URL 變更

如果隧道重啟，URL 可能會變更:
```bash
# 1. 使用自動更新工具
python3 update_tunnel_url.py

# 2. 更新 Discord Portal 中的 Redirect URIs
# https://discord.com/developers/applications/1052577015221456694/oauth2

# 3. 更新 .env 中的 DISCORD_REDIRECT_URI
```

---

## 📊 後端端點參考

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/auth/login` | GET | 獲取 Discord OAuth URL |
| `/api/auth/callback` | GET | 處理 Discord 回調 |
| `/api/auth/verify` | GET | 驗證 token 有效性 |
| `/api/auth/user` | GET | 取得認證用戶信息 (需要 Bearer token) |
| `/api/auth/logout` | POST | 登出並銷毀 session |
| `/api/auth/status` | GET | 檢查系統狀態 |

---

## 🚀 下一步

1. ✅ 更新 `.env` 中的 `DISCORD_CLIENT_SECRET`
2. ✅ 在 GCP VM 上啟動 Flask API
3. ✅ 測試 `/api/auth/login` 端點
4. ⏳ 測試完整的前端 OAuth 流程
5. ⏳ 連接排行榜、商店、股市數據

---

## 📞 支持

如有問題，請檢查:
1. `.env` 配置是否正確
2. Flask API 是否運行
3. 隧道是否連接正常
4. Discord Portal 中的 OAuth 設置

