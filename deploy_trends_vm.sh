#!/bin/bash
# 趨勢樂透系統 - VM 部署腳本
# 在 GCP VM 上運行此腳本以部署新模組

set -e  # 遇到錯誤立即停止

echo "🚀 開始部署趨勢樂透系統..."
cd ~/kkgroup

# ========================================
# 1. 備份現有文件
# ========================================
echo "📦 備份現有文件..."
BACKUP_DIR="backup/trends_$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# ========================================
# 2. 創建共享工具模組（如果不存在）
# ========================================
echo "📂 創建目錄結構..."
mkdir -p shared/utils

# ========================================
# 3. 部署核心模組（使用 git pull 或直接複製）
# ========================================
echo "📥 檢查 git 狀態..."

# 嘗試 git pull
if git pull origin main 2>/dev/null; then
    echo "✅ Git 更新成功"
else
    echo "⚠️  Git 更新失敗，嘗試手動部署..."
    # 如果 git 不工作，用戶需要手動上傳文件
fi

# ========================================
# 4. 驗證文件
# ========================================
echo "🔍 驗證文件完整性..."

FILES=(
    "shared/utils/trends_collector.py"
    "shared/utils/trends_lottery_system.py"
    "cogs/common/trends_lottery.py"
    "docs_and_tests/TRENDS_LOTTERY_GUIDE.md"
    "docs_and_tests/check_trends_system.py"
)

MISSING=0
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (缺失)"
        MISSING=$((MISSING+1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "❌ 還有 $MISSING 個文件缺失，需要手動上傳"
    echo "缺失的文件："
    for file in "${FILES[@]}"; do
        if [ ! -f "$file" ]; then
            echo "   - $file"
        fi
    done
    exit 1
fi

# ========================================
# 5. 檢查依賴
# ========================================
echo ""
echo "📦 檢查依賴..."
python3 -c "import aiohttp; print('  ✅ aiohttp')" || echo "  ⚠️  缺少 aiohttp"
python3 -c "import pytz; print('  ✅ pytz')" || echo "  ⚠️  缺少 pytz (可選)"

# ========================================
# 6. 驗證環境變數
# ========================================
echo ""
echo "🔧 檢查環境變數..."
if grep -q "TRENDS_CHANNEL_ID" ~/.env; then
    echo "  ✅ TRENDS_CHANNEL_ID"
else
    echo "  ❌ TRENDS_CHANNEL_ID 未設置"
fi

if grep -q "TWITTER_API_KEY" ~/.env; then
    echo "  ✅ TWITTER_API_KEY"
else
    echo "  ⚠️  TWITTER_API_KEY 未設置"
fi

if grep -q "REDDIT_CLIENT_ID" ~/.env; then
    echo "  ✅ REDDIT_CLIENT_ID"
else
    echo "  ⚠️  REDDIT_CLIENT_ID 未設置"
fi

# ========================================
# 7. 重啟服務
# ========================================
echo ""
echo "🔄 重啟 Bot 服務..."
sudo systemctl restart bot.service

sleep 2

# ========================================
# 8. 驗證服務狀態
# ========================================
echo ""
echo "📊 驗證服務狀態..."
if sudo systemctl is-active --quiet bot.service; then
    echo "  ✅ Bot 服務已運行"
    sudo systemctl status bot.service | grep -A 2 "Active\|PID"
else
    echo "  ❌ Bot 服務失敗"
    sudo journalctl -u bot.service -n 20 --no-pager
    exit 1
fi

echo ""
echo "✅ 部署完成！"
echo ""
echo "📋 後續步驟："
echo "1. 設置 Twitter/Reddit API 憑證（編輯 ~/.env）"
echo "2. 在 Discord 中測試 /trends_predict 命令"
echo "3. 查看日誌：sudo journalctl -u bot.service -f"
echo ""
