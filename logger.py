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
    """帶重試機制的發送函數（自動截斷超長內容）"""
    color = "ff0000" if is_error else "0000ff"  # 紅色=錯誤, 藍色=正常
    
    # ⚠️ Discord Embed description 最多 2048 字符，留 100 字符安全邊界
    if len(content) > 1950:
        # 超長內容分段發送
        lines = content.split('\n')
        current = []
        current_len = 0
        
        for line in lines:
            if current_len + len(line) + 1 > 1900:
                if current:
                    # 發送當前段
                    segment = '\n'.join(current) + "\n..."
                    _send_embed(segment, color, is_error, max_retries)
                    current = [line]
                    current_len = len(line)
                else:
                    # 單行超長，截斷
                    _send_embed(line[:1900] + "...", color, is_error, max_retries)
            else:
                current.append(line)
                current_len += len(line) + 1
        
        # 發送最後一段
        if current:
            _send_embed('\n'.join(current), color, is_error, max_retries)
        return True
    else:
        return _send_embed(content, color, is_error, max_retries)

def _send_embed(content, color, is_error, max_retries=3):
    """實際發送 Embed 的函數"""
    for attempt in range(max_retries):
        try:
            payload = {
                "embeds": [{
                    "title": f"❌ {BOT_NAME}" if is_error else f"ℹ️ {BOT_NAME}",
                    "description": content,
                    "color": int(color, 16),
                    "timestamp": datetime.now().isoformat()
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
                retry_after = float(response.headers.get('Retry-After', 1))
                time.sleep(min(retry_after, 5))
            else:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return False

def send_startup_messages():
    """統一發送啟動訊息 (簡潔格式)"""
    global startup_mode, startup_buffer
    
    with lock:
        startup_mode = False
        
        if not startup_buffer:
            print(f"[Discord] {BOT_NAME} 沒有啟動訊息", file=sys.__stderr__)
            return
        
        buffer_copy = startup_buffer.copy()
        startup_buffer.clear()
    
    # 簡潔格式：只發送關鍵訊息
    # 分離錯誤和正常訊息
    errors = [line for line in buffer_copy if "❌" in line or "❌" in line]
    success = [line for line in buffer_copy if "✅" in line]
    normal = [line for line in buffer_copy if line not in errors and line not in success]
    
    # 構建簡潔訊息
    message_parts = []
    
    # 1. 錯誤（最重要）
    if errors:
        message_parts.append("❌ **錯誤信息：**")
        message_parts.extend(errors[-5:])  # 只顯示最後 5 個錯誤
        if len(errors) > 5:
            message_parts.append(f"... 及其他 {len(errors) - 5} 個錯誤")
    
    # 2. 成功訊息
    if success:
        message_parts.append("")
        message_parts.append("✅ **已載入：**")
        # 只顯示關鍵成功訊息（模組數量等）
        key_success = [s for s in success if "擴展" in s or "指令" in s or "已就緒" in s]
        message_parts.extend(key_success[:3])
    
    # 3. 其他訊息（統計信息）
    if normal:
        message_parts.append("")
        message_parts.append("📊 **統計：**")
        # 只顯示統計行
        stat_lines = [n for n in normal if "統計" in n or "Slash" in n or "前綴" in n]
        message_parts.extend(stat_lines)
    
    final_message = "\n".join(message_parts)
    
    # 發送簡潔訊息
    if final_message.strip():
        send_with_retry(final_message)

def discord_sender():
    """背景執行緒:發送訊息 (錯誤優先, 正常訊息次之)"""
    while True:
        time.sleep(2)  # 每 2 秒檢查一次
        
        # 啟動模式下不發送
        if startup_mode:
            continue
        
        error_msg = None
        content = None
        
        # 只在取出資料時上鎖，避免在持鎖期間做網路請求
        with lock:
            # 優先處理錯誤隊列（更重要）
            if error_queue:
                error_msg = error_queue.popleft()
            elif message_queue:
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
                
                if batch:
                    content = "```\n" + "\n".join(batch) + "\n```"
        
        # 鎖外發送，避免阻塞其他執行緒
        if error_msg:
            send_with_retry(error_msg, is_error=True)
        elif content:
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
    
    # 簡化輸出格式：只在關鍵信息前加標籤
    if any(kw in message for kw in ["❌", "✅", "🤖", "⚡", "📊", "==="]):
        local_output = f"[{BOT_NAME}] {message}"
    else:
        # 普通訊息只輸出不加標籤
        local_output = message
    
    # 本地輸出
    sys.__stdout__.write(local_output + "\n")
    sys.__stdout__.flush()
    
    # 啟動模式：只收集錯誤和關鍵訊息
    # ⚠️ 使用 non-blocking 鎖以避免死鎖異步事件循環
    acquired = lock.acquire(blocking=False)
    try:
        if acquired:
            if startup_mode:
                # 只收集有實際信息的行（跳過純分隔線）
                if message.strip() and not message.startswith("="):
                    startup_buffer.append(message)
            else:
                # 正常模式:放進 queue
                message_queue.append(local_output)
    finally:
        if acquired:
            lock.release()

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
