# 🔐 敏感信息管理指南

## 已完成的清理工作 

✅ **Git 歷史攔截**
- 已使用 `git-filter-repo` 從所有 commits 中完全移除以下文件
- 所有包含敏感信息的歷史記錄已重寫並推送到 GitHub
- 遠端內容已更新（強制推送）

### 已移除的敏感文件：
- `.env` - 包含所有 Discord Bot Tokens 和 API Keys
- `google_credentials.json` - Google Service Account Private Key  
- `web_portal/config.json` - 敏感配置

---

## ⚠️ 立即行動 - 撤銷已洩漏的 Credentials

### 1️⃣ Discord Bot Tokens（最緊急）

找到以下已洩漏的 token 並撤銷：

```
主 Bot Token: MTA1MjU3NzAxNTIyMTQ1Njk0Ng.GgP0C0.ZH2RwFNGtlvheTJ8ARu6q07zaQOmk98CRauKGA
UI Bot Token: MTM3NTgyMDM1MzQ4NTY3MjU5OQ.GDDiR9.tlB2OWitx6CDAwY-Zh-z9thK744dIcO6ps9mPM
SHOP Bot Token: MTM3NTgyNjA2OTk0ODQ2NTE1Mg.GGuEgJ.ggSSrsXc7JtK3XkwQ6gFQblZ2iZvutjM7CZLPA
```

**操作步驟：**
1. 進入 [Discord Developer Portal](https://discord.com/developers/applications)
2. 每個應用 → Bot → TOKEN → **Reset Token**（自動生成新 token）
3. 複製新 token 到本地 `.env` 文件

### 2️⃣ Google API 密鑰

```
AI_API_KEY: AIzaSyAWpBN9Vg7A0-g6GIdvSiYnqF_m6abI0bA
```

**操作步驟：**
1. 進入 [Google Cloud Console](https://console.cloud.google.com)
2. APIs & Services → Credentials → 找到該 API Key
3. **Delete** 舊的，建立新的
4. 將新 key 複製到本地 `.env`

### 3️⃣ 其他 API Keys（需逐個檢查）

- `GROQ_API_KEY` - 登入 Groq 官網重設
- `GITHUB_TOKEN` - 進入 [GitHub Settings → Tokens](https://github.com/settings/tokens) 刪除舊 token
- `HUGGINGFACE_TOKEN` - 進入 HuggingFace 帳號設定重設
- `REPLICATE_API_TOKEN` - 登入 Replicate 重設

---

## 🛡️ 未來最佳實踐

### 本地配置（不推送到 Git）
```bash
.env                          # 本地使用，已在 .gitignore 中
.env.backup.local             # 本地備份
google_credentials.json       # 本地使用，已在 .gitignore 中
```

### 在 GitHub 中使用敏感信息
**不要**在代碼中硬編碼！使用以下方式：

#### ✅ 正確做法
```python
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("AI_API_KEY")
```

#### ❌ 錯誤做法
```python
API_KEY = "AIzaSyAWpBN9Vg7A0-g6GIdvSiYnqF_m6abI0bA"  # 不要！
```

### GCP VM 同步策略
- `.env` 文件**只在本地和 GCP VM 同步**
- 使用 `gcloud compute scp` 傳輸敏感文件
- **永遠不要** 推送 `.env` 到任何 Git 倉庫

### Git 推送前檢查清單
```bash
# 推送前執行：
git diff --staged                          # 確認更改內容
git status | grep -E "\.env|credentials"  # 確保沒有敏感文件
```

---

## 📋 當前 .gitignore 規則

以下文件和模式將被 Git 忽略：

```gitignore
# 環境配置（最重要）
.env
.env.*
!.env.example
google_credentials.json
*-credentials.json
*_credentials.json
*.key
*.pem
secrets.json
config.local.json
.vault

# Cloud 配置
.aws/
.azure/
.gcp/
```

---

## 🔄 Credentials 更新流程

### 第 1 步：本機更新
1. 撤銷 GitHub 上的舊 credentials
2. 生成新 credentials
3. 複製到本地 `.env`

### 第 2 步：GCP VM 同步
```bash
# 使用 gcloud 傳輸更新的 .env
gcloud compute scp ~/.env e193752468@instance-20250501-142333:~/kkgroup/.env \
  --zone us-central1-c \
  --tunnel-through-iap
```

### 第 3 步：重啟 Bot 服務
```bash
# 在 GCP VM 上
sudo systemctl restart bot.service
sudo systemctl restart shopbot.service
sudo systemctl restart uibot.service
```

---

## ✨ 驗證清理成功

檢查 GitHub 遠端是否不再包含敏感文件：

```bash
# 應該返回空結果
git ls-tree -r origin/main | grep -E "\.env|google_credentials|credentials"
```

---

## 📞 緊急聯絡

如果發現新的密鑰洩漏：
1. **立即撤銷**該 credential
2. **生成新的** credential
3. **檢查使用情況**（是否被濫用）

---

**最後更新:** 2026年3月18日
**狀態:** ✅ 所有歷史敏感文件已清理
