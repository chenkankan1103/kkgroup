#!/bin/bash
# Git 遠端維護工具 - GCP 部署腳本

set -e  # 任何錯誤就終止

echo "════════════════════════════════════════════════════════"
echo "🚀 Git 遠端維護工具 - GCP 部署程序"
echo "════════════════════════════════════════════════════════"

WORK_DIR="/home/e193752468/kkgroup"

# 第一步：更新代碼
echo ""
echo "1️⃣ 從 GitHub 拉取最新代碼..."
cd "$WORK_DIR"
git pull origin main
echo "✅ 代碼已更新"

# 第二步：驗證新工具
echo ""
echo "2️⃣ 驗證新工具是否正確註冊..."
python3 check_registry.py 2>&1 | tail -10
echo "✅ 工具驗證完成"

# 第三步：檢查語法
echo ""
echo "3️⃣ 檢查 agent_tools.py 的語法..."
python3 -m py_compile agent_tools.py
echo "✅ 語法檢查通過"

# 第四步：重啟 BOT
echo ""
echo "4️⃣ 重啟 BOT 服務..."
sudo systemctl restart bot.service
sleep 3
echo "✅ BOT 已重啟"

# 第五步：驗證 BOT 狀態
echo ""
echo "5️⃣ 檢查 BOT 運行狀態..."
sudo systemctl status bot.service --no-pager | head -10
echo "✅ BOT 運行檢查完成"

# 第六步：檢查近期日誌
echo ""
echo "6️⃣ BOT 近 20 行日誌..."
sudo journalctl -u bot.service -n 20 --no-pager | tail -10
echo "✅ 日誌檢查完成"

echo ""
echo "════════════════════════════════════════════════════════"
echo "✅ 部署完成！新工具已上線"
echo "════════════════════════════════════════════════════════"
echo ""
echo "🧪 接下來可以進行 Discord 測試："
echo "  @KK園區中控室 查詢一下目前的 Git 狀態"
echo "  @KK園區中控室 讀取 bot.py 的內容"
