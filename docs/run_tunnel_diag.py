#!/usr/bin/env python3
"""上傳并執行隧道診斷腳本"""
import subprocess
import tempfile
import os
import sys

# 診斷腳本內容
diag_script = """#!/bin/bash
echo "=== 1. 隧道進程狀態 ==="
sudo systemctl status cloudflared --no-pager 2>&1 | head -20

echo ""
echo "=== 2. cloudflared 配置文件 ==="
sudo cat /root/.cloudflared/*.json 2>/dev/null | head -30 || echo "(未找到)"

echo ""
echo "=== 3. 隧道聆聽地址和端口 ==="
sudo ss -tlnp 2>/dev/null | grep -E "cloudflare|:80" || echo "(無法取得)"

echo ""
echo "=== 4. cloudflared 啟動命令 ==="
sudo systemctl cat cloudflared 2>/dev/null | grep -E "ExecStart"

echo ""
echo "=== 5. 最新隧道日誌 ==="
sudo journalctl -u cloudflared -n 15 --no-pager 2>/dev/null | tail -10
"""

# 寫入臨時文件
with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
    f.write(diag_script)
    script_file = f.name

try:
    # 上傳腳本
    print("📤 上傳診斷腳本到 GCP VM...")
    scp_cmd = [
        'wsl', 'scp', '-i', os.path.expanduser('~/.ssh/id_rsa'),
        '-o', 'StrictHostKeyChecking=no',
        script_file, 'e193752468@10.128.0.3:/tmp/diagnose.sh'
    ]
    result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        print(f"上傳失敗: {result.stderr}")
        sys.exit(1)
    
    # 執行腳本
    print("🔍 執行診斷...")
    ssh_cmd = [
        'wsl', 'ssh', '-i', os.path.expanduser('~/.ssh/id_rsa'),
        '-o', 'StrictHostKeyChecking=no',
        'e193752468@10.128.0.3', 'bash /tmp/diagnose.sh'
    ]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
    print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print("⚠️  錯誤:", result.stderr)
    
finally:
    # 清理臨時文件
    try:
        os.unlink(script_file)
    except:
        pass
