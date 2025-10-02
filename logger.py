import requests
import sys
import os
import threading
import time
from collections import deque
import random

# ✅ 填入你的 Webhook
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1423172112763584573/4esYiK_mCjLLw-ROffN2Bo7ZLHMtKAMka8FcUMfIyxGmZ657bVPjo61mGhJKaSDPcKqc"

# ✅ 自動偵測目前是執行哪一隻 bot
BOT_NAME = os.path.basename(sys.argv[0]).replace(".py", "").upper()

# ✅ 防洗頻機制
MAX_QUEUE_SIZE = 50
message_queue = deque(maxlen=MAX_QUEUE_SIZE)
lock = threading.Lock()

# ✅ 啟動緩衝機制
startup_mode = True
startup_buffer = []
startup_timer = None

# ✅ 給每支 bot 不同的啟動時間,避免衝突
BASE_STARTUP_WAIT = 8
STARTUP_WAIT_TIME = BASE_STARTUP_WAIT + random.uniform(0, 4)  # 8-12 秒隨機

def send_with_retry(content, max_retries=3):
    """帶重試機制的發送函數"""
    for attempt in range(max_retries):
        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": content},
                timeout=10  # 增加 timeout
            )
            
            if response.status_code == 204:
                return True
            elif response.status_code == 429:
                # 被限流,等待後重試
                retry_after = float(response.headers.get('Retry-After', 2))
                print(f"[Discord] 被限流,等待 {retry_after} 秒...", file=sys.__stderr__)
                time.sleep(retry_after)
            else:
                print(f"[Discord] 發送失敗: {response.status_code}", file=sys.__stderr__)
                time.sleep(1)
        except Exception as e:
            print(f"[Discord Error] 嘗試 {attempt + 1}/{max_retries}: {e}", file=sys.__stderr__)
            time.sleep(2)
    
    return False

def send_startup_messages():
    """統一發送啟動訊息"""
    global startup_mode, startup_buffer
    
    with lock:
        startup_mode = False
        
        if not startup_buffer:
            print(f"[Discord] {BOT_NAME} 沒有啟動訊息", file=sys.__stderr__)
            return
        
        # 組合所有啟動訊息
        header = f"{'='*50}\n[{BOT_NAME}] 啟動訊息 (延遲 {STARTUP_WAIT_TIME:.1f}秒)\n{'='*50}"
        content = "\n".join(startup_buffer)
        footer = f"{'='*50}"
        
        full_message = f"```\n{header}\n{content}\n{footer}\n```"
        
        # 複製 buffer 後清空
        buffer_copy = startup_buffer.copy()
        startup_buffer.clear()
    
    # 在鎖外發送,避免阻塞
    print(f"[Discord] 正在發送 {BOT_NAME} 的啟動訊息...", file=sys.__stderr__)
    success = send_with_retry(full_message)
    
    if success:
        print(f"[Discord] {BOT_NAME} 啟動訊息發送成功", file=sys.__stderr__)
    else:
        print(f"[Discord] {BOT_NAME} 啟動訊息發送失敗", file=sys.__stderr__)

def discord_sender():
    """背景執行緒:每 2 秒批次發送訊息"""
    while True:
        time.sleep(2)
        
        # 啟動模式下不發送
        if startup_mode:
            continue
        
        with lock:
            if not message_queue:
                continue
            
            # 一次最多取訊息(限制在 1900 字元內)
            batch = []
            total_length = 0
            
            while message_queue and len(batch) < 100:
                msg = message_queue.popleft()
                if total_length + len(msg) > 1900:
                    message_queue.appendleft(msg)
                    break
                batch.append(msg)
                total_length += len(msg) + 1
            
            if not batch:
                continue
            
            content = f"```\n" + "\n".join(batch) + "\n```"
        
        # 使用帶重試的發送
        send_with_retry(content)

# 啟動背景發送執行緒
thread = threading.Thread(target=discord_sender, daemon=True)
thread.start()

# 啟動計時器(隨機延遲後發送啟動訊息)
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
