#!/usr/bin/env python3
"""診斷 Bot 重複問題"""

import subprocess

print("=" * 70)
print("🔍 診斷 Bot 重複問題")
print("=" * 70)

# 1. 檢查 systemd 服務
print("\n1️⃣ 檢查 systemd 服務:")
cmd = ["ssh", "gcp-kkgroup", "ls -la /etc/systemd/system/ | grep -E 'bot|shop|ui'"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
print(result.stdout if result.stdout else "   無結果")

# 2. 檢查進程數
print("\n2️⃣ 檢查進程數:")
cmd = ["ssh", "gcp-kkgroup", "echo '=== bot.py ===' && pgrep -f 'python.*bot.py' | wc -l && echo '=== shopbot.py ===' && pgrep -f 'python.*shopbot.py' | wc -l && echo '=== uibot.py ===' && pgrep -f 'python.*uibot.py' | wc -l"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
print(result.stdout if result.stdout else "   無結果")

# 3. 檢查 systemd 是否運行
print("\n3️⃣ 檢查 systemd 服務狀態:")
cmd = ["ssh", "gcp-kkgroup", "sudo systemctl is-active bot.service 2>/dev/null && echo '✅ bot.service 活躍' || echo '⚠️ bot.service 不活躍'"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
print(result.stdout if result.stdout else "   無結果")

print("\n" + "=" * 70)
