#!/bin/bash
# GCP VM 部署腳本
# 在 GCP VM 上執行以完成重組部署

set -e  # 任何錯誤就終止

echo "========== GCP VM 重組部署 =========="
echo ""

# Step 1: 進入專案目錄
echo "Step 1: 進入專案目錄..."
cd /home/e193752468/kkgroup
echo "✅ 位置: $(pwd)"
echo ""

# Step 2: 拉取最新代碼
echo "Step 2: 拉取最新代碼..."
git fetch origin
echo "✅ 已從遠端拉取"
echo ""

# Step 3: 檢出重組分支
echo "Step 3: 檢出分支 main..."
git checkout main
echo "✅ 已切換到重組分支"
echo ""

# Step 4: 驗證目錄結構
echo "Step 4: 驗證新目錄結構..."
echo "檢查關鍵目錄："
for dir in bots shared/db shared/utils web/api cogs/common cogs/shop cogs/ui config/services; do
    if [ -d "$dir" ]; then
        echo "  ✅ $dir"
    else
        echo "  ❌ $dir 未找到"
    fi
done
echo ""

# Step 5: 複製服務檔案
echo "Step 5: 複製 systemd 服務檔案..."
sudo cp config/services/bot.service /etc/systemd/system/bot.service
sudo cp config/services/shopbot.service /etc/systemd/system/shopbot.service
sudo cp config/services/uibot.service /etc/systemd/system/uibot.service
sudo cp config/services/kkgroup-api.service /etc/systemd/system/kkgroup-api.service
echo "✅ 已複製所有服務檔案"
echo ""

# Step 6: 重新載入 systemd
echo "Step 6: 重新載入 systemd 配置..."
sudo systemctl daemon-reload
echo "✅ systemd 已重新載入"
echo ""

# Step 7: 檢查服務檔案路徑
echo "Step 7: 驗證服務配置..."
echo "檢查 bot.service 的 ExecStart："
sudo grep "ExecStart" /etc/systemd/system/bot.service
echo ""

# Step 8: 重啟服務
echo "Step 8: 重啟 Bot 服務..."
echo "重啟 bot.service..."
sudo systemctl restart bot.service
sleep 2
echo "  狀態: $(sudo systemctl is-active bot.service)"
echo ""

echo "重啟 shopbot.service..."
sudo systemctl restart shopbot.service
sleep 2
echo "  狀態: $(sudo systemctl is-active shopbot.service)"
echo ""

echo "重啟 uibot.service..."
sudo systemctl restart uibot.service
sleep 2
echo "  狀態: $(sudo systemctl is-active uibot.service)"
echo ""

echo "重啟 kkgroup-api.service..."
sudo systemctl restart kkgroup-api.service
sleep 2
echo "  狀態: $(sudo systemctl is-active kkgroup-api.service)"
echo ""

# Step 9: 檢查日誌
echo "Step 9: 檢查最近的日誌..."
echo ""
echo "=== bot.service (最近 20 行) ==="
sudo journalctl -u bot.service -n 20 --no-pager | tail -20
echo ""

echo "=== shopbot.service (最近 20 行) ==="
sudo journalctl -u shopbot.service -n 20 --no-pager | tail -20
echo ""

echo "=== uibot.service (最近 20 行) ==="
sudo journalctl -u uibot.service -n 20 --no-pager | tail -20
echo ""

# 最終狀態
echo "========== 部署完成 =========="
echo ""
echo "所有服務狀態："
sudo systemctl status bot.service --no-pager | grep "Active:"
sudo systemctl status shopbot.service --no-pager | grep "Active:"
sudo systemctl status uibot.service --no-pager | grep "Active:"
echo ""
echo "✅ GCP VM 部署完成！"
