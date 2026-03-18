# 🎮 KK 園區 Web Portal - Discord OAuth 集成完成報告

**建成時間**: 2025-02-08  
**狀態**: ✅ 後端完全實現 + 前端集成 + 文檔齊全  
**下一步**: 填入 DISCORD_CLIENT_SECRET 並進行端到端測試

---

## 📊 實現概況

### 已完成項目 ✅

#### 1. 後端 OAuth 系統 (blueprints/discord_auth.py)
- ✅ 完整的 OAuth 2.0 實現
- ✅ 6 個核心端點已實現:
  - `/api/auth/login` - 生成 OAuth 授權 URL
  - `/api/auth/callback` - 處理 Discord 回調
  - `/api/auth/verify` - 驗證 token 有效性
  - `/api/auth/user` - 取得認證用戶信息
  - `/api/auth/logout` - 登出並銷毀 session
  - `/api/auth/status` - 系統健康檢查
- ✅ Session 管理 (7 天有效期)
- ✅ 用戶角色檢查 (KK 園區伺服器成員驗證)
- ✅ @require_auth 裝飾器用於保護端點

#### 2. 前端 OAuth 集成 (docs/index.html)
- ✅ 完整的客戶端認證邏輯
- ✅ localStorage token 管理
- ✅ 用戶菜單動態生成
- ✅ 登出功能
- ✅ 頁面重載時自動驗證
- ✅ 錯誤處理和日誌記錄

#### 3. API 伺服器配置 (unified_api.py)
- ✅ Session 中間件配置
- ✅ CORS 跨域支持 (credentials enabled)
- ✅ Discord OAuth Blueprint 註冊
- ✅ 日誌記錄 (OAuth debug logs)

#### 4. 環境配置 (.env)
- ✅ Discord OAuth 變數
- ✅ 隧道 URI 配置
- ✅ Session 加密密鑰
- ⚠️ CLIENT_SECRET 需填入 (目前是佔位符)

#### 5. 文檔和工具
- ✅ OAUTH_SETUP.md - 詳細設置指南
- ✅ oauth_health_check.py - 系統診斷工具
- ✅ README.md 已更新

---

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                      GitHub Pages                              │
│             (docs/index.html - Web Portal)                     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  前端 (JavaScript)                                   │   │
│  │  - loginDiscord() → 調用 /api/auth/login             │   │
│  │  - checkAuthToken() → 從 URL 提取 auth_token        │   │
│  │  - verifyAuth() → 驗證 token 有效性                 │   │
│  │  - 動態用戶菜單 (已認證/未認證)                      │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ https://catrina-brief-fish-educators.trycloudflare.com
                       │
┌──────────────────────v──────────────────────────────────────┐
│           Cloudflare 隧道 (代理本地 Flask)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────v──────────────────────────────────────┐
│                     GCP VM (Flask API)                        │
│                   unified_api.py                              │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Discord OAuth Blueprint (blueprints/discord_auth.py) │   │
│  │                                                        │   │
│  │  1. /api/auth/login                                   │   │
│  │     → 生成 Discord OAuth URL                         │   │
│  │                                                        │   │
│  │  2. /api/auth/callback (Discord 回調)                │   │
│  │     → 交換 code 獲取 access_token                    │   │
│  │     → 獲取用戶信息 + 角色                            │   │
│  │     → 創建 session                                    │   │
│  │     → 重定向前端 /?auth_token=xxx                    │   │
│  │                                                        │   │
│  │  3. /api/auth/verify (驗證 token)                     │   │
│  │     → Bearer token 驗證                              │   │
│  │     → 返回用戶信息                                    │   │
│  │                                                        │   │
│  │  4. /api/auth/user (獲取用戶)                        │   │
│  │     → @require_auth 保護                             │   │
│  │     → 返回完整用戶數據                                │   │
│  │                                                        │   │
│  │  5. /api/auth/logout (登出)                          │   │
│  │     → 銷毀 session                                    │   │
│  │                                                        │   │
│  │  6. /api/auth/status (健康檢查)                      │   │
│  │     → 系統狀態信息                                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                                 │
│  Session Storage: in-memory dict (生產環境應使用 Redis)      │
│  - user_sessions[token] = {id, username, email, avatar, ...}│
│  - 7 天有效期                                                 │
└─────────────────────────────────────────────────────────────┘
                       │
                       │ requests.post(...discord/api/oauth2/token)
                       │
┌──────────────────────v──────────────────────────────────────┐
│                   Discord API                                 │
│         (OAuth 2.0 服務 + 用戶信息 API)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔐 OAuth Flow 詳解

### 完整流程 (5 步)

