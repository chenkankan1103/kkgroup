import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())  # 自動往上層目錄找 .env

# 資料庫配置
DB_PATH = os.getenv("DB_PATH", "user_data.db")

# 角色ID配置
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID", 1363507802609422357))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 1133462727742996582))
VIP_ROLE_ID = int(os.getenv("VIP_ROLE_ID", 1369561759777689610))
RAINBOW_ROLE_ID = int(os.getenv("RAINBOW_ROLE_ID", 1369373373498658877))

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
# config.py 或 shop_config.py 中的拉霸機配置

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

# 期望值計算說明:
# 基於權重計算，大約的機率分布：
# - 三連大獎 (💎/⭐/🔔): 極低機率，高回報
# - 三連小獎 (🍋/🍒/🍊/🍉/🍇): 低機率，中等回報  
# - 兩個相同: 中等機率，小回報 (+10%)
# - 單星星: 中等機率，保本 (0%)
# - 無獎: 高機率，小虧損 (-5%)
# 
# 整體期望值約為99%，讓玩家感受到贏多輸少的體驗
