"""大麻商品配置與種植參數"""

# 大麻商品配置（種子）
CANNABIS_SHOP = {
    "種子": {
        "常規種": {
            "name": "常規種子",
            "price": 100,
            "emoji": "🌱",
            "growth_time": 18000,  # 5小時
            "max_yield": 5,
            "description": "標準大麻種子，成長快、產量穩定"
        },
        "優質種": {
            "name": "優質種子",
            "price": 200,
            "emoji": "🌿",
            "growth_time": 36000,  # 10小時
            "max_yield": 10,
            "description": "優質大麻種子，成長較慢但產量高"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 500,
            "emoji": "👑",
            "growth_time": 54000,  # 15小時
            "max_yield": 20,
            "description": "稀有黃金種子，回報豐厚"
        }
    }
}

# 大麻出售價格
CANNABIS_HARVEST_PRICES = {
    "常規種": 200,      # 每個 200 KKcoin（購買 100，賣 200，利潤倍增）
    "優質種": 500,      # 每個 500 KKcoin
    "黃金種": 1500      # 每個 1500 KKcoin
}
