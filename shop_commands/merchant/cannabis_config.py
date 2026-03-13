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
    "常規種": 100,      # 每個 100 KKcoin（產出 2.5~5 個，1小時1次，理論日收益 6,000~12,000）
    "優質種": 150,      # 每個 150 KKcoin（產出 5~10 個，2小時1次，理論日收益 9,000~18,000）
    "黃金種": 300       # 每個 300 KKcoin（產出 10~20 個，3小時1次，理論日收益 24,000~48,000）
}
