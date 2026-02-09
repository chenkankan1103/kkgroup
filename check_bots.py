#!/usr/bin/env python3
"""檢查 Bot 進程和 systemd 服務狀態"""

import subprocess

print("=" * 70)
print("🔍 Bot 進程和 systemd 服務檢查")
print("=" * 70)

# 1. 檢查所有 python 進程
print("\n1️⃣ 檢查所有 Bot 進程:")
print("-" * 70)

cmd = ["ssh", "gcp-kkgroup", "pgrep -af 'python.*bot\\.py|python.*shopbot\\.py|python.*uibot\\.py'"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

if result.stdout:
    lines = result.stdout.strip().split('\n')
    print(f"找到 {len(lines)} 個進程:")
    for i, line in enumerate(lines, 1):
        print(f"  {i}. {line[:80]}")
else:
    print("❌ 沒有找到任何 Bot 進程")

# 2. 檢查 systemd 服務狀態
print("\n2️⃣ 檢查 systemd 服務:")
print("-" * 70)

services = ["bot", "shopbot", "uibot"]
for service in services:
    cmd = ["ssh", "gcp-kkgroup", f"systemctl --user is-active {service} 2>/dev/null || echo '未找到'"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    status = result.stdout.strip()
    
    if status == "active":
        print(f"  ✅ {service}: {status}")
    elif status == "inactive":
        print(f"  ⚠️ {service}: {status}")
    else:
        print(f"  ❌ {service}: {status}")

# 3. 檢查重複進程
print("\n3️⃣ 檢查重複進程:")
print("-" * 70)

cmd = ["ssh", "gcp-kkgroup", "ps aux | grep -E 'bot\\.py|shopbot\\.py|uibot\\.py' | grep -v grep | wc -l"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0

if count > 3:
    print(f"  ⚠️ 檢測到重複進程! (預期 3 個, 實際 {count} 個)")
    print(f"     建議清理重複進程")
else:
    print(f"  ✅ 進程數正常 ({count}/3)")

# 4. 檢查最近日誌
print("\n4️⃣ 最近 systemd 日誌:")
print("-" * 70)

cmd = ["ssh", "gcp-kkgroup", "journalctl --user -u bot -u shopbot -u uibot -n 5 --no-pager 2>/dev/null || echo '無日誌'"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
print(result.stdout[:500] if result.stdout else "無日誌")

print("\n" + "=" * 70)
