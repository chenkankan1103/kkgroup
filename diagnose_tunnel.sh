#!/bin/bash
# 診斷隧道配置

echo "=== 1. 隧道進程狀態 ==="
sudo systemctl status cloudflared --no-pager | head -20

echo ""
echo "=== 2. cloudflared 配置文件內容 ==="
if [ -f /root/.cloudflared/*.json ]; then
    cat /root/.cloudflared/*.json 2>/dev/null | head -20
else
    echo "(未找到配置文件)"
fi

echo ""
echo "=== 3. 隧道聆聽地址 ==="
sudo netstat -tlnp 2>/dev/null | grep cloudflare || echo "(netstat 無法取得)"

echo ""
echo "=== 4. cloudflared 啟動命令 ==="
sudo systemctl cat cloudflared 2>/dev/null | grep "ExecStart"

echo ""
echo "=== 5. 最新隧道日誌 (最後 10 行) ==="
sudo journalctl -u cloudflared -n 10 --no-pager

echo ""
echo "✅ 診斷完成"
