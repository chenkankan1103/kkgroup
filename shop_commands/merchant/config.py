import os
from dotenv import load_dotenv, find_dotenv

# 修正：明確指定 .env 檔案路徑
# 從當前檔案位置往上找到 kkgroup 資料夾中的 .env
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '..', '.env')

# 如果找不到，使用 find_dotenv() 作為備用方案
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv(find_dotenv())

# 資料庫配置
DB_PATH = os.getenv("DB_PATH", "user_data.db")

# 角色ID配置 - 添加調試資訊
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID", 0))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 0))
VIP_ROLE_ID = int(os.getenv("VIP_ROLE_ID", 0))
RAINBOW_ROLE_ID = int(os.getenv("RAINBOW_ROLE_ID", 0))

# 調試：印出載入的角色ID（可選）
print(f"[Config] RAINBOW_ROLE_ID: {RAINBOW_ROLE_ID}")
print(f"[Config] VIP_ROLE_ID: {VIP_ROLE_ID}")
print(f"[Config] MUTE_ROLE_ID: {MUTE_ROLE_ID}")
print(f"[Config] MEMBER_ROLE_ID: {MEMBER_ROLE_ID}")

# 商店配置
try:
    from shop_config import EQUIPMENT_SHOP, ROLE_SHOP
    print("[Config] 成功載入 shop_config")
except ImportError:
    print("[Config] shop_config 不存在，使用預設配置")
    # 預設商店配置
    EQUIPMENT_SHOP = {}
    ROLE_SHOP = {
        "七彩披風": {"price": 50, "role_id": RAINBOW_ROLE_ID, "duration": 86400},
        "進階組員": {"price": 75, "role_id": VIP_ROLE_ID, "duration": 604800},
    }

# 確保角色ID不為0
if RAINBOW_ROLE_ID == 0 or VIP_ROLE_ID == 0:
    print(f"[警告] 角色ID設定可能有問題:")
    print(f"  RAINBOW_ROLE_ID: {RAINBOW_ROLE_ID}")
    print(f"  VIP_ROLE_ID: {VIP_ROLE_ID}")
    print(f"  請檢查 .env 檔案是否正確載入")

# 遊戲配置
SLOT_MACHINE_CONFIG = {
    "weights": {
        "💎": 2,    # 鑽石 - 最稀有
        "⭐": 6,    # 星星 - 稀有，單個有保本效果
        "🔔": 8,    # 鈴鐺 - 中等稀有
        "🍋": 12,   # 檸檬 - 常見
        "🍒": 15,   # 櫻桃 - 常見
        "🍊": 18,   # 橘子 - 很常見
        "🍉": 18,   # 西瓜 - 很常見
        "🍇": 21,   # 葡萄 - 最常見
    },
    "multipliers": {
        "💎": 15,   # 💎💎💎 = 15倍 (淨贏14倍)
        "⭐": 8,    # ⭐⭐⭐ = 8倍 (淨贏7倍)
        "🔔": 5,    # 🔔🔔🔔 = 5倍 (淨贏4倍)
        "🍋": 3,    # 🍋🍋🍋 = 3倍 (淨贏2倍)
        "🍒": 2.5,  # 🍒🍒🍒 = 2.5倍 (淨贏1.5倍)
        # 🍊🍉🍇 三連都是1.5倍在邏輯中處理
    }
}
