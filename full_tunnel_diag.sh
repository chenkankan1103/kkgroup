#!/bin/bash
# 完整的隧道和 Nginx 診斷腳本

echo "========================================"
echo "🔍 KKGroup 隧道診斷 - $(date)"
echo "========================================"

echo ""
echo "1️⃣ cloudflared 監聽的端口"
echo "==========================================="
sudo lsof -i -P -n 2>/dev/null | grep cloudflared || echo "(lsof 無法取得)"

echo ""
echo "2️⃣ cloudflared 進程詳細信息"
echo "==========================================="
ps aux | grep cloudflared | grep -v grep

echo ""
echo "3️⃣ systemd cloudflared 服務配置"
echo "==========================================="
sudo cat /etc/systemd/system/cloudflared.service 2>/dev/null | head -20

echo ""
echo "4️⃣ cloudflared 最新日誌 (包括錯誤)"
echo "==========================================="
sudo journalctl -u cloudflared -n 20 --no-pager 2>/dev/null | tail -15

echo ""
echo "5️⃣ Nginx 監聽狀態"
echo "==========================================="
sudo ss -tlnp | grep -E "nginx|:80" || echo "(無法取得)"

echo ""
echo "6️⃣ Nginx 最新訪問日誌 (最後 20 行)"
echo "==========================================="
sudo tail -20 /var/log/nginx/access.log 2>/dev/null || echo "(無法讀取)"

echo ""
echo "7️⃣ Nginx 錯誤日誌"
echo "==========================================="
sudo tail -10 /var/log/nginx/error.log 2>/dev/null || echo "(無法讀取)"

echo ""
echo "8️⃣ 隧道 URL"
echo "==========================================="
sudo journalctl -u cloudflared -n 50 --no-pager 2>/dev/null | grep "https://" | tail -1

echo ""
echo "✅ 診斷完成"
