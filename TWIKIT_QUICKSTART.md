# 🐦 Twikit 快速配置

## 第一步：添加 Twitter 帳號到 .env

```bash
# 編輯 .env
nano .env

# 添加以下行：
TWITTER_USERNAME=your_username
TWITTER_EMAIL=your_email@example.com
TWITTER_PASSWORD=your_password
```

## 第二步：部署到 VM

```bash
git push origin main
```

然後 SSH 到 VM：
```bash
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap
cd /home/e193752468/kkgroup
git pull origin main
source venv/bin/activate
pip install -q twikit beautifulsoup4
nano .env  # 添加 Twitter 認證信息
sudo systemctl restart bot.service
```

## 第三步：驗證

```bash
# 檢查日誌
sudo journalctl -u bot.service -n 30 --no-pager | grep -i twikit
```

✅ 應該看到：`✅ [Twikit 成功] 獲取 25 項 Twitter 趨勢`

---

📖 **詳細說明** → [TWIKIT_SETUP_GUIDE.md](docs_and_tests/TWIKIT_SETUP_GUIDE.md)
