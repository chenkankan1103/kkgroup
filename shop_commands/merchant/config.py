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
