#!/usr/bin/env python3
import subprocess
import sys

# 修正的 Nginx 配置
nginx_config = """server {
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
"""

# 通過 gcloud 上傳配置
cmd = [
    'gcloud', 'compute', 'ssh', 'e193752468@instance-20250501-142333',
    '--zone', 'us-central1-c',
    '--tunnel-through-iap',
    '--command', f'echo {repr(nginx_config)} | sudo tee /etc/nginx/sites-available/default > /dev/null && sudo nginx -t && sudo systemctl reload nginx && echo "✅ Nginx 已修正並重新載入"'
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    print(result.stdout)
    if result.returncode != 0:
        print("❌ 錯誤:", result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
except Exception as e:
    print(f"❌ 執行失敗: {e}", file=sys.stderr)
    sys.exit(1)
