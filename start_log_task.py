#!/usr/bin/env python3
"""
手動啟動全域日誌更新任務
"""

import asyncio
import os
import sys

# 添加當前目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def start_log_task():
    """手動啟動日誌任務"""
    try:
        from status_dashboard import global_update_logs_task, get_bot_instance

        print("🔍 檢查當前任務狀態...")
        is_running = global_update_logs_task.is_running()
        print(f"任務運行狀態: {is_running}")

        if not is_running:
            print("啟動全域日誌更新任務...")
            global_update_logs_task.start()
            print("✅ 任務已啟動")

            # 檢查機器人實例
            for bot_type in ["bot", "shopbot", "uibot"]:
                bot_instance = get_bot_instance(bot_type)
                print(f"{bot_type} 實例: {'存在' if bot_instance else '不存在'}")

            # 等待一段時間看看任務是否運行
            print("等待 30 秒檢查任務輸出...")
            await asyncio.sleep(30)

        else:
            print("任務已在運行")

    except Exception as e:
        print(f"❌ 啟動任務失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(start_log_task())