import os
from dotenv import load_dotenv
from pathlib import Path

# 確保載入 .env 檔案 - 在上上層資料夾
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 調試：顯示 .env 檔案路徑和是否存在
print(f"[Config] .env 檔案路徑: {env_path}")
print(f"[Config] .env 檔案是否存在: {env_path.exists()}")

# 資料庫配置
DB_PATH = os.getenv("DB_PATH", "user_data.db")

# 角色ID配置 - 使用硬編碼作為備用方案
def get_role_id(env_var, default_id):
    """獲取角色ID，優先使用環境變數，否則使用預設值"""
    env_value = os.getenv(env_var)
    if env_value:
        try:
            return int(env_value)
        except ValueError:
            print(f"[警告] {env_var} 環境變數格式錯誤: {env_value}")
    return default_id

# 角色ID配置
RAINBOW_ROLE_ID = get_role_id("RAINBOW_ROLE_ID", 1369373373498658877)  # 變色龍披風ID
VIP_ROLE_ID = get_role_id("VIP_ROLE_ID", 1369561759777689610)        # 進階組員ID
MUTE_ROLE_ID = get_role_id("MUTE_ROLE_ID", 0)
MEMBER_ROLE_ID = get_role_id("MEMBER_ROLE_ID", 0)

# 調試：印出載入的角色ID
print(f"[Config] RAINBOW_ROLE_ID: {RAINBOW_ROLE_ID} ({'從環境變數' if os.getenv('RAINBOW_ROLE_ID') else '使用預設值'})")
print(f"[Config] VIP_ROLE_ID: {VIP_ROLE_ID} ({'從環境變數' if os.getenv('VIP_ROLE_ID') else '使用預設值'})")
print(f"[Config] MUTE_ROLE_ID: {MUTE_ROLE_ID} ({'從環境變數' if os.getenv('MUTE_ROLE_ID') else '使用預設值'})")
print(f"[Config] MEMBER_ROLE_ID: {MEMBER_ROLE_ID} ({'從環境變數' if os.getenv('MEMBER_ROLE_ID') else '使用預設值'})")

# 裝備商店配置 - 移動到這裡避免循環導入
EQUIPMENT_SHOP = {
    "hair": {
        "清新短髮": {
            "id": 30000,
            "price": 100,
            "description": "清新自然的短髮造型"
        },
        "時尚長捲髮": {
            "id": 30010,
            "price": 150,
            "description": "優雅的長捲髮造型"
        },
        "活力馬尾": {
            "id": 30020,
            "price": 120,
            "description": "充滿活力的馬尾辮"
        }
    },
    "face": {
        "溫和表情": {
            "id": 20000,
            "price": 80,
            "description": "溫和友善的面部表情"
        },
        "活潑表情": {
            "id": 20010,
            "price": 90,
            "description": "活潑開朗的面部表情"
        }
    },
    "skin": {
        "自然膚色": {
            "id": 12000,
            "price": 50,
            "description": "自然健康的膚色"
        },
        "白皙膚色": {
            "id": 12001,
            "price": 60,
            "description": "白皙透亮的膚色"
        }
    },
    "top": {
        "休閒T恤": {
            "id": 1040010,
            "price": 200,
            "description": "舒適的休閒T恤"
        },
        "正式襯衫": {
            "id": 1040020,
            "price": 300,
            "description": "正式場合的襯衫"
        }
    },
    "bottom": {
        "牛仔褲": {
            "id": 1060096,
            "price": 250,
            "description": "經典的牛仔褲"
        },
        "休閒短褲": {
            "id": 1060100,
            "price": 180,
            "description": "舒適的休閒短褲"
        }
    },
    "shoes": {
        "運動鞋": {
            "id": 1072288,
            "price": 300,
            "description": "舒適的運動鞋"
        },
        "正式皮鞋": {
            "id": 1072300,
            "price": 400,
            "description": "正式的皮鞋"
        }
    }
}

# 角色商店配置 - 直接在這裡定義，不使用外部檔案
ROLE_SHOP = {
    "七彩披風": {
        "price": 50, 
        "role_id": RAINBOW_ROLE_ID, 
        "duration": 86400  # 1天 = 86400秒
    },
    "進階組員": {
        "price": 75, 
        "role_id": VIP_ROLE_ID, 
        "duration": 604800  # 1週 = 604800秒
    }
}

# 驗證關鍵角色ID
critical_roles = {
    "RAINBOW_ROLE_ID": RAINBOW_ROLE_ID,
    "VIP_ROLE_ID": VIP_ROLE_ID
}

missing_roles = [name for name, role_id in critical_roles.items() if role_id == 0]
if missing_roles:
    print(f"[警告] 以下關鍵角色ID未設定: {', '.join(missing_roles)}")
    print("請檢查 .env 檔案或環境變數設定")
else:
    print("[Config] 所有關鍵角色ID已正確載入")

# 驗證角色商店配置
print("[Config] 角色商店配置:")
for role_name, config in ROLE_SHOP.items():
    role_id = config["role_id"]
    price = config["price"]
    duration = config.get("duration", "永久")
    print(f"  - {role_name}: 價格={price}, 角色ID={role_id}, 時長={duration}秒")

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
