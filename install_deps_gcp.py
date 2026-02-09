#!/usr/bin/env python3
"""
在 GCP 遠程環境中安裝 matplotlib
"""
import subprocess
import sys

print("🔧 在 GCP 上安裝 matplotlib 依賴...")
print()

# 通過 SSH 執行安裝
cmd = """ssh gcp-kkgroup "source /home/e193752468/kkgroup/venv/bin/activate && pip install -q matplotlib numpy Pillow aiohttp && echo '✅ 依賴安裝完成' && pip list | grep matplotlib | head -1"
"""

result = subprocess.run(
    cmd,
    shell=True,
    capture_output=True,
    text=True,
    timeout=180
)

print("STDOUT:")
print(result.stdout)

if result.stderr:
    print("\nSTDERR:")
    print(result.stderr)

print("\n返回碼:", result.returncode)

if result.returncode == 0:
    print("\n✅ 安裝成功！")
else:
    print("\n❌ 安裝失敗")

sys.exit(result.returncode)
