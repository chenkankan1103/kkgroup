#!/usr/bin/env python3
"""
手動添加測試日誌並檢查更新
"""

import os
import sys
import json
from datetime import datetime

# 添加當前目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接操作日誌文件
logs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard_logs.json')

def add_test_log():
    """添加測試日誌"""
    try:
        # 讀取現有日誌
        if os.path.exists(logs_file):
            with open(logs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"bot": [], "shopbot": [], "uibot": []}

        # 添加新日誌
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        test_log = f"{timestamp} 手動測試日誌 - 系統檢查"

        for bot_type in ["bot", "shopbot", "uibot"]:
            if bot_type not in data:
                data[bot_type] = []
            data[bot_type].append(test_log)
            # 只保留最近10條
            data[bot_type] = data[bot_type][-10:]

        # 保存
        with open(logs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 已添加測試日誌: {test_log}")
        return True

    except Exception as e:
        print(f"❌ 添加日誌失敗: {e}")
        return False

if __name__ == "__main__":
    success = add_test_log()
    if success:
        print("請檢查 Discord 頻道是否更新了日誌")