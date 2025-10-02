import requests
import sys
import os
import threading
import time
from collections import deque

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
STARTUP_WAIT_TIME = 10  # 啟動後等待 10 秒


def send_startup_messages():
    """10 秒後統一發送啟動訊息"""
    global startup_mode, startup_buffer
    
    with lock:
        startup_mode = False
        
        if not startup_buffer:
            return
        
        # 組合所有啟動訊息
        header = f"{'='*50}\n[{BOT_NAME}] 啟動訊息\n{'='*50}"
        content = "\n".join(startup_buffer)
        footer = f"{'='*50}"
        
        full_message = f"{header}\n{content}\n{footer}"
        
        # 直接發送（不經過 queue）
        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": f"```\n{full_message}\n```"},
                timeout=5
            )
            if response.status_code != 204:
                print(f"[Discord] 發送失敗: {response.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"[Discord Error] {e}", file=sys.stderr)
        
        startup_buffer.clear()


def discord_sender():
    """背景執行緒：每 2 秒批次發送訊息"""
    while True:
        time.sleep(2)
        
        # 啟動模式下不發送
        if startup_mode:
            continue
        
        with lock:
            if not message_queue:
                continue
            
            # 一次最多取訊息（限制在 1900 字元內）
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
            
            content = "\n".join(batch)
        
        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": f"```\n{content}\n```"},
                timeout=5
            )
            if response.status_code == 429:
                print(f"[Discord] 被限流,等待中...", file=sys.stderr)
                time.sleep(5)
        except Exception as e:
            print(f"[Discord Error] {e}", file=sys.stderr)


# 啟動背景發送執行緒
thread = threading.Thread(target=discord_sender, daemon=True)
thread.start()

# 啟動計時器（10 秒後發送啟動訊息）
startup_timer = threading.Timer(STARTUP_WAIT_TIME, send_startup_messages)
startup_timer.start()


def discord_print(*args, **kwargs):
    """模擬 print()，加上 BOT 標籤，同時送出"""
    message = " ".join(map(str, args))
    local_output = f"[{BOT_NAME}] {message}"
    
    # ✅ 本地輸出（給 journalctl 看）
    sys.__stdout__.write(local_output + "\n")
    sys.__stdout__.flush()
    
    # ✅ 啟動模式：收集訊息到 buffer
    with lock:
        if startup_mode:
            startup_buffer.append(local_output)
        else:
            # 正常模式：放進 queue
            message_queue.append(local_output)


# 覆蓋全域 print
print = discord_print
