import requests
import sys
import os
import threading
import time

# ✅ 填入你的 Webhook
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1423172112763584573/4esYiK_mCjLLw-ROffN2Bo7ZLHMtKAMka8FcUMfIyxGmZ657bVPjo61mGhJKaSDPcKqc"

# ✅ 自動偵測目前是執行哪一隻 bot
BOT_NAME = os.path.basename(sys.argv[0]).replace(".py", "").upper()

# ✅ 防洗頻機制：多條訊息會進 queue，再由背景執行緒批次發送
message_queue = []
lock = threading.Lock()

def discord_sender():
    """背景執行緒：每秒發一次訊息，避免洗版"""
    while True:
        time.sleep(1)
        with lock:
            if not message_queue:
                continue
            content = "\n".join(message_queue[:10])  # 一次最多發 10 行
            del message_queue[:10]

        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
        except Exception as e:
            print(f"[Discord Error] {e}", file=sys.stderr)

# 啟動背景發送執行緒
thread = threading.Thread(target=discord_sender, daemon=True)
thread.start()

def discord_print(*args, **kwargs):
    """模擬 print()，加上 BOT 標籤，同時送出"""
    message = " ".join(map(str, args))
    local_output = f"[{BOT_NAME}] {message}"

    # ✅ 本地輸出（給 journalctl 看）
    sys.__stdout__.write(local_output + "\n")
    sys.__stdout__.flush()

    # ✅ 放進 queue 準備給 Discord
    with lock:
        message_queue.append(local_output)

# 覆蓋全域 print
print = discord_print
