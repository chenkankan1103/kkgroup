# 🪝 GitHub Webhook 自動部署指南

## 📋 概述

此功能允許你在 GitHub 上 push 代碼時，VM 會自動接收通知、拉取最新代碼並重啟所有服務。

**優點:**
- ✅ 零定期輪詢，節省 97% 出站流量
- ✅ 推送即刻自動部署
- ✅ Discord 實時部署消息
- ✅ 簽名驗證，安全可靠

---

## 🔧 第一步：環境設置

### 1. 檢查 .env 文件

確保 `.env` 中有以下變量（已存在無需修改）:

```bash
GITHUB_WEBHOOK_SECRET="your-secret-password-here"
DISCORD_BOT_TOKEN="your-discord-token"
DISCORD_SYS_CHANNEL_ID="your-channel-id"
```

**⚠️ 重要：**
- `GITHUB_WEBHOOK_SECRET` 要設置為一個強密碼（20+ 字符）
- 這個密鑰必須同時存入 .env 和 GitHub 設置，用於驗證 webhook 簽名

---

## 🌐 第二步：GitHub 倉庫設置

### 進入 GitHub Settings

1. 打開你的倉庫: https://github.com/chenkankan1103/kkgroup
2. 進入 **Settings** → **Webhooks**

### 新增 Webhook

点击 **Add webhook** 按鈕

### 填寫配置

| 欄位 | 值 |
|------|-----|
| **Payload URL** | `http://your-vm-ip:5000/webhook/github` |
| **Content type** | `application/json` |
| **Secret** | 與 .env 中的 `GITHUB_WEBHOOK_SECRET` 相同 |

**例子:**
```
Payload URL: http://203.0.113.45:5000/webhook/github
Content type: application/json  ✓
Secret: sup3r_s3cr3t_p@ssw0rd_123456
```

### 選擇事件

- 取消勾選 "Send me everything"
- 勾選 **Push events** ✅

### 啟用 Webhook

- 確保 **Active** 被勾選
- 點擊 **Add webhook**

---

## 📍 關鍵步驟：獲取 VM IP

你需要知道 GCP VM 的外部 IP 地址。

### 查詢方式

**方式 1: 在 GCP Console**
```
VM Instances → 你的實例 → 外部 IP
```

**方式 2: 通過 SSH 執行**
```bash
curl -s https://checkip.amazonaws.com
# 或
hostname -I
```

**例子:**
- Payload URL: `http://203.0.113.45:5000/webhook/github`
- 將 `203.0.113.45` 替換為你的實際 IP

---

## ✅ 第三步：測試 Webhook

### 在 GitHub 中測試

1. 進入 Webhooks 設置頁面
2. 找到剛創建的 webhook
3. 向下滾動找到 **Recent Deliveries**
4. 點擊最新項目，查看請求和響應

**預期響應:**
```json
{
  "status": "success",
  "message": "自動部署完成",
  "details": {
    "git_pull": "Git pull 成功",
    "restart": "所有服務重啟成功"
  }
}
```

### 在 VM 上檢查日誌

```bash
# 查看 API 服務日誌
sudo journalctl -u kkgroup-api.service -n 50 --no-pager

# 查看具體的 webhook 相關日誌
sudo journalctl -u kkgroup-api.service -n 100 --no-pager | grep -i webhook

# 實時監控
sudo journalctl -u kkgroup-api.service -f
```

---

## 🧪 完整測試流程

### 1. 確保 API 服務運行

```bash
# SSH 進入 GCP VM
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 檢查服務狀態
sudo systemctl status kkgroup-api.service
```

### 2. 做個小改動並 Push

在本地機器上:
```bash
cd /path/to/kkgroup

# 做個小改動（例如修改 README）
echo "# Test webhook" >> README.md

# Commit 並 push
git add README.md
git commit -m "test: webhook deployment test"
git push origin restructure-project-20260414
```

### 3. 監控日誌

```bash
# 方式 1: 看 webhook 健康檢查
curl http://203.0.113.45:5000/webhook/health

# 方式 2: 查詢 GitHub webhook 日誌（GitHub 頁面）
# Settings → Webhooks → Recent Deliveries

# 方式 3: 檢查 Discord 通知
# 看系統頻道是否收到自動部署消息
```

---

## 🔐 安全考慮

### 签名验证

Webhook 使用 HMAC-SHA256 簽名驗證，確保請求來自 GitHub:

```python
# webhook.py 中的驗證邏輯
import hmac, hashlib

signature = hmac.new(
    GITHUB_WEBHOOK_SECRET.encode(),
    payload_body,
    hashlib.sha256
).hexdigest()

expected = f"sha256={signature}"
assert hmac.compare_digest(expected, signature_header)
```

### 分支過濾

- 只有 `restructure-project-20260414` 分支的 push 會觸發自動部署
- 其他分支的 push 會被忽略（安全起見）

---

## 📊 流量對比

### 舊方案 (Cron 輪詢)
```
每 5 分鐘 → git fetch → GitHub API
每天 288 次 × 200KB ≈ 57.6MB/天
月度 ≈ 1.7GB
```

### 新方案 (Webhook)
```
Push 時 → GitHub 主動發送
每天僅當有 push 時觸發
估計 ≈ 50MB/月
節省 97%+ 出站流量！ 🎉
```

---

## 🛠️ 常見問題

### Q: Webhook 沒有被觸發？

**檢查清單:**
1. API 服務是否運行？ `sudo systemctl status kkgroup-api.service`
2. IP 地址正確嗎？ 檢查當前外部 IP
3. 防火牆允許 5000 端口嗎？
4. .env 中的密鑰設置正確？
5. 檢查 GitHub webhook Recent Deliveries 中的錯誤信息

### Q: 簽名驗證失敗？

- 確保 .env 中的 `GITHUB_WEBHOOK_SECRET` 與 GitHub 設置中的 **Secret** 完全相同
- 重啟 API 服務: `sudo systemctl restart kkgroup-api.service`

### Q: Git pull 失敗？

- 檢查 .git/index.lock: `ls -la /home/e193752468/kkgroup/.git/index.lock`
- 檢查分支名稱是否為 `restructure-project-20260414`
- 查看日誌: `sudo journalctl -u kkgroup-api.service -n 50`

### Q: 服務重啟失敗？

- 檢查 systemd 配置: `sudo systemctl status bot.service`
- 檢查 sudo 權限: `sudo visudo` (確保允許無密碼重啟)

---

## 📚 相關檔案

| 檔案 | 用途 |
|------|------|
| `web/blueprints/webhook.py` | Webhook 接收器邏輯 |
| `web/api/unified_api.py` | 主 Flask API，已整合 webhook |
| `scheduled_tasks/update_restart.py` | 已優化，改為 30 分鐘 fetch 間隔（可選禁用） |

---

## 🚀 後續步驟

### 選項 1: 禁用舊的 Cron 任務（推薦）

如果改用 webhook，可以禁用 crontab 中的：
```bash
# 從 crontab 中移除或註釋掉
*/5 * * * * /path/to/update_restart.py
```

### 選項 2: 保留 Cron 作為備用

如果要保留舊方案作為備用（多重保障），保持目前的 30 分鐘 fetch 間隔即可。

---

## 💡 提示

- Webhook 優先級高於 Cron。有 webhook 時優先使用
- Discord 消息會顯示部署詳情（提交信息、修改檔案等）
- 可在 GitHub 的 webhook settings 中看到完整的請求/響應日誌
