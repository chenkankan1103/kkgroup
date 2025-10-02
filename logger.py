# logger.py
import requests
import sys

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1423172112763584573/4esYiK_mCjLLw-ROffN2Bo7ZLHMtKAMka8FcUMfIyxGmZ657bVPjo61mGhJKaSDPcKqc"

def discord_print(*args, **kwargs):
    message = " ".join(map(str, args))
    print(message, **kwargs)          # 本地輸出（systemd journalctl 可看到）
    sys.stdout.flush()

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
    except Exception as e:
        print(f"[Discord Error] {e}", file=sys.stderr)

# 覆蓋全域 print
print = discord_print
