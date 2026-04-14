#!/usr/bin/env python3
"""修正 Nginx 配置的 404 問題"""
import subprocess
import base64
import sys

# 正確的 Nginx 配置
nginx_config = b"""server {
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

# Base64 編碼內容
config_b64 = base64.b64encode(nginx_config).decode('ascii')

# 執行命令
cmd = f'''
echo {config_b64} | base64 -d | sudo tee /etc/nginx/sites-available/default > /dev/null && \\
echo "✅ 配置已更新" && \\
sudo nginx -t && echo "✅ Nginx 配置有效" || (echo "❌ Nginx 配置有舛誤"; exit 1) && \\
sudo systemctl reload nginx && echo "✅ Nginx 已重新載入" || (echo "❌ Nginx 重新載入失敗"; exit 1)
'''

# 通過 gcloud IAP-SSH 執行
gcloud_cmd = [
    'gcloud', 'compute', 'ssh', 'e193752468@instance-20250501-142333',
    '--zone', 'us-central1-c',
    '--tunnel-through-iap',
    '--command', cmd
]

print("🔧 正在修正 Nginx 配置...")
try:
    result = subprocess.run(gcloud_cmd, capture_output=True, text=True, timeout=30)
    print(result.stdout)
    if result.returncode != 0:
        print("❌ 錯誤:", result.stderr, file=sys.stderr)
        sys.exit(1)
    
    # 測試
    print("\n🧪 測試隧道連接...")
    test_cmd = [
        'powershell', '-Command',
        '$URL = "https://beach-because-dating-shelter.trycloudflare.com/assets/leaderboard.png"; ' +
        'try { $r = Invoke-WebRequest -Uri $URL -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop; ' +
        'Write-Host "✅ HTTP $($r.StatusCode)" } ' +
        'catch { Write-Host "❌ $($_.Exception.Response.StatusCode)" }'
    ]
    result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=15)
    print(result.stdout)
    
    print("\n✨ 完成！")
except Exception as e:
    print(f"❌ 失敗: {e}", file=sys.stderr)
    sys.exit(1)
