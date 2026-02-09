#!/usr/bin/env python3
"""清理重複 Bot 進程並重啟 systemd 服務"""

import subprocess
import time

print("=" * 70)
print("🔧 清理重複進程並重啟 systemd 服務")
print("=" * 70)

# 1. 殺死所有 Bot 進程
print("\n1️⃣ 殺死所有舊 Bot 進程...")
cmd = ["ssh", "gcp-kkgroup", "pkill -f 'python.*bot.py|python.*shopbot.py|python.*uibot.py'"]

try:
    subprocess.run(cmd, capture_output=True, timeout=10)
    print("   ✅ 舊進程已清理")
    time.sleep(2)
except Exception as e:
    print(f"   ⚠️ 清理出錯: {e}")

# 2. 重啟 systemd 服務
print("\n2️⃣ 重啟 systemd 服務...")
services = ["bot", "shopbot", "uibot"]

for service in services:
    print(f"   重啟 {service}...")
    
    # 停止服務
    cmd = ["ssh", "gcp-kkgroup", f"systemctl --user stop {service}"]
    try:
        subprocess.run(cmd, capture_output=True, timeout=10)
    except:
        pass
    
    time.sleep(1)
    
    # 啟動服務
    cmd = ["ssh", "gcp-kkgroup", f"systemctl --user start {service}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"      ✅ {service} 已啟動")
        else:
            print(f"      ⚠️ {service} 啟動失敗")
    except Exception as e:
        print(f"      ❌ {service} 出錯: {e}")
    
    time.sleep(1)

# 3. 驗證服務狀態
print("\n3️⃣ 驗證服務狀態...")
print("-" * 70)

for service in services:
    cmd = ["ssh", "gcp-kkgroup", f"systemctl --user is-active {service}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        status = result.stdout.strip()
        if status == "active":
            print(f"   ✅ {service}: {status}")
        else:
            print(f"   ⚠️ {service}: {status}")
    except Exception as e:
        print(f"   ❌ {service}: 檢查失敗")

print("\n" + "=" * 70)
print("✅ 清理和重啟完成！")
print("=" * 70)
print("\n📝 下一步:")
print("   - 檢查 Discord 中 Bot 是否上線")
print("   - 如果還是離線，檢查 Bot TOKEN 是否正確")
print("   - 查看日誌: journalctl --user -u bot -f")
