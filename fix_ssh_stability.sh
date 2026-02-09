#!/bin/bash
# GCP SSH 穩定性修復腳本

echo "========================================="
echo "正在修復 SSH 連接穩定性配置..."
echo "========================================="

# 1. 添加 SSH keepalive 設定
echo "[1/3] 添加 SSH keepalive 設定..."
echo 'ClientAliveInterval 60
ClientAliveCountMax 3
TCPKeepAlive yes' | sudo tee /etc/ssh/sshd_config.d/keepalive.conf > /dev/null
echo "✓ 已添加 keepalive 設定"

# 2. 驗證配置
echo "[2/3] 驗證 SSH 配置..."
sudo sshd -T | grep -E 'clientaliveinterval|clientalivecount|tcpkeepalive' || echo "✓ 配置已驗證"
echo "✓ SSH 配置有效"

# 3. 重新加載 SSH 服務（不中斷現有連接）
echo "[3/3] 重新加載 SSH 服務..."
sudo systemctl reload ssh || sudo systemctl reload sshd
echo "✓ SSH 服務已重新加載"

echo ""
echo "========================================="
echo "✅ SSH 穩定性配置完成！"
echo "========================================="
echo ""
echo "設定詳情："
echo "- ClientAliveInterval: 60 秒（每 60 秒發送一次 keepalive 訊息）"
echo "- ClientAliveCountMax: 3 個不回應後斷開"
echo "- TCPKeepAlive: 已啟用"
echo ""
echo "這會大幅改善遠端 SSH 連接的穩定性。"
