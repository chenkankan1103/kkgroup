import requests
import sys
import os
import threading
import time
import logging
import traceback
import hashlib
from collections import deque
from datetime import datetime, timedelta
import random

# ✅ 填入你的 Webhook
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1423172112763584573/4esYiK_mCjLLw-ROffN2Bo7ZLHMtKAMka8FcUMfIyxGmZ657bVPjo61mGhJKaSDPcKqc"

# ✅ 自動偵測目前是執行哪一隻 bot
BOT_NAME = os.path.basename(sys.argv[0]).replace(".py", "").upper()

# ✅ 根據不同 bot 設定不同的啟動延遲
BOT_DELAYS = {
    "BOT": 5,
    "SHOPBOT": 8,
    "UIBOT": 11
}
STARTUP_WAIT_TIME = BOT_DELAYS.get(BOT_NAME, 5 + random.uniform(0, 5))

# ✅ 防洗頻機制
MAX_QUEUE_SIZE = 100
message_queue = deque(maxlen=MAX_QUEUE_SIZE)
error_queue = deque(maxlen=50)  # 錯誤隊列（優先級更高）
lock = threading.Lock()

# ✅ 錯誤去重機制（防止同一個錯誤狂轟）
error_dedup = {}  # {error_hash: last_timestamp}
ERROR_DEDUP_WINDOW = 60  # 同一個錯誤 60 秒內只報一次

# ✅ 啟動緩衝機制
startup_mode = True
startup_buffer = []
startup_timer = None

def hash_error(error_msg):
    """生成錯誤的哈希值用於去重"""
    # 只取錯誤的主要部分（不包含時間戳等變化的信息）
    main_part = error_msg.split('\n')[0]
    return hashlib.md5(main_part.encode()).hexdigest()

def should_report_error(error_hash):
    """檢查是否應該報告這個錯誤（去重）"""
    global error_dedup
    
    now = time.time()
    
    # 清理過期的記錄
    expired_keys = [k for k, v in error_dedup.items() if now - v > ERROR_DEDUP_WINDOW]
    for k in expired_keys:
        del error_dedup[k]
    
    # 檢查是否在窗口內已報告
    if error_hash in error_dedup:
        return False
    
    error_dedup[error_hash] = now
    return True

