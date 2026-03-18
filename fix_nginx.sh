#!/bin/bash
set -e

# GCP VM 詳細資訊
VM_NAME="instance-20250501-142333"
VM_USER="e193752468"
VM_ZONE="us-central1-c"

echo "🔧 開始修正 Nginx 配置..."

# 通過 gcloud IAP SSH 隧道執行修復
gcloud compute ssh "${VM_USER}@${VM_NAME}" \
    --zone="${VM_ZONE}" \
    --tunnel-through-iap \
    --command='
cat | sudo tee /etc/nginx/sites-available/default > /dev/null

' << 'NGINX_CONFIG'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root /var/www/html;
    index index.html;

    location /assets/ {
        alias /var/www/html/assets/;
        autoindex on;
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
NGINX_CONFIG

echo "✅ 配置已上傳"

# 驗證和重新載入
gcloud compute ssh "${VM_USER}@${VM_NAME}" \
    --zone="${VM_ZONE}" \
    --tunnel-through-iap \
    --command='
sudo nginx -t && echo "✅ Nginx 配置有效"
sudo systemctl reload nginx && echo "✅ Nginx 已重新載入"
echo "🧪 快速測試..."
curl -s http://127.0.0.1/assets/leaderboard.png | wc -c
'

echo ""
echo "✨ 完成！現在測試隧道連接..."
