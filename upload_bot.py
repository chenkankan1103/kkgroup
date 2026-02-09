#!/usr/bin/env python3
"""
上傳修復後的 bot.py 到 GCP
"""
import subprocess
import sys

# 讀取本地 bot.py
with open('bot.py', 'rb') as f:
    content = f.read()

print(f"📤 上傳 bot.py ({len(content)} 字節)")

# 通過 SSH 上傳
cmd = 'ssh gcp-kkgroup "cat > /tmp/bot_new.py"'
proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, stderr = proc.communicate(input=content, timeout=30)

if proc.returncode == 0:
    print("✅ bot.py 上傳成功")
    
    # 驗證並部署
    verify_cmd = 'ssh gcp-kkgroup "sudo cp /tmp/bot_new.py /home/e193752468/kkgroup/bot.py && sudo chown e193752468:e193752468 /home/e193752468/kkgroup/bot.py && python3 -m py_compile /home/e193752468/kkgroup/bot.py && echo \'✅ 語法檢查通過\'"'
    result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=30)
    
    print(result.stdout)
    if result.returncode != 0:
        print("❌ 部署失敗:")
        print(result.stderr)
        sys.exit(1)
    
    print("✅ bot.py 已成功部署到 GCP")
else:
    print("❌ 上傳失敗:")
    print(stderr.decode())
    sys.exit(1)

print("")
print("即將重啟 Bot...")
restart_cmd = 'ssh gcp-kkgroup "sudo systemctl restart bot"'
subprocess.run(restart_cmd, shell=True, timeout=10)
print("⏳ Bot 重啟中...")
