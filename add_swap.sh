#!/bin/bash
# 為 GCP 實例添加 Swap 空間

echo "=================================================="
echo "🔧 添加 Swap 空間"
echo "=================================================="
echo ""

# 1. 檢查是否已有 swap
echo "[1/4] 檢查現有 Swap..."
SWAP_SIZE=$(swapon -s | tail -1 | awk '{print $3}')
if [ -n "$SWAP_SIZE" ] && [ "$SWAP_SIZE" -gt 0 ]; then
    echo "✓ 已有 Swap: $SWAP_SIZE KB"
else
    echo "✓ 無現有 Swap，準備新增"
fi

echo ""
echo "[2/4] 創建 2GB Swap 文件..."
# 創建 2GB swap 文件
sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1G count=2

# 設置權限
sudo chmod 600 /swapfile
echo "✓ Swap 文件已創建"

echo ""
echo "[3/4] 格式化並啟用 Swap..."
# 格式化為 swap
sudo mkswap /swapfile

# 啟用 swap
sudo swapon /swapfile

# 使其持久化（開機後自動啟用）
if ! grep -q "/swapfile" /etc/fstab; then
    echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab > /dev/null
    echo "✓ 已添加到 /etc/fstab"
else
    echo "✓ 已存在於 /etc/fstab"
fi

echo ""
echo "[4/4] 優化 Swap 設定..."
# 優化 swap 使用（降低 swappiness，使系統優先使用物理記憶體）
echo "vm.swappiness = 20" | sudo tee -a /etc/sysctl.conf > /dev/null
sudo sysctl -p > /dev/null 2>&1

echo ""
echo "=================================================="
echo "✅ Swap 配置完成！"
echo "=================================================="
echo ""

echo "配置詳情："
swapon -s
echo ""
echo "系統記憶體狀態："
free -h
echo ""
echo "預期效果："
echo "- 記憶體容量：從 1GB 擴展至 ~3GB (1GB 實體 + 2GB Swap)"
echo "- SSH 連接不再導致 OOM"
echo "- BOT 穩定性大幅提升"
echo ""
