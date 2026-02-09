#!/usr/bin/env python3
"""
使用 SSH Exec 上傳文件
"""

import subprocess
import os

print("=" * 60)
print("📤 上傳改進的 KKCoin V2")
print("=" * 60)

# 讀取本地文件
local_file = "commands/kkcoin_visualizer_v2.py"
remote_path = "/home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"

if not os.path.exists(local_file):
    print(f"❌ 找不到: {local_file}")
    exit(1)

print(f"\n📁 正在讀取: {local_file}")
with open(local_file, 'r', encoding='utf-8') as f:
    content = f.read()

file_size = len(content.encode('utf-8'))
print(f"✓ 檔案大小: {file_size:,} bytes")

# 上傳到 GCP
print(f"\n📤 上傳中...")

try:
    # 使用 SSH 直接寫入
    ssh_cmd = [
        "ssh",
        "gcp-kkgroup",
        f"cat > {remote_path}",
    ]
    
    result = subprocess.run(
        ssh_cmd,
        input=content,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    if result.returncode == 0:
        print(f"✅ 上傳成功！")
    else:
        print(f"⚠️ 返回碼: {result.returncode}")
        if result.stderr:
            print(f"錯誤: {result.stderr[:200]}")

except Exception as e:
    print(f"❌ 上傳失敗: {e}")

# 驗證
print(f"\n🔍 驗證遠程文件...")

try:
    verify_cmd = ["ssh", "gcp-kkgroup", f"wc -l {remote_path}"]
    result = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0:
        print(f"✅ 驗證成功: {result.stdout.strip()}")
    else:
        print(f"❌ 驗證失敗")
        
except Exception as e:
    print(f"❌ 驗證出錯: {e}")

print("\n" + "=" * 60)
