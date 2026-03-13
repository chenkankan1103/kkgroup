"""大麻商品配置與種植參數"""

# 大麻商品配置（種子）
CANNABIS_SHOP = {
    "種子": {
        "常規種": {
            "name": "常規種子",
            "price": 50,
            "emoji": "🌱",
            "growth_time": 3600,  # 1小時
            "max_yield": 3,
            "description": "標準大麻種子，成長快、穩定獲利"
        },
        "優質種": {
            "name": "優質種子",
            "price": 100,
            "emoji": "🌿",
            "growth_time": 7200,  # 2小時
            "max_yield": 3,
            "description": "優質大麻種子，平衡收益"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 250,
            "emoji": "👑",
            "growth_time": 10800,  # 3小時
            "max_yield": 3,
            "description": "稀有黃金種子，長期收益穩定"
        }
    }
}

# 大麻出售價格
CANNABIS_HARVEST_PRICES = {
    "常規種": 30,       # 每個 30 KKcoin（產出 1.5~3 個，1小時1次，理論日收益 1,800/格）
    "優質種": 70,       # 每個 70 KKcoin（產出 1.5~3 個，2小時1次，理論日收益 1,890/格）
    "黃金種": 100       # 每個 100 KKcoin（產出 1.5~3 個，3小時1次，理論日收益 1,800/格）
}
