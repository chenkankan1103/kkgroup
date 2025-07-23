import os
from dotenv import load_dotenv

load_dotenv()

# 資料庫配置
DB_PATH = os.getenv("DB_PATH", "user_data.db")

# 角色ID配置
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID", 0))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 0))
VIP_ROLE_ID = int(os.getenv("VIP_ROLE_ID", 0))
RAINBOW_ROLE_ID = int(os.getenv("RAINBOW_ROLE_ID", 0))

# 商店配置
try:
    from shop_config import EQUIPMENT_SHOP, ROLE_SHOP
except ImportError:
    # 預設商店配置
    EQUIPMENT_SHOP = {}
    ROLE_SHOP = {
        "七彩披風": {"price": 50, "role_id": RAINBOW_ROLE_ID, "duration": 86400},
        "進階組員": {"price": 75, "role_id": VIP_ROLE_ID, "duration": 604800},
    }

# 遊戲配置
SLOT_MACHINE_CONFIG = {
    "icons": ["🍒", "🍋", "🍊", "🍉", "🍇", "🔔", "⭐", "💎"],
    "weights": {
        "💎": 3,
        "⭐": 6,
        "🔔": 12,
        "🍋": 15,
        "🍒": 18,
        "🍊": 20,
        "🍉": 20,
        "🍇": 26
    },
    "multipliers": {
        "💎": 10,
        "⭐": 7,
        "🔔": 5,
        "🍋": 3,
        "🍒": 2
    }
}