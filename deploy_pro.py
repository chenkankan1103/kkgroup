#!/usr/bin/env python3
"""部署新的 KKCoin Pro 版本到 GCP"""

import subprocess
import time

print("=" * 70)
print("🚀 部署 KKCoin Pro 版本")
print("=" * 70)

# 1. 上傳 kkcoin_pro.py
print("\n📤 上傳 kkcoin_pro.py...")
cmd = ["scp", "commands/kkcoin_pro.py", "gcp-kkgroup:/home/e193752468/kkgroup/commands/kkcoin_pro.py"]

try:
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode == 0:
        print(f"   ✅ kkcoin_pro.py 上傳成功")
    else:
        print(f"   ⚠️ 返回碼: {result.returncode}")
except Exception as e:
    print(f"   ⚠️ 上傳異常: {e}")

# 2. 上傳 kcoin.py
print("\n📤 上傳 kcoin.py...")
cmd = ["scp", "commands/kcoin.py", "gcp-kkgroup:/home/e193752468/kkgroup/commands/kcoin.py"]

try:
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode == 0:
        print(f"   ✅ kcoin.py 上傳成功")
    else:
        print(f"   ⚠️ 返回碼: {result.returncode}")
except Exception as e:
    print(f"   ⚠️ 上傳異常: {e}")

# 3. 重啟 Bot
print(f"\n🔄 重啟 Bot...")
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

# 4. 驗證
print(f"\n✅ 驗證...")
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
print("\n📝 現在可以在 Discord 使用:")
print("   /kkcoin_leaderboard - 原本列表格式排行榜")
print("   /kkcoin_pro - 新版深色主題排行榜 (推薦！)")
print("   /kkcoin_v2 - 升級版排行榜（3合1）")
