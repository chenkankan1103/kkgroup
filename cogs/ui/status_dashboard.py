"""
狀態面板 - 簡化版日誌記錄工具
用於統一記錄UI操作和系統事件
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# 設定 logger
logger = logging.getLogger("status_dashboard")
logger.setLevel(logging.INFO)

# 如果沒有處理器，添加一個簡單的控制台處理器
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def add_log(module: str, message: str) -> None:
    """
    添加日誌記錄

    Args:
        module: 模組名稱 (例如: "ui", "bot", "shop")
        message: 日誌訊息
    """
    # 使用台灣時區
    tw_tz = ZoneInfo("Asia/Taipei")
    timestamp = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")

    # 記錄到 logger
    logger.info(f"[{module}] {message}")

    # 同時輸出到控制台（保持向後相容）
    print(f"[{module}] {message}")

# 為了向後相容，也提供一個別名函數
def log_ui(message: str) -> None:
    """UI 專用日誌記錄"""
    add_log("ui", message)

def log_bot(message: str) -> None:
    """Bot 專用日誌記錄"""
    add_log("bot", message)

def log_shop(message: str) -> None:
    """商店專用日誌記錄"""
    add_log("shop", message)