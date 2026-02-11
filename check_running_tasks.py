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

# 檢查進程 (Windows 兼容)
import subprocess
try:
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], capture_output=True, text=True)
    if 'python.exe' in result.stdout:
        print("找到 python.exe 進程")
        # 檢查是否有 bot.py 相關的進程
        result2 = subprocess.run(['tasklist', '/FI', 'WINDOWTITLE eq *bot.py*'], capture_output=True, text=True)
        if result2.stdout.strip():
            print("找到 bot.py 相關的進程")
        else:
            print("沒有找到 bot.py 相關的進程")
    else:
        print("❌ 沒有找到 python.exe 進程")
except Exception as e:
    print(f"檢查進程時出錯: {e}")

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