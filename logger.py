import sys
import os
import logging
import traceback
from datetime import datetime
import builtins

# ✅ 自動偵測目前是執行哪一隻 bot
BOT_NAME = os.path.basename(sys.argv[0]).replace(".py", "").upper()

# 保持標準 print 函數 (原本會被覆蓋用來發送到 Discord，現在只用標準 print)
print = builtins.print

def handle_exception(exc_type, exc_value, exc_traceback):
    """全局異常處理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        # KeyboardInterrupt 不報告
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # 格式化異常信息
    error_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    error_msg = "".join(error_lines)
    
    # 打印到標準錯誤
    sys.__stderr__.write(f"[{BOT_NAME}] 未處理的異常:\n{error_msg}\n")
    sys.__stderr__.flush()

# 設置全局異常處理
sys.excepthook = handle_exception

# 配置 logging
logging.basicConfig(
    level=logging.WARNING,
    format='[%(name)s] %(levelname)s: %(message)s'
)

# 備註：Discord webhook 發送已移至 webhook_logger.py
# webhook_logger.py 處理所有 Discord 統一消息發送
