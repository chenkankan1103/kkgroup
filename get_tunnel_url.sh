#!/bin/bash
# 獲取當前的 Cloudflare Quick Tunnel URL

TUNNEL_ID=$(curl -s https://api.cloudflare.com/client/v4/accounts/$(curl -s https://www.cloudflare.com/api/v4/zones -H "Authorization: Bearer $CF_TOKEN" | jq -r '.result[0].account.id')/tunnels 2>/dev/null | jq -r '.result[0].id' 2>/dev/null || echo "")

if [ -z "$TUNNEL_ID" ]; then
    # 從日誌中查找隧道 URL
    echo "嘗試從日誌中查找隧道 URL..."
    TUNNEL_URL=$(sudo journalctl -u cloudflared.service -n 200 --no-pager 2>/dev/null | grep -oP '(?:https?://)?[a-z-]+\.trycloudflare\.com' | head -1)
    
    if [ ! -z "$TUNNEL_URL" ]; then
        echo "當前隧道 URL: $TUNNEL_URL"
    else
        echo "無法找到隧道 URL"
        echo "隧道狀態："
        sudo systemctl status cloudflared --no-pager 2>&1 | head -5
        echo ""
        echo "最近的日誌："
        sudo journalctl -u cloudflared.service -n 5 --no-pager 2>/dev/null | tail -5
    fi
else
    echo "隧道 ID: $TUNNEL_ID"
fi
