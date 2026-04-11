# GCP VM .env 同步指南

## 📋 背景

地震監測功能已全部移除，`.env.example` 已更新並推送到 GitHub。此指南說明如何在 GCP VM 上同步更新。

## 🔄 同步步驟

### 步驟 1: 在 GCP VM 上拉取最新代碼

```bash
cd /home/e193752468/kkgroup
git pull origin main
```

此命令會更新以下文件：
- ✅ `.env.example` - 已移除 CWB_API_KEY
- ✅ `utils/earthquake.py` - 轉換為存根文件
- ✅ `.gitignore` - 添加 docs_and_tests/ 規則

### 步驟 2: 更新 GCP VM 的 .env（移除 CWB_API_KEY）

如果 GCP VM 的 `.env` 中有 CWB_API_KEY，請執行：

```bash
# 檢查是否有 CWB_API_KEY
grep CWB /home/e193752468/kkgroup/.env

# 如果有，使用 sed 移除該行
sed -i '/^CWB_API_KEY=/d' /home/e193752468/kkgroup/.env

# 驗證已移除
grep CWB /home/e193752468/kkgroup/.env  # 應該無輸出
```

### 步驟 3: 驗證服務正常運行

```bash
# 檢查所有 bot 服務
sudo systemctl status bot.service shopbot.service uibot.service

# 檢查日誌（確保沒有地震相關錯誤）
sudo journalctl -u bot.service -n 50 | grep -i "earthquake\|CWB\|error"
```

預期結果：無 CWB 或地震相關的輸出

### 步驟 4: 同步本地 .env（可選）

如果需要從 GCP VM 複製 `.env` 回本地：

```bash
# 從本地執行（Windows PowerShell）
gcloud compute scp e193752468@instance-20250501-142333:/home/e193752468/kkgroup/.env .env.gcp --zone=us-central1-c --tunnel-through-iap

# 檢查並合併更改
diff .env .env.gcp
```

## ✅ 已完成的更改

| 項目 | 狀態 | 備註 |
|------|------|------|
| `.env.example` Git 更新 | ✅ 完成 | 已推送 commit dfe1be80 |
| `utils/earthquake.py` | ✅ 完成 | 已轉換為存根文件 |
| `.gitignore` 更新 | ✅ 完成 | 已添加 docs_and_tests/ |
| 本地 .env 檢查 | ✅ 完成 | 本地無 CWB_API_KEY |
| GCP VM .env 更新 | ⏳ 待執行 | 需 SSH 連接 |

## 🚨 常見問題

### Q: SSH 連接超時怎麼辦？

A: 使用以下命令進行故障排查：

```bash
# 檢查 IAP 隧道
gcloud compute ssh instance-20250501-142333 --project=kkgroup --zone=us-central1-c --troubleshoot --tunnel-through-iap

# 或使用本地 gcloud 配置
gcloud config list
```

### Q: 如何確認地震 API 已完全禁用？

A: 地震監測功能已從以下位置完全移除：

- ❌ `utils/earthquake.py` - 原 66 行代碼已刪除
- ❌ 所有 bot 文件導入 - 沒有調用代碼
- ❌ `.env` - 無 CWB_API_KEY
- ❌ `network_traffic_monitor.py` - 無地震 API 檢查

## 📊 流量改進

移除地震監測後的月度流量估計：

```
清除前: 700-1100 MB/月 ($8.40-13.20)
清除後: 290-300 MB/月 ($3.48-3.6)
節省: 74% ✨
```

## 📝 相關提交

```
546a8d54 (HEAD -> main) remove: delete old locker_analysis_report.txt
5c973bac refactor: organize traffic analysis tools and tests into docs_and_tests folder
dfe1be80 refactor: remove earthquake monitoring system code - disable unused CWB API integration
```

檢查更改：
```bash
git log --oneline -n 10
git show dfe1be80  # 查看地震代碼移除細節
```

## 🔍 後續監控

### 執行完整流量檢查

```bash
cd /home/e193752468/kkgroup
python3 network_traffic_monitor.py --check-all 2>&1 | tee flow_check.log
```

### 監控日誌

```bash
# 監控主 Bot 日誌（確認無 CWB 相關錯誤）
sudo journalctl -u bot.service -f | grep -iE "error|exception|CWB"

# 檢查服務狀態
sudo systemctl status bot.service -l
```

---

**最後更新**: 2026-04-11  
**更新者**: Copilot 自動化  
**狀態**: 本地完成 ✅ | GCP 待執行 ⏳
