"""大麻商品配置與種植參數"""

# 大麻商品配置（種子）
CANNABIS_SHOP = {
    "種子": {
        "常規種": {
            "name": "常規種子",
            "price": 50,
            "emoji": "🌱",
            "growth_time": 3600,  # 1小時
            "max_yield": 5,
            "description": "標準大麻種子，成長快、產量穩定"
        },
        "優質種": {
            "name": "優質種子",
            "price": 100,
            "emoji": "🌿",
            "growth_time": 7200,  # 2小時
            "max_yield": 10,
            "description": "優質大麻種子，成長較慢但產量高"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 250,
            "emoji": "👑",
            "growth_time": 10800,  # 3小時
            "max_yield": 20,
            "description": "稀有黃金種子，回報豐厚"
        }
    }
}

# 大麻出售價格
CANNABIS_HARVEST_PRICES = {
    "常規種": 100,      # 每個 100 KKcoin（購買 50，賣 100，利潤倍增）
    "優質種": 250,      # 每個 250 KKcoin
    "黃金種": 750      # 每個 750 KKcoin
}
