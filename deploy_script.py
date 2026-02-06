#!/usr/bin/env python3
"""部署更新的啟動腳本到 GCP"""
import subprocess
import base64
import sys

# 讀取本地腳本
with open('start_bot_and_api.sh', 'rb') as f:
    script_content = f.read()

# Base64 編碼
encoded = base64.b64encode(script_content).decode()

# 準備 SSH 命令
ssh_cmd = [
    'ssh',
    '-i',
    f'{sys.path[0]}/../../../.ssh/id_rsa_gcp' if sys.platform == 'win32' else '/root/.ssh/id_rsa_gcp',
    'kankan@35.206.126.157',
    f'echo "{encoded}" | base64 -d | sudo tee /home/e193752468/kkgroup/start_bot_and_api.sh > /dev/null && sudo chmod +x /home/e193752468/kkgroup/start_bot_and_api.sh && echo "✅ 新啟動腳本已部署"'
]

# 執行
print("部署中...")
try:
    # 使用 echo 和管道的方式，避免引號問題
    full_cmd = f'echo "{encoded}" | ssh -i "$env:USERPROFILE\\.ssh\\id_rsa_gcp" kankan@35.206.126.157 "base64 -d | sudo tee /home/e193752468/kkgroup/start_bot_and_api.sh > /dev/null && sudo chmod +x /home/e193752468/kkgroup/start_bot_and_api.sh"'
    result = subprocess.run(['powershell', '-Command', full_cmd], capture_output=True, text=True, timeout=30)
    print(result.stdout)
    if result.stderr:
        print("Error:", result.stderr)
except subprocess.TimeoutExpired:
    print("❌ 部署超時")
except Exception as e:
    print(f"❌ 部署失敗: {e}")
