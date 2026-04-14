#!/usr/bin/env python3
"""
修復 crontab 配置：改用虛擬環境 Python
"""
import subprocess

# 新的 crontab 配置（使用虛擬環境 Python）
new_cron = """# m h  dom mon dow   command
*/5 * * * * /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/sync_to_sheet.py >> /home/e193752468/kkgroup/sync_cron.log 2>&1
*/5 * * * * /home/e193752468/kkgroup/venv/bin/python /home/e193752468/kkgroup/update_restart.py >> /home/e193752468/kkgroup/update.log 2>&1
"""

try:
    result = subprocess.run(
        ["crontab", "-"],
        input=new_cron,
        check=True,
        capture_output=True,
        text=True
    )
    print("✅ Crontab 已更新 (使用虛擬環境 Python)")
    print("驗證更新後的 crontab:")
    
    verify = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
        check=True
    )
    print(verify.stdout)
    
except subprocess.CalledProcessError as e:
    print(f"❌ 更新失敗: {e.stderr}")
except Exception as e:
    print(f"❌ 發生錯誤: {e}")
