"""大麻商品配置與種植參數"""

# 大麻商品配置（種子）
CANNABIS_SHOP = {
    "種子": {
        "常規種": {
            "name": "常規種子",
            "price": 50,
            "emoji": "🌱",
            "growth_time": 7200,  # 2小時（基礎1小時*2，實際 1-3 小時）
            "max_yield": 20,
            "description": "標準大麻種子，容易大豐收"
        },
        "優質種": {
            "name": "優質種子",
            "price": 100,
            "emoji": "🌿",
            "growth_time": 14400,  # 4小時（基礎2小時*2，實際 3-5 小時）
            "max_yield": 20,
            "description": "優質大麻種子，產量不穩定"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 250,
            "emoji": "👑",
            "growth_time": 21600,  # 6小時（基礎3小時*2，實際 5-7 小時）
            "max_yield": 20,
            "description": "稀有黃金種子，常見低產"
        }
    }
}

# 大麻出售價格
CANNABIS_HARVEST_PRICES = {
    "常規種": 40,       # 每個 40 KKcoin
    "優質種": 80,       # 每個 80 KKcoin
    "黃金種": 150       # 每個 150 KKcoin
}
