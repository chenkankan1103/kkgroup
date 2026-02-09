#!/usr/bin/env python3
"""
使用 Python Paramiko 上傳 KKCoin V2 改進版本到 GCP
"""

import subprocess
import os
import time
import sys

print("=" * 70)
print("🚀 部署改進的 KKCoin V2 到 GCP")
print("=" * 70)

# 1️⃣ 上傳文件
print("\n📁 步驟 1: 上傳文件...")

local_visualizer = "commands/kkcoin_visualizer_v2.py"

if not os.path.exists(local_visualizer):
    print(f"❌ 找不到文件: {local_visualizer}")
    sys.exit(1)

# 計算文件大小
file_size = os.path.getsize(local_visualizer)
print(f"   檔案大小: {file_size:,} bytes")

# 使用 SCP 上傳
try:
    cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        local_visualizer,
        "gcp-kkgroup:/home/e193752468/kkgroup/commands/"
    ]
    
    print(f"   命令: scp {local_visualizer} gcp-kkgroup:...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        print(f"   ✅ 上傳成功 ({file_size:,} bytes)")
    else:
        print(f"   ⚠️ SCP 結果: {result.returncode}")
        if result.stderr:
            print(f"   stderr: {result.stderr[:100]}")

except subprocess.TimeoutExpired:
    print(f"   ❌ 上傳超時")
except Exception as e:
    print(f"   ❌ 上傳出錯: {e}")

# 2️⃣ 驗證文件
print("\n✓ 步驟 2: 驗證遠程文件...")

try:
    verify_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no", 
        "-o", "UserKnownHostsFile=/dev/null",
        "gcp-kkgroup",
        "ls -lh /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"
    ]
    
    result = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=15)
    
    if result.returncode == 0:
        print(f"   ✅ 文件驗證成功:")
        print(f"   {result.stdout.strip()}")
    else:
        print(f"   ❌ 文件驗證失敗")
        
except Exception as e:
    print(f"   ❌ 驗證出錯: {e}")

# 3️⃣ 重啟 Bot
print("\n↻ 步驟 3: 重啟 Bot 進程...")

try:
    # 先查出所有 bot.py 進程
    ps_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null", 
        "gcp-kkgroup",
        "ps aux | grep [b]ot.py | awk '{print $2}'"
    ]
    
    result = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=10)
    pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
    
    if pids:
        print(f"   找到 {len(pids)} 個 Bot 進程: {pids}")
        
        # 停止所有 bot.py 進程
        for pid in pids:
            kill_cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "gcp-kkgroup",
                f"sudo kill -9 {pid} 2>/dev/null || kill -9 {pid}"
            ]
            subprocess.run(kill_cmd, capture_output=True, timeout=5)
            print(f"   🛑 已停止進程 {pid}")
        
        # 等待進程完全停止
        time.sleep(2)
        
        # 啟動新的 bot.py
        print(f"   🔄 啟動新的 Bot 進程...")
        
        start_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "gcp-kkgroup",
            "cd /home/e193752468/kkgroup && nohup python bot.py > /tmp/bot_$(date +%s).log 2>&1 &"
        ]
        
        result = subprocess.run(start_cmd, capture_output=True, timeout=15)
        
        # 等待啟動
        time.sleep(3)
        
        # 驗證新進程
        verify_start = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "gcp-kkgroup",
            "ps aux | grep [b]ot.py"
        ]
        
        result = subprocess.run(verify_start, capture_output=True, text=True, timeout=10)
        
        if "bot.py" in result.stdout:
            print(f"   ✅ Bot 已成功重啟")
            for line in result.stdout.strip().split('\n'):
                if 'bot.py' in line:
                    pid = line.split()[1]
                    print(f"   新進程 PID: {pid}")
        else:
            print(f"   ⚠️ Bot 可能未成功啟動")
    else:
        print(f"   ℹ️ 沒有找到運行中的 Bot 進程 (可能需要手動啟動)")

except Exception as e:
    print(f"   ❌ 重啟失敗: {e}")

# 4️⃣ 檢查日誌
print("\n📋 步驟 4: 檢查 Bot 日誌...")

try:
    log_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "gcp-kkgroup",
        "tail -15 /tmp/bot_*.log 2>/dev/null | tail -20"
    ]
    
    result = subprocess.run(log_cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0 and result.stdout:
        lines = result.stdout.strip().split('\n')
        print(f"   最後 {min(10, len(lines))} 行日誌:")
        for line in lines[-10:]:
            if line.strip():
                print(f"   {line}")
    else:
        print(f"   ℹ️ 暫無日誌可用")

except Exception as e:
    print(f"   ⚠️ 無法讀取日誌: {e}")

print("\n" + "=" * 70)
print("✅ 部署完成！")
print("=" * 70)

print("""
📝 接下來的步驟:

1️⃣ 在 Discord 中測試:
   輸入命令: /kkcoin_v2
   
2️⃣ 預期看到:
   ✨ 3 張改進的圖表
   ① 排行榜 (前 15 名, 金銀銅特效)
   ② 長條圖 (漸變色長條 + 立體陰影)
   ③ 饼圖 + 周統計 (豐富配色 + 指標卡片)

3️⃣ 如需自動更新:
   執行命令: /kkcoin_v2_setup #頻道名稱
   系統會每 5 分鐘自動更新一次

💡 故障排除:
   如果 Bot 未啟動或出錯，執行:
   ssh gcp-kkgroup 'tail -50 /tmp/bot_*.log | tail -30'
""")