```
1. 用戶點擊「登入 DC」
   └─> fetch('/api/auth/login')
       └─> 返回: { oauth_url: "https://discord.com/api/oauth2/authorize?..." }

2. 前端重定向用戶到 Discord OAuth
   └─> window.location.href = oauth_url
       └─> 用戶在 Discord 授權應用

3. Discord 回調到我們的伺服器
   └─> GET /api/auth/callback?code=XXX&state=YYY
       ├─> POST /discord/api/oauth2/token (交換 code 獲取 token)
       ├─> GET /discord/api/users/@me (獲取用戶信息)
       ├─> GET /discord/api/users/@me/guilds (查詢用戶的伺服器)
       ├─> 檢查用戶是否在 KK 園區伺服器中
       ├─> GET /discord/api/guilds/{GUILD_ID}/members/{USER_ID} (獲取角色)
       ├─> 創建 session (user_sessions[token] = {...})
       └─> 重定向: /?auth_token=token (隱藏在 URL 中)

4. 前端提取 auth_token 並存儲
   └─> URL 參數提取 ?auth_token=token
       ├─> localStorage.setItem('auth_token', token)
       └─> window.history.replaceState() 清理 URL

5. 前端驗證 token 並顯示用戶菜單
   └─> fetch('/api/auth/verify', { Authorization: `Bearer ${token}` })
       └─> 返回: { authenticated: true, user: {...} }
           └─> 動態生成用戶菜單 (顯示用戶名 + 登出按鈕)
```

---

## 📋 當前配置狀態

### ✅ 已配置

```
✓ Discord Application ID: 1052577015221456694
✓ OAuth Redirect URI: https://katrina-brief-fish-educators.trycloudflare.com/api/auth/callback
✓ Tunnel URL: https://katrina-brief-fish-educators.trycloudflare.com
✓ Flask API: 運行在 GCP VM (localhost:5000 通過隧道暴露)
✓ CORS: 已啟用 (credentials 支持)
✓ Session: 7 天有效期
```

### ⚠️ 需要完成

```
⏳ DISCORD_CLIENT_SECRET: 需從 Discord Developer Portal 填入
  → 路徑: https://discord.com/developers/applications/1052577015221456694/oauth2
  → 當前值: YOUR_CLIENT_SECRET_HERE (佔位符)
  → 位置: .env 中的 DISCORD_CLIENT_SECRET 變數
```

---

## 🚀 快速開始

### 第 1 步: 配置 Discord Application ⚠️ 必需

```bash
# 1. 前往 Discord Developer Portal
https://discord.com/developers/applications/1052577015221456694

# 2. OAuth 2 → General
#    - 確認 Client ID: 1052577015221456694

# 3. OAuth 2 → Redirects
#    - 添加/確認: https://katrina-brief-fish-educators.trycloudflare.com/api/auth/callback

# 4. OAuth 2 → General
#    - 複製 Client Secret
```

### 第 2 步: 更新 .env

```bash
# 編輯 .env 文件，找到:
DISCORD_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE

# 改為:
DISCORD_CLIENT_SECRET=你複製的真實密鑰

# 不要上傳到 GitHub!
```

### 第 3 步: 啟動 Flask API

```bash
# SSH 到 GCP VM
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap

# 在 VM 上
cd /root/kkgroup
python3 unified_api.py
# 應該看到: WARNING in app.run, running Flask in production...
#         * Running on http://127.0.0.1:5000
```

### 第 4 步: 測試 OAuth

```bash
# 選項 A: 使用健康檢查工具
python3 oauth_health_check.py
# 會生成詳細的檢查報告

# 選項 B: 手動測試
# 打開瀏覽器: https://chenkankan1103.github.io/kkgroup/
# 點擊「登入 DC」按鈕
# 應該跳轉到 Discord 授權頁面

# 選項 C: 使用 curl 測試
curl -X GET "https://katrina-brief-fish-educators.trycloudflare.com/api/auth/login"
# 應該返回 JSON: { "oauth_url": "https://discord.com/api/oauth2/authorize?..." }
```

---

## 🧪 測試用例

### 用例 1: 完整 OAuth 流程 (E2E)

```bash
✅ 步驟:
1. 打開前端: https://chenkankan1103.github.io/kkgroup/
2. 點擊「登入 DC」
3. 看到 Discord 授權對話框
4. 點擊「授權」
5. 重定向回 Web Portal
6. 看到用戶名顯示在導航欄 (替代登入按鈕)

❌ 常見問題:
- "INVALID_CLIENT" → CLIENT_SECRET 不對
- "Redirect URI mismatch" → /api/auth/callback URL 不匹配
- "隱藏隧道後無法連接" → Flask 沒有運行或隧道已重啟
```

### 用例 2: Token 驗證

```bash
curl -X GET "https://katrina-brief-fish-educators.trycloudflare.com/api/auth/verify" \
  -H "Authorization: Bearer your_token_here"

# 預期回應:
# { "authenticated": true, "user": { "id": "...", "username": "...", ... } }
```

