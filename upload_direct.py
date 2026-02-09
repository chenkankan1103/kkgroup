#!/usr/bin/env python3
"""
直接上傳改進的 KKCoin V2 到 GCP
使用 SSH 管道方式直接傳輸
"""

import subprocess
import os

print("=" * 60)
print("📤 直接上傳 KKCoin V2 改進版本")
print("=" * 60)

# 1️⃣ 上傳 kkcoin_visualizer_v2.py
print("\n📁 上傳文件...")

local_file = "commands/kkcoin_visualizer_v2.py"
remote_path = "/home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"

if not os.path.exists(local_file):
    print(f"❌ 找不到: {local_file}")
    exit(1)

# 使用 cat 管道方式傳輸
try:
    with open(local_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用 heredoc 上傳
    cmd = f"""ssh gcp-kkgroup 'cat > {remote_path} << 'EOF'
{content}
EOF
'"""
    
    print(f"📤 上傳: {local_file} -> {remote_path}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        print(f"✅ 上傳成功！")
    else:
        print(f"❌ 上傳失敗")
        if result.stderr:
            print(f"錯誤: {result.stderr[:200]}")

except Exception as e:
    print(f"❌ 錯誤: {e}")

# 2️⃣ 驗證文件
print("\n🔍 驗證遠程文件...")
verification_cmd = f"ssh gcp-kkgroup 'wc -l {remote_path}'"
result = subprocess.run(verification_cmd, shell=True, capture_output=True, text=True, timeout=10)

if result.returncode == 0:
    print(f"✅ 文件已驗證: {result.stdout.strip()}")
else:
    print(f"❌ 驗證失敗")

print("\n" + "=" * 60)
print("✅ 上傳完成！")
print("=" * 60)
