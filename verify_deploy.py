#!/usr/bin/env python3
import subprocess
import time

print("🔍 驗證部署狀態...")

# 檢查文件
print("\n1️⃣ 檢查遠程文件...")
try:
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", "test -f /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py && echo 'FILE_EXISTS' || echo 'FILE_NOT_FOUND'"],
        capture_output=True,
        text=True,
        timeout=10
    )
    status = result.stdout.strip()
    if "FILE_EXISTS" in status:
        print(f"   ✅ 文件已部署到 GCP")
    else:
        print(f"   ❌ 文件未找到")
except Exception as e:
    print(f"   ❌ 檢查失敗: {e}")

# 驗證文件內容
print("\n2️⃣ 驗證文件內容...")
try:
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", "grep 'def create_enhanced_leaderboard_image' /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py && echo 'FUNCTION_FOUND' || echo 'FUNCTION_NOT_FOUND'"],
        capture_output=True,
        text=True,
        timeout=10
    )
    if "FUNCTION_FOUND" in result.stdout:
        print(f"   ✅ 改進版本確認存在")
    else:
        print(f"   ❌ 找不到改進函數")
except Exception as e:
    print(f"   ❌ 驗證失敗: {e}")

# 重新啟動 Bot
print("\n3️⃣ 啟動 Bot...")
try:
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", "cd /home/e193752468/kkgroup && python bot.py > /tmp/bot.log 2>&1 &"],
        capture_output=True,
        timeout=5
    )
    print(f"   ✅ Bot 啟動命令發送")
    time.sleep(2)
    
    # 檢查是否啟動成功
    result = subprocess.run(
        ["ssh", "gcp-kkgroup", "pgrep -f 'python bot.py' | wc -l"],
        capture_output=True,
        text=True,
        timeout=10
    )
    count = result.stdout.strip()
    if int(count) > 0:
        print(f"   ✅ Bot 進程已啟動 ({count} 個進程)")
    else:
        print(f"   ⚠️ Bot 進程未見，可能在啟動中...")
        
except Exception as e:
    print(f"   ⚠️ 啟動出錯或超時: {e}")

print("\n" + "="*60)
print("✅ 部署驗證完成！")
print("="*60)
print("\n📝 下一步:")
print("   在 Discord 執行: /kkcoin_v2")
print("   應會看到改進的視覺效果（使用初版的字型和顏色）")