### 用例 3: 登出

```bash
curl -X POST "https://katrina-brief-fish-educators.trycloudflare.com/api/auth/logout" \
  -H "Authorization: Bearer your_token_here"

# 預期回應:
# { "success": true, "message": "已成功登出" }
```

---

## 🔧 故障排查

### 問題 1: "無法連接隧道"

**原因**: Flask API 沒有運行

**解決**:
```bash
# SSH 到 GCP VM
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 檢查進程
ps aux | grep python3

# 啟動 Flask
python3 unified_api.py
```

### 問題 2: "INVALID_CLIENT 錯誤"

**原因**: DISCORD_CLIENT_SECRET 不正確

**解決**:
```bash
# 1. 驗證 .env 中的值
grep DISCORD_CLIENT_SECRET .env

# 2. 確認與 Discord Portal 中的值相同
# https://discord.com/developers/applications/1052577015221456694
```

### 問題 3: "隧道 URL 變更"

如果重啟 cloudflared，URL 可能變更

**解決**:
```bash
# 1. 更新 .env 中的 DISCORD_REDIRECT_URI
# 2. 更新 Discord Portal 中的 Redirect URIs
# 3. 重啟 Flask API
```

### 問題 4: "前端一直不能登錄"

**檢查清單**:
- [ ] Flask API 運行中? → 檢查 GCP VM
- [ ] 隧道 URL 正確? → 檢查 config.json
- [ ] CLIENT_SECRET 正確? → 檢查 .env
- [ ] 瀏覽器控制台有否錯誤? → F12 → Console
- [ ] 隧道日誌是否有錯誤? → `gcloud compute ssh... "journalctl -u cloudflared -n 50"`

---

## 📁 文件清單

| 文件 | 狀態 | 說明 |
|------|------|------|
| `blueprints/discord_auth.py` | ✅ 2025-02-08 | Discord OAuth 後端 (181 行) |
| `docs/index.html` | ✅ 2025-02-08 | 前端 Web Portal (OAuth 集成) |
| `unified_api.py` | ✅ 2025-02-08 | 更新了 session/CORS 配置 |
| `.env` | ✅ 2025-02-08 | OAuth 環境變數 (需填 SECRET) |
| `OAUTH_SETUP.md` | ✅ 2025-02-08 | 詳細設置指南 |
| `oauth_health_check.py` | ✅ 2025-02-08 | 系統診斷工具 |

---

## ✨ 新增功能

### 前端功能

- ✨ OAuth 登入流程
- ✨ Token localStorage 管理
- ✨ 用戶菜單動態生成
- ✨ 自動 token 驗證
- ✨ 登出功能
- ✨ 錯誤處理

### 後端功能

- ✨ 完整 OAuth 2.0 實現
- ✨ Session 管理 (7 天有效期)
- ✨ 用戶角色檢查
- ✨ 保護的端點 (@require_auth)
- ✨ 詳細的錯誤消息和日誌

---

## 📞 後續工作

### 立即可做 (5-10 分鐘)

1. ✅ 獲取 Discord CLIENT_SECRET
2. ✅ 更新 .env
3. ✅ 在 GCP VM 上啟動 Flask
4. ✅ 測試 OAuth 流程

### 短期 (1-2 小時)

1. ⏳ 連接排行榜 API (`/api/stats/detailed`)
2. ⏳ 連接商店 API (`GET /shop/items`)
3. ⏳ 連接股市 API (`GET /api/stocks/data`)
4. ⏳ 測試完整的 Web Portal

### 中期 (後續)

1. ⏳ 實裝 Session 存儲到 Redis (生產級)
2. ⏳ 添加更多用戶信息顯示
3. ⏳ 實現角色徽章顯示
4. ⏳ 添加用戶偏好設置

---

## 🎯 成功標誌

OAuth 系統成功運作的標誌:

```
✅ 用戶點擊「登入 DC」後跳轉到 Discord
✅ 用戶授權後重定向回 Web Portal
✅ 導航欄顯示用戶名和登出按鈕
✅ 刷新頁面時保持登入狀態
✅ 點擊登出後返回登入按鈕
✅ 控制台無 CORS 或 OAuth 錯誤
```

---

## 📊 技術統計

| 指標 | 值 |
|------|-----|
| 後端代碼行數 | 181 行 (discord_auth.py) |
| OAuth 端點數 | 6 個 |
| 前端函數數 | 8 個 (auth 相關) |
| 配置變數 | 4 個 |
| 文檔頁數 | 3 份 (OAUTH_SETUP.md + 本文件 + inline comments) |
| 測試選項 | 3 種 (curl + 前端 + health check) |

---

**最後更新**: 2025-02-08  
**下一步**: 填入 DISCORD_CLIENT_SECRET 並進行端到端測試！ 🚀

