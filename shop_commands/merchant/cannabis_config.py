"""大麻商品配置與種植參數"""

# 大麻商品配置（種子）
CANNABIS_SHOP = {
    "種子": {
        "常規種": {
            "name": "常規種子",
            "price": 70,
            "emoji": "🌱",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "標準大麻種子，容易大豐收"
        },
        "優質種": {
            "name": "優質種子",
            "price": 90,
            "emoji": "🌿",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "優質大麻種子，機率中等的高產"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 150,
            "emoji": "👑",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "稀有黃金種子，高級但常常低產"
        }
    }
}

# 大麻出售價格（×10倍）
CANNABIS_HARVEST_PRICES = {
    "常規種": 700,      # 每個 700 KKcoin
    "優質種": 900,      # 每個 900 KKcoin
    "黃金種": 1500      # 每個 1500 KKcoin
}
