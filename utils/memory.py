import json
import time
import os
import logging

logger = logging.getLogger(__name__)

# JSON 檔案路徑
MEMORY_FILE = 'memory.json'

# 確保檔案存在
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, 'w') as f:
        json.dump({}, f)

# 讀取 JSON 記憶資料 - 增強版，處理損壞的檔案
def read_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
            # 如果檔案為空，返回空字典
            if not content:
                logger.warning("memory.json 為空，返回空字典")
                return {}
            
            # 嘗試解析 JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失敗: {e}")
                logger.warning(f"嘗試修復損壞的 JSON 檔案")
                
                # 嘗試提取第一個完整的 JSON 對象
                start_idx = content.find('{')
                if start_idx != -1:
                    brace_count = 0
                    for i in range(start_idx, len(content)):
                        if content[i] == '{':
                            brace_count += 1
                        elif content[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_str = content[start_idx:i+1]
                                try:
                                    data = json.loads(json_str)
                                    logger.warning("成功修復並提取 JSON 數據")
                                    # 保存修復後的數據
                                    save_memory(data)
                                    return data
                                except:
                                    pass
                
                logger.error("無法修復 JSON 檔案，返回空字典")
                return {}
    except Exception as e:
        logger.error(f"讀取 memory.json 時出錯: {e}")
        return {}

# 儲存記憶
def save_memory(data):
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("記憶已保存")
    except Exception as e:
        logger.error(f"保存記憶時出錯: {e}")

# 儲存訊息
def add_to_history(user_id: int, message: str):
    try:
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
    except Exception as e:
        logger.error(f"添加歷史訊息時出錯: {e}")

# 獲取歷史訊息
def get_history(user_id: int) -> list[str]:
    try:
        data = read_memory()
        user_id = str(user_id)
        
        if user_id not in data:
            return []
        
        return [msg["message"] for msg in data[user_id]]
    except Exception as e:
        logger.error(f"獲取歷史訊息時出錯: {e}")
        return []
