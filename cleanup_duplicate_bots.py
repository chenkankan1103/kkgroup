#!/usr/bin/env python3
"""殺死重複的 Bot 進程，讓 systemd 自動重啟"""

import subprocess
import time

print("=" * 70)
print("🔪 清理重複 Bot 進程")
print("=" * 70)

# 1. 殺死所有 bot 進程
print("\n1️⃣ 殺死所有 bot.py 進程...")
cmd = ["ssh", "gcp-kkgroup", "pkill -9 -f 'python.*bot.py'"]
result = subprocess.run(cmd, capture_output=True, timeout=10)
print("   ✅ bot.py 進程已終止")

# 2. 殺死所有 shopbot 進程
print("\n2️⃣ 殺死所有 shopbot.py 進程...")
cmd = ["ssh", "gcp-kkgroup", "pkill -9 -f 'python.*shopbot.py'"]
result = subprocess.run(cmd, capture_output=True, timeout=10)
print("   ✅ shopbot.py 進程已終止")

# 3. 殺死所有 uibot 進程
print("\n3️⃣ 殺死所有 uibot.py 進程...")
cmd = ["ssh", "gcp-kkgroup", "pkill -9 -f 'python.*uibot.py'"]
result = subprocess.run(cmd, capture_output=True, timeout=10)
print("   ✅ uibot.py 進程已終止")

# 4. 等待 systemd 重啟
print("\n⏳ 等待 systemd 自動重啟 (3秒)...")
time.sleep(3)

# 5. 檢查進程
print("\n✅ 驗證進程:")
cmd = ["ssh", "gcp-kkgroup", 
       "echo '=== bot.py ===' && pgrep -f 'python.*bot.py' | wc -l && " +
       "echo '=== shopbot.py ===' && pgrep -f 'python.*shopbot.py' | wc -l && " +
       "echo '=== uibot.py ===' && pgrep -f 'python.*uibot.py' | wc -l"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

output_lines = result.stdout.strip().split('\n')
for line in output_lines:
    if line.strip():
        print(f"   {line}")

print("\n" + "=" * 70)
print("✅ 清理完成！systemd 應已自動重啟 Bot")
print("=" * 70)
