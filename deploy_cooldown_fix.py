#!/usr/bin/env python3
"""
部署冷卻時間限制更新到 GCP
"""
import subprocess
import time
import sys

print("🚀 開始部署冷卻時間限制更新...")

# 部署文件列表
files_to_deploy = [
    ("commands/kcoin.py", "/home/e193752468/kkgroup/commands/kcoin.py"),
]

try:
    # 上傳文件
    for local_path, remote_path in files_to_deploy:
        print(f"\n📤 上傳 {local_path}...")
        result = subprocess.run(
            f'scp -o "StrictHostKeyChecking=no" "{local_path}" e193752468@gcp-kkgroup:{remote_path}',
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✅ {local_path} 上傳成功")
        else:
            print(f"❌ {local_path} 上傳失敗: {result.stderr}")
            sys.exit(1)
    
    # 重啟 Bot
    print("\n🔄 30 秒後重啟 Bot 服務...")
    time.sleep(5)
    
    print("\n🔄 正在重啟 Bot 服務...")
    result = subprocess.run(
        'ssh gcp-kkgroup "sudo systemctl restart bot.service"',
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 or "succee" in result.stderr.lower():
        print("✅ Bot 服務重啟命令已發送")
    else:
        print(f"⚠️ 重啟響應: {result.stderr}")
    
    # 等待重啟
    time.sleep(3)
    
    # 驗證
    print("\n✔️ 驗證更新...")
    result = subprocess.run(
        'ssh gcp-kkgroup "grep -c \'cooldown_times\' /home/e193752468/kkgroup/commands/kcoin.py"',
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and int(result.stdout.strip()) > 0:
        print("✅ 冷卻時間限制已成功部署！")
        print(f"   找到 {result.stdout.strip()} 個 cooldown_times 配置")
        print("\n📋 冷卻時間設定：")
        print("   - /kkcoin: 10 秒")
        print("   - /kkcoin_rank: 30 秒")
        print("   - /kkcoin_leaderboard: 30 秒")
        print("   - /kkcoin_pro: 30 秒")
        print("   - /kkcoin_weekly: 60 秒")
        print("   - /kkcoin_mvp: 60 秒")
        print("   - /kkcoin_v2: 60 秒")
    else:
        print("❌ 驗證失敗，請檢查部署")
        sys.exit(1)
    
    print("\n✨ 部署完成！")
    
except Exception as e:
    print(f"❌ 部署失敗: {e}")
    sys.exit(1)
