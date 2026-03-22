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
            "description": "4h±1h 成長，3格上限；高概率中高產，單價700KK"
        },
        "優質種": {
            "name": "優質種子",
            "price": 90,
            "emoji": "🌿",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "4h±1h 成長，3格上限；中等速度成長，中等風險高產"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 150,
            "emoji": "👑",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "4h±1h 成長，3格上限；高價稀有，但大多低產（可爆發少量高價）"
        }
    }
}

# 大麻出售價格（×10倍）
CANNABIS_HARVEST_PRICES = {
    "常規種": 700,      # 每個 700 KKcoin
    "優質種": 900,      # 每個 900 KKcoin
    "黃金種": 1500      # 每個 1500 KKcoin
}
