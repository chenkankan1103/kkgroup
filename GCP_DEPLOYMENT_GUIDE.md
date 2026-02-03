# 🚀 GCP 機器人部署檢查指南

## 📍 GCP 伺服器信息

- **項目目錄**: `/home/e193752468/kkgroup`
- **用戶名**: `e193752468`
- **系統管理**: `systemd` (三個服務)
- **Bot Token 通道**: Discord ID `1275688788806467635`

---

## 🔍 快速檢查方式

### 方式 1: SSH 連接到 GCP 並檢查

```bash
# 1. 連接到 GCP 實例（假設已配置 SSH）
ssh e193752468@<GCP_IP>

# 2. 進入項目目錄
cd /home/e193752468/kkgroup

# 3. 查看當前部署版本
git log --oneline -5

# 4. 查看是否有未應用的更新
git status

# 5. 檢查機器人進程狀態
sudo systemctl status bot.service shopbot.service uibot.service

# 6. 查看最近的日誌
sudo journalctl -u bot.service -n 50 --no-pager
sudo journalctl -u shopbot.service -n 50 --no-pager
sudo journalctl -u uibot.service -n 50 --no-pager
```

---

## 📋 完整檢查清單

### 1️⃣ 代碼版本檢查

```bash
cd /home/e193752468/kkgroup

# 查看當前 HEAD
git log --oneline -1

# 查看遠端版本
git fetch origin
git log --oneline -1 origin/main

# 比較本地和遠端
git diff --stat HEAD origin/main
```

**預期結果**：
- 本地版本應為 `612f077` (最新的購買流程改進)
- 如果有新提交，說明需要 `git pull`

---

### 2️⃣ 機器人進程檢查

```bash
# 查看三個服務的狀態
sudo systemctl status bot.service
sudo systemctl status shopbot.service
sudo systemctl status uibot.service

# 或者一行查看
sudo systemctl status bot.service shopbot.service uibot.service
```

**預期結果**：
```
● bot.service - Discord Bot
   Loaded: loaded (/etc/systemd/system/bot.service; enabled; vendor preset: enabled)
   Active: active (running) since ...
```

---

### 3️⃣ 進程運行檢查

```bash
# 查看 Python 進程
ps aux | grep python

# 查看特定的 bot 進程
pgrep -f "python.*bot.py"
pgrep -f "python.*shopbot.py"
pgrep -f "python.*uibot.py"
```

---

### 4️⃣ 日誌檢查

```bash
# 查看 bot.service 最後 100 行日誌
sudo journalctl -u bot.service -n 100 --no-pager

# 查看實時日誌（類似 tail -f）
sudo journalctl -u bot.service -f

# 按時間過濾（最後 1 小時）
sudo journalctl -u bot.service --since "1 hour ago"

# 查看錯誤
sudo journalctl -u bot.service -p err
```

---

### 5️⃣ 資源使用情況

```bash
# 查看 Bot 進程的 CPU 和內存使用
ps aux | grep python

# 查看磁盤使用
du -sh /home/e193752468/kkgroup

# 查看數據庫文件大小
ls -lh /home/e193752468/kkgroup/*.db

# 查看系統資源
free -h        # 內存
df -h          # 磁盤
```

---

### 6️⃣ 網絡連接檢查

```bash
# 檢查 Bot 是否連接到 Discord（查看埠連接）
netstat -tuln | grep -i listen

# 檢查 Discord API 連接
curl -I https://discord.com/api/v10/

# 查看 Python 進程的網絡連接
lsof -i -P -n | grep python
```

---

### 7️⃣ 環境變數檢查

```bash
# 查看環境變數是否正確加載
cat /home/e193752468/kkgroup/.env

# 驗證關鍵變數
grep "GUILD_ID\|DISCORD_BOT_TOKEN\|DISCORD_SYS_CHANNEL_ID" .env
```

---

## 🔄 更新部署流程

### 方式 A: 使用 update_restart.py（推薦）

```bash
cd /home/e193752468/kkgroup

# 直接運行更新腳本
python3 update_restart.py

# 如果失敗，查看詳細輸出
python3 update_restart.py 2>&1 | tee update.log
```

### 方式 B: 手動更新

```bash
cd /home/e193752468/kkgroup

# 1. 檢查更新
git fetch origin
git log --oneline -1 HEAD
git log --oneline -1 origin/main

# 2. 拉取最新代碼
git pull origin main

# 3. 重啟所有服務
sudo systemctl restart bot.service shopbot.service uibot.service

# 4. 驗證服務狀態
sudo systemctl status bot.service shopbot.service uibot.service
```

### 方式 C: 使用 screen（如果用 screen 管理）

