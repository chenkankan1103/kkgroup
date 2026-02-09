#!/usr/bin/env python3
"""檢查並設置 Bot systemd 服務"""

import subprocess
import sys

print("=" * 70)
print("🔧 檢查 Bot 狀態和設置 systemd")
print("=" * 70)

# 1. 檢查 systemd 用戶服務
print("\n1️⃣ 檢查 systemd 用戶服務...")

check_cmd = [
    "ssh",
    "gcp-kkgroup",
    "systemctl --user list-unit-files | grep kkgroup || echo '❌ 未設置服務'"
]

try:
    result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)
    print(result.stdout)
except Exception as e:
    print(f"⚠️ 檢查失敗: {e}")

# 2. 檢查 Bot 進程是否運行
print("\n2️⃣ 檢查 Bot 進程...")

check_proc = [
    "ssh",
    "gcp-kkgroup",
    "ps aux | grep -E 'bot.py|shopbot|uibot' | grep -v grep | wc -l"
]

try:
    result = subprocess.run(check_proc, capture_output=True, text=True, timeout=10)
    count = result.stdout.strip()
    print(f"✅ 運行中的 Bot 進程: {count} 個")
except Exception as e:
    print(f"❌ 檢查失敗: {e}")

# 3. 檢查 Discord 連接狀態
print("\n3️⃣ 檢查 Bot 日誌（最後 10 行）...")

check_log = [
    "ssh",
    "gcp-kkgroup",
    "tail -10 /tmp/bot.log 2>/dev/null | grep -E 'Logged in|Latency|error|Error' || echo '（無日誌或尚無連接信息）'"
]

try:
    result = subprocess.run(check_log, capture_output=True, text=True, timeout=10)
    print(result.stdout[:500])
except Exception as e:
    print(f"⚠️ 無法讀取日誌: {e}")

# 4. 建議
print("\n" + "=" * 70)
print("📝 建議:")
print("=" * 70)
print("""
如果 Bot 已啟動但顯示離線，請檢查：

1️⃣ Discord 連接
   - 檢查 bot.log 是否有連接錯誤
   - 確認 TOKEN 有效
   
2️⃣ 啟用 systemd 自動啟動
   ssh gcp-kkgroup
   systemctl --user daemon-reload
   systemctl --user enable kkgroup-bot
   systemctl --user start kkgroup-bot
   systemctl --user status kkgroup-bot
   
3️⃣ 查看詳細日誌
   journalctl --user -u kkgroup-bot -f
   
4️⃣ 手動重啟 Bot
   ssh gcp-kkgroup "pkill -f 'python.*bot.py'; sleep 1; cd /home/e193752468/kkgroup && nohup python3 bot.py > /tmp/bot.log 2>&1 &"
""")

print("\n✅ 檢查完成")
