# ============================================================
# GCP VM 部署命令 - 複製並在 GCP VM 上逐個執行
# ============================================================

# 1️⃣ 進入專案目錄
cd /home/e193752468/kkgroup

# 2️⃣ 拉取最新代碼
git fetch origin

# 3️⃣ 檢出重組分支
git checkout restructure-project-20260414

# 4️⃣ 驗證目錄結構
echo "=== 驗證新目錄結構 ==="
ls -la bots/ | head -5
ls -la shared/db/ | head -5
ls -la web/api/ | head -5
ls -la cogs/ | head -5
ls -la config/services/ | head -5

# 5️⃣ 複製服務檔案到 systemd
sudo cp config/services/bot.service /etc/systemd/system/bot.service
sudo cp config/services/shopbot.service /etc/systemd/system/shopbot.service
sudo cp config/services/uibot.service /etc/systemd/system/uibot.service
sudo cp config/services/kkgroup-api.service /etc/systemd/system/kkgroup-api.service

# 6️⃣ 重新載入 systemd
sudo systemctl daemon-reload

# 7️⃣ 驗證服務配置
echo "=== 驗證 bot.service 的 ExecStart ==="
sudo grep ExecStart /etc/systemd/system/bot.service

# 8️⃣ 重啟 bot 服務
echo "=== 重啟 bot.service ==="
sudo systemctl restart bot.service
sleep 3
sudo systemctl status bot.service --no-pager | grep -E "Active|Running"

# 9️⃣ 重啟 shopbot 服務
echo "=== 重啟 shopbot.service ==="
sudo systemctl restart shopbot.service
sleep 3
sudo systemctl status shopbot.service --no-pager | grep -E "Active|Running"

# 🔟 重啟 uibot 服務
echo "=== 重啟 uibot.service ==="
sudo systemctl restart uibot.service
sleep 3
sudo systemctl status uibot.service --no-pager | grep -E "Active|Running"

# 1️⃣1️⃣ 重啟 API 服務
echo "=== 重啟 kkgroup-api.service ==="
sudo systemctl restart kkgroup-api.service
sleep 3
sudo systemctl status kkgroup-api.service --no-pager | grep -E "Active|Running"

# 1️⃣2️⃣ 檢查最新日誌
echo ""
echo "=== bot.service 日誌 (最近 30 行) ==="
sudo journalctl -u bot.service -n 30 --no-pager

echo ""
echo "=== shopbot.service 日誌 (最近 30 行) ==="
sudo journalctl -u shopbot.service -n 30 --no-pager

echo ""
echo "=== uibot.service 日誌 (最近 30 行) ==="
sudo journalctl -u uibot.service -n 30 --no-pager

# 1️⃣3️⃣ 最終狀態檢查
echo ""
echo "========== 最終狀態 =========="
sudo systemctl status bot.service shopbot.service uibot.service --no-pager | grep Active
