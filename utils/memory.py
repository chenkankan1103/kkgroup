# utils/memory.py
import json
import time
import os

# JSON 檔案路徑
MEMORY_FILE = 'memory.json'

# 確保檔案存在
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, 'w') as f:
        json.dump({}, f)

# 讀取 JSON 記憶資料
def read_memory():
    with open(MEMORY_FILE, 'r') as f:
        return json.load(f)

# 儲存記憶
def save_memory(data):
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f)

# 儲存訊息
def add_to_history(user_id: int, message: str):
    data = read_memory()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = []
    
    # 新增訊息
    data[user_id].append({"timestamp": time.time(), "message": message})

    # 自動清除超過24小時的訊息
    data[user_id] = [
        msg for msg in data[user_id] if time.time() - msg["timestamp"] < 86400
    ]
    
    save_memory(data)

# 獲取歷史訊息
def get_history(user_id: int) -> list[str]:
    data = read_memory()
    user_id = str(user_id)
    if user_id not in data:
        return []
    
    return [msg["message"] for msg in data[user_id]]
