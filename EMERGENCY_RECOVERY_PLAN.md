# 🚨 系統斷線 - 緊急恢復計畫

## 📊 當前狀態診斷

### 已確認的事實
- ✅ GCP VM 狀態: **RUNNING** (verified via `gcloud compute instances describe`)
- ❌ IAP SSH 隧道: **無回應** (所有 SSH 命令均超時)
- ⚠️ Cloudflared 隧道: 最後於 **2026-05-03 03:48:17** 重新連接
- 📦 config.json 隧道 URL: `https://weekly-charge-gage-diana.trycloudflare.com` (最後更新 2026-04-30)
- 📝 Webhook 日誌: 無最新記錄 (上次 2026-05-02)

### 根本原因分析

1. **隧道重新連接** (05-03 03:47-03:48)
   - Cloudflared 進程斷開連接，重新獲得新的隧道 URL
   - 新的隧道 URL 未知 (IAP 隧道無法查詢)

2. **Config.json 未更新**
   - config.json 中的隧道 URL 仍是舊的 (April 30 版本)
   - auto_update_webhook.py 無法成功執行

3. **IAP 隧道故障** (次要問題)
   - gcloud SSH 命令持續超時
   - 可能是 IAP 連接池問題或 GCP 側故障

## 🔧 解決方案 (分級)

### 方案 A: 直接 SSH (推薦首先嘗試)

```bash
# 1️⃣ 嘗試不經 IAP 的直接 SSH
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --command "sudo journalctl -u cloudflared.service -n 10 | grep -i 'registered\|tunnel'"

# 2️⃣ 如果上述有回應，提取新隧道 URL
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --command "bash -c 'sudo journalctl -u cloudflared.service -n 50 | grep \"https://\" | tail -1'"

# 3️⃣ 或直接重啟 cloudflared 並查看新 URL
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --command "sudo systemctl restart cloudflared.service && sleep 5 && sudo journalctl -u cloudflared.service -n 5"
```

### 方案 B: 如果直接 SSH 也不行

#### B-1: 通過 GCP 控制台
1. 進入 [GCP Console](https://console.cloud.google.com)
2. 導航: `Compute Engine` → `VM instances` → `instance-20250501-142333`
3. 點擊 `三個點` → `連接至 SSH`
4. 運行以下命令:
   ```bash
   sudo journalctl -u cloudflared.service -n 50 --no-pager | grep "trycloudflare" | tail -1
   ```

#### B-2: 使用 gcloud compute instances get-serial-port-output
```bash
gcloud compute instances get-serial-port-output instance-20250501-142333 \
  --zone us-central1-c | tail -100
```

### 方案 C: 手動更新配置 (一旦獲得新 URL)

1. **獲得新隧道 URL** (使用上述任一方案)

2. **更新本地 config.json**
   ```bash
   # 方法 1: 使用提供的修復腳本
   python3 fix_webhook_emergency.py "https://NEW-TUNNEL-URL.trycloudflare.com"
   
   # 方法 2: 直接編輯
   # 編輯 config/config.json
   # 將 "url" 改為新的隧道 URL
   # 將 "API_BASE" 改為新的隧道 URL
   ```

3. **提交並推送**
   ```bash
   git add config/config.json
   git commit -m "chore: restore tunnel URL after cloudflared restart"
   git push
   ```

4. **驗證 Webhook 更新**
   - GitHub webhook 會在代碼推送時自動觸發
   - 檢查 Discord 系統頻道是否有部署通知

### 方案 D: 完整重啟 (如果以上都不行)

```bash
# 1️⃣ 重啟 cloudflared 服務 (重新獲取隧道 URL)
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c \
  --command "sudo systemctl restart cloudflared.service"

# 2️⃣ 等待 30 秒隧道完全建立
# sleep 30

# 3️⃣ 查詢新 URL
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c \
  --command "sudo journalctl -u cloudflared.service -n 20 | grep -E 'Registered|tunnel' | tail -1"

# 4️⃣ 手動更新 config.json (見方案 C)
```

## 📋 已提供的工具

### 1. **fix_webhook_emergency.py** (本機工具)
   ```bash
   # 用法
   python3 fix_webhook_emergency.py "https://example.trycloudflare.com"
   ```
   - 自動更新 config.json
   - 備份舊配置到 config.json.backup
   - 提供後續步驟指導

### 2. **改進的 auto_update_webhook.py** (VM 工具)
   - ✅ 已使用 shell=True 改進 (更好的兼容性)
   - ✅ 添加備用方法 (嘗試從配置文件讀取)
   - ✅ 增加超時容限到 15 秒

## 🎯 優先級行動清單

### 立即 (下 5 分鐘)
1. ⏸️ **嘗試方案 A**: 直接 SSH 而非 IAP
2. 📝 記錄命令結果

### 如果方案 A 成功
3. 提取新隧道 URL
4. 執行 `fix_webhook_emergency.py`
5. Git commit & push
6. 驗證部署

### 如果方案 A 失敗
7. ⏸️ 嘗試方案 B: GCP 控制台或 serial port output
8. 📝 記錄新隧道 URL

### 最後手段
9. 方案 D: 完整重啟

## 💡 預期結果

一旦隧道 URL 更新到 config.json，系統應該:
- ✅ GitHub webhook 能再次連接
- ✅ 下一次 git push 會自動觸發部署
- ✅ Bot 服務會自動重啟
- ✅ Discord 頻道會收到部署通知
- ✅ 用戶命令和功能恢復正常

## ⏱️ 預計時間

- 方案 A: **2-3 分鐘**
- 方案 B: **5-10 分鐘**
- 方案 D: **5-10 分鐘**

## 🆘 如果都不行

可能是更嚴重的基礎設施問題:
- GCP IAP 連接池故障
- Cloudflared 進程卡住
- VM 網絡連接問題

此時應該:
1. 檢查 GCP Console 中的 VM 警告
2. 查看 Activity Log
3. 考慮重啟 VM (`gcloud compute instances reset ...`)

---

**文件位置**: `/memories/session/emergency-recovery-plan.md`
**建立時間**: 2026-05-03 09:30 UTC
**優先級**: 🔴 CRITICAL
