#!/usr/bin/env python3
"""
檢查並重啟機器人
"""
import subprocess
import time
import sys

print("🔍 檢查機器人狀態與重啟...")

try:
    # 1. 檢查當前進程
    print("\n1️⃣ 檢查 Bot 進程...")
    result = subprocess.run(
        'ssh gcp-kkgroup "pgrep -f \'python.*bot.py\' | wc -l"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode == 0:
        count = result.stdout.strip()
        print(f"   當前運行中的 Bot 進程: {count} 個")
    else:
        print(f"   ⚠️ 無法檢查進程")
    
    # 2. 重啟服務
    print("\n2️⃣ 重啟 Bot 服務...")
    result = subprocess.run(
        'ssh gcp-kkgroup "sudo systemctl restart bot.service"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=15
    )
    print("   ✅ 重啟命令已發送")
    
    # 3. 等待重啟
    print("\n3️⃣ 等待 Bot 重啟...(3 秒)")
    time.sleep(3)
    
    # 4. 檢查重啟後的狀態
    print("\n4️⃣ 檢查重啟後的狀態...")
    result = subprocess.run(
        'ssh gcp-kkgroup "pgrep -f \'python.*bot.py\' | wc -l"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode == 0:
        count = result.stdout.strip()
        if int(count) > 0:
            print(f"   ✅ Bot 已成功重啟，進程數: {count}")
        else:
            print(f"   ⚠️ Bot 進程未啟動，請檢查日誌")
    
    # 5. 檢查服務狀態
    print("\n5️⃣ 檢查服務狀態...")
    result = subprocess.run(
        'ssh gcp-kkgroup "systemctl is-active bot.service"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode == 0:
        status = result.stdout.strip()
        print(f"   服務狀態: {status}")
    
    print("\n✨ 檢查完成！")
    print("   🤖 機器人應該已在 Discord 上線")
    print("   ⏳ 如果在 Discord 上看不到機器人，請等待 30 秒再檢查")
    
except Exception as e:
    print(f"❌ 檢查失敗: {e}")
    sys.exit(1)
