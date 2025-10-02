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

# ✅ 防洗頻機制：使用 deque 限制訊息數量
MAX_QUEUE_SIZE = 50  # 最多保留 50 條訊息
message_queue = deque(maxlen=MAX_QUEUE_SIZE)
lock = threading.Lock()

# ✅ 啟動時只發送一次的標記
startup_sent = False

def discord_sender():
    """背景執行緒：每 2 秒批次發送訊息"""
    while True:
        time.sleep(2)  # 改為 2 秒發送一次,降低頻率
        
        with lock:
            if not message_queue:
                continue
            
            # 一次最多取 15 行訊息 (Discord 單則訊息限制 2000 字元)
            batch = []
            total_length = 0
            
            while message_queue and len(batch) < 15:
                msg = message_queue.popleft()
                if total_length + len(msg) > 1900:  # 預留安全邊界
                    message_queue.appendleft(msg)  # 放回去
                    break
                batch.append(msg)
                total_length += len(msg) + 1  # +1 for newline
            
            if not batch:
                continue
                
            content = "\n".join(batch)
        
        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL, 
                json={"content": f"```\n{content}\n```"},  # 使用 code block 格式
                timeout=5
            )
            if response.status_code == 429:  # Rate limited
                print(f"[Discord] 被限流,等待中...", file=sys.stderr)
                time.sleep(5)
        except Exception as e:
            print(f"[Discord Error] {e}", file=sys.stderr)

# 啟動背景發送執行緒
thread = threading.Thread(target=discord_sender, daemon=True)
thread.start()

def discord_print(*args, **kwargs):
    """模擬 print(),加上 BOT 標籤,同時送出"""
    global startup_sent
    
    message = " ".join(map(str, args))
    local_output = f"[{BOT_NAME}] {message}"
    
    # ✅ 本地輸出（給 journalctl 看）
    sys.__stdout__.write(local_output + "\n")
    sys.__stdout__.flush()
    
    # ✅ 啟動訊息特殊處理
    if "準備啟動" in message and not startup_sent:
        with lock:
            message_queue.clear()  # 清空舊訊息
            message_queue.append(f"{'='*50}")
            message_queue.append(local_output)
            message_queue.append(f"{'='*50}")
        startup_sent = True
        return
    
    if "Bot 已啟動" in message:
        startup_sent = False  # 重置標記
    
    # ✅ 放進 queue 準備給 Discord
    with lock:
        message_queue.append(local_output)

# 覆蓋全域 print
print = discord_print
