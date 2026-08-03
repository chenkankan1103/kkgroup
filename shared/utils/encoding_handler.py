# -*- coding: utf-8 -*-
"""
全局 UTF-8 編碼處理模塊
提供統一的編碼規範，確保所有日誌和輸出都正確處理 UTF-8 字符和台灣時間
"""

import sys
import os
import locale
import logging
import json
from typing import Optional, Union
from datetime import datetime
import pytz

# 台灣時區
TZ_TAIPEI = pytz.timezone('Asia/Taipei')

# ============================================================
# 1. 全局編碼初始化（應在所有導入之前調用）
# ============================================================

def initialize_encoding():
    """
    初始化全局 UTF-8 編碼設置和台灣時區
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
        sys.stdout.reconfigure(encoding='utf-8', errors='surrogateescape')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='surrogateescape')
    
    # 環境變量保險
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['LC_ALL'] = 'C.UTF-8'
    os.environ['LANG'] = 'C.UTF-8'
    os.environ['TZ'] = 'Asia/Taipei'
    
    # 嘗試在系統層級設置時區（Linux）
    try:
        import time
        os.environ['TZ'] = 'Asia/Taipei'
        time.tzset()
    except (AttributeError, OSError):
        pass  # Windows 或其他不支持的系統


# ============================================================
# 2. 字符串編碼安全轉換
# ============================================================

def safe_encode_for_log(text: Union[str, bytes]) -> str:
    """
    將任何文本安全地轉換為可列印的 UTF-8 字符串
    完全保留中文字符，不進行任何轉碼
    
    Args:
        text: 輸入文本（字符串或字節）
        
    Returns:
        str: 安全的 UTF-8 字符串，包含完整的中文字符
    """
    if isinstance(text, bytes):
        try:
            # 嘗試以 UTF-8 解碼，失敗時用 surrogateescape 保存位元資訊
            return text.decode('utf-8', errors='surrogateescape')
        except Exception:
            try:
                return text.decode('utf-8', errors='replace')
            except Exception:
                return repr(text)
    
    if isinstance(text, str):
        # 直接返回，不進行任何轉碼
        # 完全信任源代碼中的 UTF-8 編碼
        return text
    
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

class TaiwanTimeFormatter(logging.Formatter):
    """
    自定義日誌格式化器，支持台灣時區和 UTF-8 編碼
    """
    
    def formatTime(self, record, datefmt=None):
        """
        使用台灣時區格式化時間
        """
        dt = datetime.now(TZ_TAIPEI)
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            t = dt.timetuple()
            s = dt.strftime('%Y-%m-%d %H:%M:%S')
        return s
    
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
    配置 UTF-8 安全的日誌記錄器，支持中文和台灣時間
    
    Args:
        name: 日誌記錄器名稱（通常為 __name__）
        level: 日誌級別
        
    Returns:
        logging.Logger: 配置好的日誌記錄器
        
    Example:
        logger = setup_utf8_logging(__name__, logging.INFO)
        logger.info("這是中文訊息 🎉")  # 完全支援中文和 emoji
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
    
    # 使用台灣時間格式化器
    formatter = TaiwanTimeFormatter(
        '[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.propagate = True  # 允許子 logger 傳播到此 handler（修復 anime_tracker 等模組日誌不顯示的問題）
    
    return logger


def print_safe(message: str, end: str = '\n'):
    """
    安全的 print 替代方案，確保 UTF-8 正確輸出和中文字符完整
    
    Args:
        message: 要輸出的消息
        end: 行尾字符（默認為換行）
        
    Example:
        print_safe("這是中文訊息 ✅")  # 完全支持中文
    """
    safe_msg = safe_encode_for_log(message)
    try:
        print(safe_msg, end=end, flush=True)
    except UnicodeEncodeError:
        # 如果直接打印失敗，嘗試其他編碼
        try:
            sys.stdout.buffer.write(safe_msg.encode('utf-8', errors='surrogateescape'))
            sys.stdout.buffer.write(end.encode('utf-8', errors='surrogateescape'))
            sys.stdout.buffer.flush()
        except Exception as e:
            print(f"[ERROR] 無法輸出: {e}", file=sys.stderr, flush=True)


def json_dumps_console_safe(data, indent: Optional[int] = 2) -> str:
    """
    依照目前 stdout 編碼決定 JSON 是否保留原始 Unicode。
    在 gcloud/plink/PowerShell 等非 UTF-8 終端中，自動退回 ASCII escape，避免中文亂碼。
    """
    encoding = (getattr(sys.stdout, 'encoding', None) or '').lower()
    keep_unicode = 'utf' in encoding
    return json.dumps(data, ensure_ascii=not keep_unicode, indent=indent, default=str)


def print_json_safe(data, indent: Optional[int] = 2, end: str = '\n'):
    """安全輸出 JSON 到終端，避免非 UTF-8 終端出現亂碼。"""
    print_safe(json_dumps_console_safe(data, indent=indent), end=end)


def get_taiwan_time(fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    取得台灣時間
    
    Args:
        fmt: 時間格式 (默認: '2026-04-27 15:30:45')
        
    Returns:
        str: 格式化的台灣時間
        
    Example:
        now = get_taiwan_time()  # '2026-04-27 15:30:45'
        now_full = get_taiwan_time('%Y年%m月%d日 %H:%M:%S')  # '2026年04月27日 15:30:45'
    """
    return datetime.now(TZ_TAIPEI).strftime(fmt)


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
