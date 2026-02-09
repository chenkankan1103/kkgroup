#!/usr/bin/env python3
"""
使用二進制模式上傳改進的 KKCoin V2 到 GCP
"""

import subprocess
import os

print("=" * 60)
print("📤 部署改進的 KKCoin V2（二進制模式）")
print("=" * 60)

local_file = "commands/kkcoin_visualizer_v2.py"
remote_path = "/home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"

if not os.path.exists(local_file):
    print(f"❌ 找不到: {local_file}")
    exit(1)

# 檢查文件大小
file_size = os.path.getsize(local_file)
print(f"\n📁 正在上傳: {local_file}")
print(f"  檔案大小: {file_size:,} bytes")

# 使用 SSH 的 SFTP 或 SCP (二進制)
try:
    cmd = [
        "scp",
        local_file,
        f"gcp-kkgroup:{remote_path}"
    ]
    
    print(f"\n📤 通過 SCP 上傳...")
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    
    if result.returncode == 0:
        print(f"✅ 上傳成功！")
    else:
        print(f"⚠️ SCP 返回碼: {result.returncode}")
        if result.stderr:
            print(f"   stderr: {result.stderr.decode('utf-8', errors='ignore')[:200]}")

except subprocess.TimeoutExpired:
    print(f"❌ 上傳超時")
except Exception as e:
    print(f"❌ 上傳出錯: {e}")

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

# 重啟 Bot
print(f"\n🔄 重啟 Bot 進程...")

try:
    cmd = [
        "ssh",
        "gcp-kkgroup",
        "pkill -f bot.py; sleep 1; cd /home/e193752468/kkgroup && nohup python bot.py > /tmp/bot.log 2>&1 &"
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=20)
    
    if result.returncode == 0 or "bot.py" in result.stderr.decode('utf-8', errors='ignore'):
        print(f"✅ Bot 已重啟！")
    else:
        print(f"⚠️ 重啟可能需要檢查")

except Exception as e:
    print(f"❌ 重啟出錯: {e}")

print("\n" + "=" * 60)
print("✅ 部署完成！")
print("=" * 60)
print("\n📝 下一步:")
print("   在 Discord 執行: /kkcoin_v2")
