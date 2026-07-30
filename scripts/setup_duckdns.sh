#!/bin/bash
# ============================================================
# DuckDNS + Let's Encrypt SSL 免費永久網址自動設定腳本
# Domain: kkgroup2026.duckdns.org
# ============================================================
set -e

DOMAIN="kkgroup2026.duckdns.org"
TOKEN="b612fd07-d0c8-4d04-a8f5-c94928f0ac4a"
EMAIL="chenkankan1103@gmail.com"
ROOT="/home/e193752468/kkgroup"

echo "============================================================"
echo "🚀 DuckDNS + Let's Encrypt SSL 設定"
echo "   Domain: ${DOMAIN}"
echo "============================================================"

# ============================================================
# Step 1: DuckDNS IP 更新
# ============================================================
echo ""
echo "=== Step 1: DuckDNS IP 更新 ==="

mkdir -p /opt/duckdns
cat > /opt/duckdns/update.sh << DUCKDNS_EOF
#!/bin/bash
echo url="http://www.duckdns.org/update?domains=kkgroup2026&token=${TOKEN}&ip=" | curl -k -s -K -
DUCKDNS_EOF
chmod +x /opt/duckdns/update.sh

# 立即更新一次 IP
/opt/duckdns/update.sh
echo "OK"

# 每 5 分鐘自動更新
cat > /etc/cron.d/duckdns << CRON_EOF
*/5 * * * * root /opt/duckdns/update.sh > /dev/null 2>&1
CRON_EOF

echo "✅ DuckDNS 更新腳本已設定（每 5 分鐘）"

# ============================================================
# Step 2: Let's Encrypt SSL 憑證
# ============================================================
echo ""
echo "=== Step 2: 取得 Let's Encrypt SSL 憑證 ==="

sudo systemctl stop nginx 2>/dev/null || true

sudo certbot certonly --standalone \
    -d "${DOMAIN}" \
    --agree-tos \
    --email "${EMAIL}" \
    --non-interactive \
    --preferred-challenges http 2>&1 || {
    echo "⚠️ certbot 失敗，檢查是否已有憑證..."
    sudo ls /etc/letsencrypt/live/ 2>/dev/null
}

sudo systemctl start nginx
echo "✅ SSL 憑證處理完成"

# ============================================================
# Step 3: Nginx HTTPS 設定
# ============================================================
echo ""
echo "=== Step 3: 設定 Nginx HTTPS ==="

sudo tee /etc/nginx/sites-enabled/default > /dev/null << NGINX_EOF
# HTTP → HTTPS 自動轉向
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name kkgroup2026.duckdns.org _;

    # Let's Encrypt 驗證
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # 其他請求轉 HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name kkgroup2026.duckdns.org _;

    ssl_certificate /etc/letsencrypt/live/kkgroup2026.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kkgroup2026.duckdns.org/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    root /var/www/html;
    index index.html;

    # API 代理到 Flask
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /webhook/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /admin {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /rpg-game {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /game {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /assets/ {
        alias /var/www/html/assets/;
    }
}
NGINX_EOF

sudo nginx -t && sudo systemctl reload nginx
echo "✅ Nginx HTTPS 設定完成"

# ============================================================
# Step 4: 更新 config.json
# ============================================================
echo ""
echo "=== Step 4: 更新 config.json ==="

NEW_URL="https://${DOMAIN}"

cd "${ROOT}"
python3 << PYCONFIG
import json

# 更新主 config
with open('config/config.json', 'r') as f:
    config = json.load(f)

config['url'] = "${NEW_URL}"
config['API_BASE'] = "${NEW_URL}"

with open('config/config.json', 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("✅ config/config.json → ${NEW_URL}")

# 更新 portal config
with open('web/portal/config.json', 'w') as f:
    json.dump({"url": "${NEW_URL}", "API_BASE": "${NEW_URL}"}, f, ensure_ascii=False, indent=2)

print("✅ web/portal/config.json → ${NEW_URL}")
PYCONFIG

# ============================================================
# Step 5: 更新 GitHub Webhook URL
# ============================================================
echo ""
echo "=== Step 5: 更新 GitHub Webhook ==="

WEBHOOK_URL="${NEW_URL}/webhook/github"

# 嘗試用 gh CLI 更新 webhook
if which gh > /dev/null 2>&1; then
    WEBHOOK_ID=$(gh api repos/chenkankan1103/kkgroup/hooks --jq '.[0].id' 2>/dev/null || echo "")
    if [ -n "${WEBHOOK_ID}" ]; then
        gh api "repos/chenkankan1103/kkgroup/hooks/${WEBHOOK_ID}" \
            -X PATCH \
            -f config[url]="${WEBHOOK_URL}" \
            -f config[content_type]="json" \
            -f active=true 2>/dev/null && echo "✅ GitHub Webhook 已更新" || echo "⚠️ Webhook 更新需要 GitHub token"
    else
        echo "⚠️ 無法取得 webhook ID (需要 gh auth login)"
    fi
else
    echo "⚠️ gh CLI 未安裝，請手動更新 webhook URL:"
fi
echo "   Webhook URL: ${WEBHOOK_URL}"

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================================"
echo "✅ 全部設定完成！"
echo "============================================================"
echo ""
echo "   🌐 永久網址: ${NEW_URL}"
echo "   🔐 HTTPS:    Let's Encrypt 自動更新"
echo "   📝 管理後台: ${NEW_URL}/admin"
echo "   🎮 RPG遊戲:  ${NEW_URL}/rpg-game"
echo ""
echo "   ⚠️ 請手動更新 Discord Developer Portal:"
echo "      ${NEW_URL}/api/auth/callback"
echo "      https://discord.com/developers/applications/1483817997058707587/oauth2"
echo ""
echo "   📋 DuckDNS 每 5 分鐘自動更新 IP（cron）"
echo "   📋 SSL 憑證自動續期（certbot.timer）"
echo "============================================================"