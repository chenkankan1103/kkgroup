#!/usr/bin/env python3
"""快速診斷隧道 404 問題"""
import subprocess
import json
import re

def run_gcloud_cmd(cmd_str):
    """執行 gcloud 命令"""
    cmd = [
        'gcloud', 'compute', 'ssh', 'e193752468@instance-20250501-142333',
        '--zone', 'us-central1-c', '--tunnel-through-iap',
        '--command', cmd_str
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return f"錯誤: {e}", 1

print("\n" + "="*50)
print("🔍 隧道 404 問題診斷")
print("="*50 + "\n")

# 1. 檢查 Nginx 監聽
print("1️⃣  Nginx 監聽狀態:")
stdout, code = run_gcloud_cmd("sudo ss -tlnp | grep 80")
print(stdout)

# 2. 檢查 Nginx 配置
print("\n2️⃣  Nginx 位置配置:")
stdout, code = run_gcloud_cmd("sudo grep -A2 'location' /etc/nginx/sites-available/default")
print(stdout)

# 3. 最新日誌
print("\n3️⃣  最新 Nginx 訪問日誌 (過去 5 行):")
stdout, code = run_gcloud_cmd("sudo tail -5 /var/log/nginx/access.log")
for line in stdout.split('\n'):
    print(line)

# 4. 檢查文件
print("\n4️⃣  检查 leaderboard.png 文件:")
stdout, code = run_gcloud_cmd("ls -lh /var/www/html/assets/leaderboard.png")
print(stdout)

print("\n" + "="*50 + "\n")
