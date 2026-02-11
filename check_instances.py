#!/usr/bin/env python3
"""
檢查機器人實例和任務狀態
"""

import os
import sys

# 添加當前目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接檢查模組狀態
try:
    import status_dashboard
    print("✅ status_dashboard 模組載入成功")

    # 檢查任務狀態
    task_running = status_dashboard.global_update_logs_task.is_running()
    print(f"全域日誌任務運行狀態: {task_running}")

    # 檢查機器人實例
    bot_instances = getattr(status_dashboard, 'bot_instances', {})
    print(f"機器人實例數量: {len(bot_instances)}")
    for bot_type, instance in bot_instances.items():
        print(f"  {bot_type}: {'存在' if instance else '不存在'}")

    # 檢查日誌存儲
    logs_storage = getattr(status_dashboard, 'logs_storage', {})
    print(f"日誌存儲狀態:")
    for bot_type, logs in logs_storage.items():
        print(f"  {bot_type}: {len(logs)} 條日誌")

except Exception as e:
    print(f"❌ 檢查失敗: {e}")
    import traceback
    traceback.print_exc()