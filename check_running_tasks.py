#!/usr/bin/env python3
"""
直接檢查運行中的機器人進程的任務狀態
"""

import os
import sys

# 添加當前目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 嘗試直接檢查運行中的進程
print("🔍 檢查運行中的 Discord 機器人任務狀態...")

# 檢查進程
import subprocess
result = subprocess.run(['pgrep', '-f', 'python.*bot.py'], capture_output=True, text=True)
if result.returncode == 0:
    pids = result.stdout.strip().split('\n')
    print(f"找到 {len(pids)} 個機器人進程: {pids}")
else:
    print("❌ 沒有找到運行中的機器人進程")

# 嘗試連接到運行中的進程（如果可能的話）
print("\n嘗試檢查任務狀態...")
try:
    import status_dashboard
    task = status_dashboard.global_update_logs_task
    print(f"任務對象存在: {task}")
    print(f"任務運行狀態: {task.is_running()}")
    print(f"任務名稱: {task.coro.__name__ if hasattr(task, 'coro') else 'N/A'}")
except Exception as e:
    print(f"❌ 無法檢查任務狀態: {e}")

print("\n檢查完成")