def send_with_retry(content, max_retries=3, is_error=False):
    """帶重試機制的發送函數"""
    color = "ff0000" if is_error else "0000ff"  # 紅色=錯誤, 藍色=正常
    
    # ⚠️ 重要：Discord Embed description 最多 2048 字符
    # 留 100 字符的安全邊界用於時間戳等其他信息
    max_content_length = 1900
    
    if len(content) > max_content_length:
        content = content[:max_content_length] + "\n...(內容已截斷)"
    
    for attempt in range(max_retries):
        try:
            # 使用 Embed 格式以區分錯誤和正常訊息
            payload = {
                "embeds": [{
                    "title": f"❌ {BOT_NAME} 錯誤" if is_error else f"ℹ️ {BOT_NAME} 訊息",
                    "description": content,
                    "color": int(color, 16),
                    "timestamp": datetime.now().isoformat(),
                    "footer": {"text": f"時間戳: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                }]
            }
            
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 204:
                return True
            elif response.status_code == 429:
                # 被限流,等待後重試
                retry_after = float(response.headers.get('Retry-After', 3))
                print(f"[Discord] 被限流,等待 {retry_after} 秒...", file=sys.__stderr__)
                time.sleep(retry_after)
            else:
                print(f"[Discord] 發送失敗: {response.status_code}", file=sys.__stderr__)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指數退避: 1秒, 2秒, 4秒
        except Exception as e:
            print(f"[Discord Error] 嘗試 {attempt + 1}/{max_retries}: {e}", file=sys.__stderr__)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return False

def send_startup_messages():
    """統一發送啟動訊息 (支援分段發送)"""
    global startup_mode, startup_buffer
    
    with lock:
        startup_mode = False
        
        if not startup_buffer:
            print(f"[Discord] {BOT_NAME} 沒有啟動訊息", file=sys.__stderr__)
            return
        
        buffer_copy = startup_buffer.copy()
        startup_buffer.clear()
    
    # 分段發送邏輯
    header = f"{'='*50}\n[{BOT_NAME}] 啟動訊息\n{'='*50}"
    footer = f"{'='*50}"
    
    # 計算每段可用空間 (2000 - code block - header/footer - 安全邊界)
    max_content_length = 1700
    
    # 將內容分段
    segments = []
    current_segment = []
    current_length = 0
    
    for line in buffer_copy:
        line_length = len(line) + 1  # +1 for newline
        
        if current_length + line_length > max_content_length:
            # 當前段已滿,保存並開始新段
            segments.append("\n".join(current_segment))
            current_segment = [line]
            current_length = line_length
        else:
            current_segment.append(line)
            current_length += line_length
    
    # 添加最後一段
    if current_segment:
        segments.append("\n".join(current_segment))
    
    # 發送所有段落
    total_segments = len(segments)
    
    for i, segment in enumerate(segments, 1):
        if total_segments > 1:
            part_header = f"{header} (第 {i}/{total_segments} 部分)"
        else:
            part_header = header
        
        message = f"```\n{part_header}\n{segment}\n{footer}\n```"
        
        success = send_with_retry(message)
        
        # 段落之間間隔 1 秒,避免限流
        if i < total_segments:
            time.sleep(1)

def discord_sender():
    """背景執行緒:發送訊息 (錯誤優先, 正常訊息次之)"""
    while True:
        time.sleep(2)  # 每 2 秒檢查一次
        
        # 啟動模式下不發送
        if startup_mode:
            continue
        
        with lock:
            # 優先處理錯誤隊列（更重要）
            if error_queue:
                error_msg = error_queue.popleft()
                send_with_retry(error_msg, is_error=True)
                continue
            
            # 然後處理普通訊息隊列
            if not message_queue:
                continue
            
            # 一次最多取 20 條訊息(限制在 1500 字元內)
            batch = []
            total_length = 0
            
            while message_queue and len(batch) < 20:
                msg = message_queue.popleft()
                if total_length + len(msg) > 1500:
                    message_queue.appendleft(msg)
                    break
                batch.append(msg)
                total_length += len(msg) + 1
            
            if not batch:
                continue
            
            content = "```\n" + "\n".join(batch) + "\n```"
        
        # 使用帶重試的發送
        send_with_retry(content, is_error=False)

# 啟動背景發送執行緒
thread = threading.Thread(target=discord_sender, daemon=True)
thread.start()

# 啟動計時器(不同 bot 不同延遲)
print(f"[Discord] {BOT_NAME} 將在 {STARTUP_WAIT_TIME:.1f} 秒後發送啟動訊息", file=sys.__stderr__)
startup_timer = threading.Timer(STARTUP_WAIT_TIME, send_startup_messages)
startup_timer.start()

def discord_print(*args, **kwargs):
    """模擬 print(),加上 BOT 標籤,同時送出"""
    message = " ".join(map(str, args))
    local_output = f"[{BOT_NAME}] {message}"
    
    # ✅ 本地輸出(給 journalctl 看)
    sys.__stdout__.write(local_output + "\n")
    sys.__stdout__.flush()
    
    # ✅ 啟動模式:收集訊息到 buffer
    with lock:
        if startup_mode:
            startup_buffer.append(local_output)
        else:
            # 正常模式:放進 queue
            message_queue.append(local_output)

# 覆蓋全域 print
print = discord_print

def handle_exception(exc_type, exc_value, exc_traceback):
    """全局異常處理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        # KeyboardInterrupt 不報告
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # 格式化異常信息
    error_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    error_msg = "".join(error_lines)
    
    # 生成哈希用於去重
    error_hash = hash_error(error_msg)
    
    # 檢查是否應該報告
    if should_report_error(error_hash):
        # 截斷長錯誤訊息（Discord 有 2000 字符限制）
        if len(error_msg) > 1800:
            error_msg = error_msg[:1800] + "\n... (訊息已截斷)"
        
        with lock:
            error_queue.append(f"```\n❌ {BOT_NAME} 捕捉到異常:\n{error_msg}\n```")
    
    # 仍然打印到標準錯誤
    sys.__stderr__.write(f"[{BOT_NAME}] 未處理的異常:\n{error_msg}\n")
    sys.__stderr__.flush()

# 設置全局異常處理
sys.excepthook = handle_exception

class DiscordLoggingHandler(logging.Handler):
    """自定義 logging handler，將日誌發送到 Discord"""
    
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            # 只報告 ERROR 和以上級別
            log_msg = self.format(record)
            
            # 生成哈希用於去重
            error_hash = hash_error(log_msg)
            
            if should_report_error(error_hash):
                with lock:
                    error_queue.append(f"```\n🔴 [{record.levelname}] {log_msg}\n```")

# 配置 logging
logging.basicConfig(
    level=logging.WARNING,
    format='[%(name)s] %(levelname)s: %(message)s'
)

# 添加 Discord handler
discord_handler = DiscordLoggingHandler()
discord_handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
logging.getLogger().addHandler(discord_handler)
