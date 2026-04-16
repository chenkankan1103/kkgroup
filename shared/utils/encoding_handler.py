# -*- coding: utf-8 -*-
"""
全局 UTF-8 編碼處理模塊
提供統一的編碼規範，確保所有日誌和輸出都正確處理 UTF-8 字符
"""

import sys
import os
import locale
import logging
from typing import Optional, Union

# ============================================================
# 1. 全局編碼初始化（應在所有導入之前調用）
# ============================================================

def initialize_encoding():
    """
    初始化全局 UTF-8 編碼設置
    應在程序最開始調用，在任何其他模塊導入之前
    """
    try:
        # 設置 locale 為 UTF-8
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except (locale.Error, ValueError):
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except (locale.Error, ValueError):
            pass  # 某些系統可能不支持
    
    # 強制配置 stdout/stderr 為 UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    # 環境變量保險
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['LC_ALL'] = 'C.UTF-8'
    os.environ['LANG'] = 'C.UTF-8'


# ============================================================
# 2. 字符串編碼安全轉換
# ============================================================

def safe_encode_for_log(text: Union[str, bytes]) -> str:
    """
    將任何文本安全地轉換為可列印的 UTF-8 字符串
    
    Args:
        text: 輸入文本（字符串或字節）
        
    Returns:
        str: 安全的 UTF-8 字符串，不會導致日誌亂碼
    """
    if isinstance(text, bytes):
        try:
            return text.decode('utf-8', errors='replace')
        except Exception:
            return text.decode('utf-8', errors='ignore')
    
    if isinstance(text, str):
        # 確保字符串編碼無誤
        try:
            # 嘗試重新編碼以清除潛在的編碼問題
            return text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        except Exception:
            return repr(text)
    
    # 其他類型轉換為字符串
    return str(text)


def sanitize_for_systemd(text: str) -> str:
    """
    將文本轉換為 systemd journalctl 安全的格式
    某些字符在 journalctl 中可能顯示為亂碼，此函數進行轉義
    
    Args:
        text: 輸入文本
        
    Returns:
        str: systemd 安全的文本
    """
    # 首先安全編碼
    text = safe_encode_for_log(text)
    
    # 移除或轉義可能導致問題的控制字符
    # 保留可列印的 UTF-8 字符
    allowed_chars = []
    for char in text:
        code = ord(char)
        # 保留可列印字符、空格、制表符、換行符
        if (32 <= code <= 126) or (code in [9, 10, 13]) or (code >= 128):
            allowed_chars.append(char)
        else:
            # 控制字符轉換為 [XX]
            allowed_chars.append(f'[{code:02X}]')
    
    return ''.join(allowed_chars)


# ============================================================
# 3. 日誌處理器
# ============================================================

class UTF8LogFormatter(logging.Formatter):
    """
    自定義日誌格式化器，確保所有日誌輸出都是正確的 UTF-8 編碼
    """
    
    def format(self, record):
        # 確保記錄中的所有文本都是安全的 UTF-8
        if isinstance(record.msg, str):
            record.msg = safe_encode_for_log(record.msg)
        
        # 處理日誌參數
        if record.args:
            if isinstance(record.args, dict):
                for key, value in record.args.items():
                    record.args[key] = safe_encode_for_log(value)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(safe_encode_for_log(arg) for arg in record.args)
        
        # 調用父類方法進行格式化
        result = super().format(record)
        
        # 最後一次確保輸出安全
        return safe_encode_for_log(result)


def setup_utf8_logging(name: Optional[str] = None, 
                       level: int = logging.INFO) -> logging.Logger:
    """
    配置 UTF-8 安全的日誌記錄器
    
    Args:
        name: 日誌記錄器名稱（通常為 __name__）
        level: 日誌級別
        
    Returns:
        logging.Logger: 配置好的日誌記錄器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 如果已經有處理器，先移除（避免重複）
    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
    
    # 創建 stdout 處理器（用於 systemd journalctl）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 使用自定義格式化器
    formatter = UTF8LogFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    return logger


def print_safe(message: str, end: str = '\n'):
    """
    安全的 print 替代方案，確保 UTF-8 正確輸出
    
    Args:
        message: 要輸出的消息
        end: 行尾字符（默認為換行）
    """
    safe_msg = safe_encode_for_log(message)
    try:
        print(safe_msg, end=end, flush=True)
    except UnicodeEncodeError:
        # 如果直接打印失敗，使用 ASCII-safe 版本
        print(sanitize_for_systemd(safe_msg), end=end, flush=True)


# ============================================================
# 4. 快速初始化函數（推薦用法）
# ============================================================

def init_all():
    """
    一次性初始化所有編碼設置
    應在程序最開始調用，通常在 if __name__ == '__main__': 之前
    
    Example:
        from shared.utils.encoding_handler import init_all
        init_all()  # 放在最開始
        # 其他代碼...
    """
    initialize_encoding()
