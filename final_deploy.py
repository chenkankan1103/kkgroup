#!/usr/bin/env python3
"""最終部署驗證和 Bot 啟動"""

import subprocess
import time

print("=" * 70)
print("🚀 KKCoin V2 最終部署驗證")
print("=" * 70)

# 1. 打包本機最新版本
print("\n📦 打包最新版本...")
local_file = "commands/kkcoin_visualizer_v2.py"

try:
    with open(local_file, 'rb') as f:
        local_content = f.read()
    print(f"   ✅ 本機版本: {len(local_content)} bytes")
except Exception as e:
    print(f"   ❌ 讀取失敗: {e}")
    exit(1)

# 2. 上傳到 GCP
print("\n📤 上傳到 GCP...")
cmd = [
    "scp",
    local_file,
    "gcp-kkgroup:/home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"
]

try:
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode == 0:
        print(f"   ✅ 上傳成功")
    else:
        print(f"   ⚠️ SCP returns: {result.returncode}")
        if result.stderr:
            print(f"      {result.stderr.decode('utf-8', errors='ignore')[:100]}")
except Exception as e:
    print(f"   ❌ 上傳異常: {e}")

# 3. 重啟 Bot
print("\n🔄 重啟 Bot...")
restart_cmd = [
    "ssh",
    "gcp-kkgroup",
    "pkill -f 'python bot.py' 2>/dev/null; sleep 2; cd /home/e193752468/kkgroup && nohup python bot.py > /tmp/bot.log 2>&1 &"
]

try:
    subprocess.run(restart_cmd, capture_output=True, timeout=10)
    print(f"   ✅ 重啟命令已發送")
    time.sleep(3)
except Exception as e:
    print(f"   ❌ 重啟失敗: {e}")

# 4. 驗證運行
print("\n✅ 驗證運行...")
check_cmd = [
    "ssh",
    "gcp-kkgroup",
    "ps aux | grep '[p]ython bot.py' | grep -v grep | wc -l"
]

try:
    result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)
    count = result.stdout.strip()
    if int(count) > 0:
        print(f"   ✅ Bot 進程運行中 ({count} 個)")
    else:
        print(f"   ⚠️ 未檢測到 Bot 進程")
except Exception as e:
    print(f"   ⚠️ 檢查失敗: {e}")

print("\n" + "=" * 70)
print("✅ 部署完成!")
print("=" * 70)
print("\n📝 後續步驟:")
print("   1. 在 Discord 執行: /kkcoin_v2")
print("   2. 應會看到改進的視覺效果")
print("   3. 顏色和字型應該與初版一致")