```bash
# 列出所有 screen 會話
screen -ls

# 進入 bot screen
screen -r bot

# 查看運行中的進程
# 按 Ctrl-A 然後 Shift-P 查看進程

# 退出 screen（不退出進程）
# 按 Ctrl-A 然後 D

# 停止 screen 中的進程
# 按 Ctrl-C
```

---

## 🧪 驗證最新功能（購買流程改進）

部署後，測試新功能是否正常：

```bash
# 1. 確認代碼版本
cd /home/e193752468/kkgroup
git log --oneline -1  # 應該是 612f077 或更新

# 2. 檢查 cannabis_merchant_view_v2.py 是否已更新
grep -n "edit_message" shop_commands/merchant/cannabis_merchant_view_v2.py

# 應該有多個 edit_message 調用，例如：
# - seed_selected() 中的 edit_message
# - fertilizer_selected() 中的 edit_message
# - sell_selected() 中的 edit_message

# 3. 檢查是否有 Modal 類（應該沒有）
grep -n "class.*Modal" shop_commands/merchant/cannabis_merchant_view_v2.py
# 預期：無結果

# 4. 檢查是否排除了 cannabis_merchant_view_v2
grep "cannabis_merchant_view_v2" shop_commands/auto_reload.py
# 預期：應該在 excluded_modules 中
```

---

## 🐛 故障排查

### 問題 1: Bot 進程不運行

```bash
# 檢查 systemd 日誌
sudo journalctl -u bot.service -n 50

# 手動運行看是否有錯誤
cd /home/e193752468/kkgroup
source venv/bin/activate
python bot.py

# 檢查權限
ls -l /home/e193752468/kkgroup/bot.py
```

### 問題 2: 購買流程還是有 Modal 錯誤

```bash
# 確認代碼已更新
git status  # 應該是 clean

# 檢查 Python 緩存
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 重啟服務
sudo systemctl restart bot.service shopbot.service uibot.service
```

### 問題 3: 無法 git pull

```bash
# 檢查 git 狀態
git status

# 如果有衝突
git reset --hard HEAD
git pull origin main

# 檢查 git 配置
git config --list | grep -i user
git config --list | grep -i remote
```

---

## 📊 監控命令速查

```bash
# ⚡ 快速狀態檢查（複製整個命令）
sudo systemctl status bot.service shopbot.service uibot.service && \
echo "=== Git Version ===" && \
git log --oneline -1 && \
echo "=== Recent Errors ===" && \
sudo journalctl -u bot.service -p err --since "1 hour ago"

# 🔄 實時日誌監控
sudo journalctl -u bot.service -f

# 💾 數據庫檢查
ls -lh *.db 2>/dev/null || echo "No .db files found"

# 🐍 Python 進程監控
watch -n 1 'ps aux | grep "[p]ython"'
```

---

## 📝 常用 systemd 命令

```bash
# 啟動服務
sudo systemctl start bot.service

# 停止服務
sudo systemctl stop bot.service

# 重啟服務
sudo systemctl restart bot.service

# 重新加載配置（不需要重啟）
sudo systemctl reload bot.service

# 查看服務狀態
sudo systemctl status bot.service

# 查看是否開啟自動啟動
sudo systemctl is-enabled bot.service

# 啟用自動啟動
sudo systemctl enable bot.service

# 禁用自動啟動
sudo systemctl disable bot.service

# 查看所有失敗的服務
sudo systemctl list-units --failed

# 重載 systemd 配置
sudo systemctl daemon-reload
```

---

## 🎯 部署檢查步驟（快速版）

```bash
# 1. 連接到 GCP
ssh e193752468@<GCP_IP>

# 2. 快速檢查（複製以下命令）
cd /home/e193752468/kkgroup && \
echo "=== Code Version ===" && \
git log --oneline -1 && \
echo "" && \
echo "=== Service Status ===" && \
sudo systemctl status --no-pager bot.service shopbot.service uibot.service && \
echo "" && \
echo "=== Recent Logs ===" && \
sudo journalctl -u bot.service -n 20 --no-pager

# 3. 如果需要更新
python3 update_restart.py

# 4. 驗證更新
git log --oneline -1
sudo systemctl status bot.service
```

---

## 💡 提示

- GCP 上的 systemd 日誌存儲在 `journalctl` 中，不是文本文件
- 使用 `sudo` 查看日誌需要權限
- `git pull` 後 systemd 不會自動重啟服務，需要手動 `restart`
- `.db` 文件（SQLite 數據庫）由 `update_restart.py` 自動保護，不會被覆蓋
- 所有三個 Bot（bot, shopbot, uibot）必須運行才能完整工作

