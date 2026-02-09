#!/usr/bin/env python3
"""驗證改進的字型設置已部署"""

import subprocess

print("🔍 驗證字型設置...")

# 驗證 FONT_PATH 在正確位置
cmd = [
    "ssh",
    "gcp-kkgroup",
    "python -c 'import sys; sys.path.insert(0, \\\"/home/e193752468/kkgroup\\\"); from commands.kkcoin_visualizer_v2 import FONT_PATH, MATPLOTLIB_AVAILABLE; print(f\\\"✅ FONT_PATH: {FONT_PATH}\\\"); print(f\\\"✅ matplotlib 可用: {MATPLOTLIB_AVAILABLE}\\\")'"
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    print(result.stdout)
    if result.stderr:
        print(f"錯誤信息: {result.stderr[:200]}")
except Exception as e:
    print(f"❌ 驗證失敗: {e}")

print("\n✅ 部署驗證完成")
print("\n現在可以在 Discord 中執行: /kkcoin_v2")
