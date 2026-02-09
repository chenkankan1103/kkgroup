#!/usr/bin/env python3
"""
上傳改進的 KKCoin V2 可視化文件到 GCP
"""

import subprocess
import os
import time

# GCP SSH 配置
GCP_HOST = "gcp-kkgroup"
REMOTE_PATH = "/home/e193752468/kkgroup"

# 本地文件
LOCAL_FILES = {
    "commands/kkcoin_visualizer_v2.py": f"{REMOTE_PATH}/commands/kkcoin_visualizer_v2.py",
    "commands/kcoin.py": f"{REMOTE_PATH}/commands/kcoin.py",
}

print("=" * 60)
print("📤 上傳改進的 KKCoin V2 文件到 GCP")
print("=" * 60)

# 1️⃣ 上傳文件
print("\n📁 正在上傳文件...")
for local_file, remote_file in LOCAL_FILES.items():
    if not os.path.exists(local_file):
        print(f"   ❌ 找不到本地文件: {local_file}")
        continue
    
    try:
        # 使用 scp 上傳
        cmd = ["scp", local_file, f"{GCP_HOST}:{remote_file}"]
        print(f"   📤 上傳: {local_file}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"   ✅ {local_file} 上傳成功")
        else:
            print(f"   ⚠️ {local_file} 上傳可能失敗")
            if result.stderr:
                print(f"      錯誤: {result.stderr[:100]}")
    
    except Exception as e:
        print(f"   ❌ 上傳失敗: {e}")

# 2️⃣ 驗證文件
print("\n🔍 驗證遠程文件...")
try:
    cmd = f"ssh {GCP_HOST} 'ls -lah {REMOTE_PATH}/commands/kkcoin_visualizer_v2.py'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        print(f"   ✅ 遠程文件已確認存在")
        print(f"   {result.stdout.strip()}")
    else:
        print(f"   ❌ 驗證失敗")
except Exception as e:
    print(f"   ❌ 驗證錯誤: {e}")

# 3️⃣ 重啟 Bot
print("\n🔄 重啟 Bot 進程...")
try:
    # 查找 bot.py 進程
    cmd = "ssh gcp-kkgroup 'ps aux | grep \"bot.py\" | grep -v grep | awk \"{print $2}\"'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    pids = result.stdout.strip().split('\n')
    
    active_pids = [pid for pid in pids if pid]
    
    if active_pids:
        print(f"   找到 {len(active_pids)} 個 Bot 進程: {', '.join(active_pids)}")
        
        for pid in active_pids:
            if pid:
                # 杀死進程
                kill_cmd = f"ssh gcp-kkgroup 'sudo kill -9 {pid}'"
                subprocess.run(kill_cmd, shell=True, capture_output=True, timeout=10)
                print(f"   🛑 已停止進程 PID {pid}")
        
        # 等待
        time.sleep(2)
        
        # 重啟 bot.py (後台運行)
        restart_cmd = (
            f"ssh gcp-kkgroup 'cd {REMOTE_PATH} && "
            "nohup python bot.py > /tmp/bot.log 2>&1 &'"
        )
        result = subprocess.run(restart_cmd, shell=True, capture_output=True, timeout=15)
        
        # 等待啟動
        time.sleep(3)
        
        # 驗證 Bot 是否成功啟動
        verify_cmd = f"ssh gcp-kkgroup 'ps aux | grep \\\"bot.py\\\" | grep -v grep'"
        result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and "bot.py" in result.stdout:
            print(f"   ✅ Bot 已成功重啟")
            print(f"   {result.stdout.strip()}")
        else:
            print(f"   ⚠️ Bot 可能未正確啟動，請檢查日誌")
    else:
        print(f"   ⚠️ 找不到運行中的 Bot 進程")
        
except Exception as e:
    print(f"   ❌ 重啟失敗: {e}")

# 4️⃣ 檢查日誌
print("\n📋 檢查最新日誌...")
try:
    cmd = f"ssh gcp-kkgroup 'tail -20 /tmp/bot.log 2>/dev/null || echo \\\"日誌不可用\\\"'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    
    log_lines = result.stdout.strip().split('\n')
    for line in log_lines[-10:]:
        if line:
            print(f"   {line}")
except Exception as e:
    print(f"   ⚠️ 無法讀取日誌: {e}")

print("\n" + "=" * 60)
print("✅ 上傳和重啟流程完成！")
print("=" * 60)
print("\n📝 測試指令:")
print("   1. 進入 Discord")
print("   2. 執行 /kkcoin_v2 查看升級版排行榜")
print("   3. 檢查 3 張圖表是否正確顯示")
print("\n💡 如果有問題，檢查日誌:")
print(f"   ssh {GCP_HOST} 'tail -50 /tmp/bot.log'")
print()
