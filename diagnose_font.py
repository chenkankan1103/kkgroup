#!/usr/bin/env python3
"""診斷中文字型問題"""

import subprocess
import os

print("=" * 70)
print("🔍 診斷中文字型問題")
print("=" * 70)

# 1. 檢查本地字型
print("\n1️⃣ 檢查本地字型...")
local_font = "fonts/NotoSansCJKtc-Regular.otf"
if os.path.exists(local_font):
    size = os.path.getsize(local_font)
    print(f"   ✅ 找到本地字型: {size:,} bytes")
else:
    print(f"   ❌ 找不到本地字型: {local_font}")

# 2. 檢查 GCP 上的字型
print("\n2️⃣ 檢查 GCP 上的字型...")
cmd = ["ssh", "gcp-kkgroup", "ls -lh /home/e193752468/kkgroup/fonts/NotoSansCJKtc-Regular.otf 2>/dev/null || echo 'NOT_FOUND'"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

if "NOT_FOUND" not in result.stdout:
    print(f"   ✅ GCP 上找到字型")
    print(f"      {result.stdout.strip()}")
else:
    print(f"   ❌ GCP 上找不到字型")
    print(f"      將上傳字型...")
    
    # 上傳字型
    cmd = ["scp", local_font, "gcp-kkgroup:/home/e193752468/kkgroup/fonts/"]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    
    if result.returncode == 0:
        print(f"   ✅ 字型上傳成功")
    else:
        print(f"   ❌ 字型上傳失敗")

# 3. 測試 matplotlib 字型加載
print("\n3️⃣ 測試 matplotlib 字型加載在 GCP...")
test_code = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os

font_path = '/home/e193752468/kkgroup/fonts/NotoSansCJKtc-Regular.otf'
if os.path.exists(font_path):
    print(f"✅ 字型文件存在: {os.path.getsize(font_path)} bytes")
    try:
        prop = fm.FontProperties(fname=font_path)
        print(f"✅ matplotlib 可以加載字型")
        print(f"   字型名稱: {prop.get_name()}")
    except Exception as e:
        print(f"❌ matplotlib 加載字型失敗: {e}")
else:
    print(f"❌ 字型文件不存在: {font_path}")
"""

cmd = ["ssh", "gcp-kkgroup", f"cd /home/e193752468/kkgroup && python -c \"{test_code}\""]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

print("   " + "\n   ".join(result.stdout.strip().split("\n")))
if result.stderr and "error" in result.stderr.lower():
    print(f"   ⚠️ stderr: {result.stderr[:100]}")

# 4. 測試 PIL 字型加載
print("\n4️⃣ 測試 PIL 字型加載在 GCP...")
test_code = """
from PIL import ImageFont
import os

font_path = '/home/e193752468/kkgroup/fonts/NotoSansCJKtc-Regular.otf'
if os.path.exists(font_path):
    try:
        font = ImageFont.truetype(font_path, size=24)
        print(f"✅ PIL 可以加載字型")
    except Exception as e:
        print(f"❌ PIL 加載字型失敗: {e}")
else:
    print(f"❌ 字型文件不存在")
"""

cmd = ["ssh", "gcp-kkgroup", f"cd /home/e193752468/kkgroup && python -c \"{test_code}\""]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

print("   " + "\n   ".join(result.stdout.strip().split("\n")))

print("\n" + "=" * 70)
