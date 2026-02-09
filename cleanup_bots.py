#!/usr/bin/env python3
"""清理重複的 Bot 進程並重啟 systemd 服務"""

import subprocess
import time

print("=" * 70)
print("🧹 清理重複的 Bot 進程")
print("=" * 70)

# 1. 停止所有 bot.py 進程
print("\n🛑 停止所有 bot.py 進程...")
subprocess.run(
    ["ssh", "gcp-kkgroup", "pkill -f 'bot.py'"],
    capture_output=True,
    timeout=10
)
print("   ✅ 已發送停止信號")

time.sleep(2)

# 2. 重啟 systemd 服務
print("\n🔄 重啟 systemd 服務...")
services = ["discord-bot", "discord-shopbot", "discord-uibot"]

for service in services:
    print(f"\n   啟動 {service}.service...")
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", f"systemctl --user restart {service}.service"],
        capture_output=True,
        timeout=10
    )
    if result.returncode == 0:
        print(f"   ✅ {service}.service 已重啟")
    else:
        print(f"   ⚠️ {service}.service 重啟可能有問題")

time.sleep(3)

# 3. 檢查服務狀態
print("\n✅ 檢查服務狀態...")
for service in services:
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", f"systemctl --user is-active {service}.service"],
        capture_output=True,
        text=True,
        timeout=10
    )
    status = result.stdout.strip()
    emoji = "✅" if status == "active" else "❌"
    print(f"   {emoji} {service}.service: {status}")

# 4. 檢查進程
print("\n📊 當前運行的 Bot 進程:")
result = subprocess.run(
    ["ssh", "gcp-kkgroup", "pgrep -f 'python.*bot.py' | wc -l"],
    capture_output=True,
    text=True,
    timeout=10
)
count = result.stdout.strip()
print(f"   共 {count} 個 Bot 進程")

print("\n" + "=" * 70)
print("✅ 完成！")
print("=" * 70)
print("\n💡 如果 Bot 還是離線，請檢查:")
print("   1. Discord TOKEN 是否正確")
print("   2. 網路連接是否正常")
print("   3. 執行: ssh gcp-kkgroup 'journalctl --user -u discord-bot.service -n 50'")
