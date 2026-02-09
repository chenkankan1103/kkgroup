#!/usr/bin/env python3
"""檢查 GCP 狀態並清理重複進程"""

import subprocess

print("=" * 70)
print("🔍 檢查 GCP 狀態")
print("=" * 70)

# 1. 當前用戶
print("\n📋 當前登入用戶:")
result = subprocess.run(
    ["ssh", "gcp-kkgroup", "whoami"],
    capture_output=True,
    text=True,
    timeout=10
)
print(f"   用戶: {result.stdout.strip()}")

# 2. 檢查進程
print("\n🔍 檢查 Bot 進程:")
result = subprocess.run(
    ["ssh", "gcp-kkgroup", "ps aux | grep '[b]ot.py' | grep python"],
    capture_output=True,
    text=True,
    timeout=10
)
lines = [l for l in result.stdout.strip().split('\n') if l]
print(f"   找到 {len(lines)} 個進程")
for line in lines:
    parts = line.split()
    if len(parts) >= 11:
        print(f"   - PID: {parts[1]}, 命令: {' '.join(parts[10:13])}")

# 3. 檢查 systemd 服務
print("\n⚙️ 檢查 systemd 服務:")
for service in ["discord-bot", "discord-shopbot", "discord-uibot"]:
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", f"systemctl --user is-active {service}.service 2>&1"],
        capture_output=True,
        text=True,
        timeout=10
    )
    status = result.stdout.strip()
    emoji = "✅" if status == "active" else "❌"
    print(f"   {emoji} {service}.service: {status}")

# 4. 建議操作
print("\n" + "=" * 70)
print("💡 建議操作:")
print("=" * 70)
print("\n如果有重複進程，執行以下命令清理：")
print("   ssh gcp-kkgroup 'pkill -f bot.py'")
print("   ssh gcp-kkgroup 'systemctl --user restart discord-bot discord-shopbot discord-uibot'")
