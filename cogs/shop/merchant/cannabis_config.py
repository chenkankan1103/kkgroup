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
            "description": "4h±1h 成長，5格上限；高概率中高產，單價700KK",
        },
        "優質種": {
            "name": "優質種子",
            "price": 90,
            "emoji": "🌿",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "4h±1h 成長，5格上限；中等速度成長，中等風險高產",
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 150,
            "emoji": "👑",
            "growth_time": 14400,  # 4小時（隨機 ±1 小時）
            "max_yield": 15,
            "description": "4h±1h 成長，5格上限；高價稀有，但大多低產（可爆發少量高價）",
        },
    },
    "肥料": {
        "基礎肥料": {
            "name": "基礎肥料",
            "price": 30,
            "emoji": "💧",
            "growth_boost": 0.1,  # 加速 10%
            "description": "小幅縮短成長時間，適合早期使用",
        },
        "高效肥料": {
            "name": "高效肥料",
            "price": 60,
            "emoji": "⚡",
            "growth_boost": 0.2,  # 加速 20%
            "description": "中幅縮短成長時間，性價比最佳",
        },
        "頂級肥料": {
            "name": "頂級肥料",
            "price": 100,
            "emoji": "✨",
            "growth_boost": 0.35,  # 加速 35%
            "description": "大幅縮短成長時間，適合緊急催熟",
        },
    },
}

# 大麻出售價格（×10倍）
CANNABIS_HARVEST_PRICES = {
    "常規種": 700,  # 每個 700 KKcoin
    "優質種": 900,  # 每個 900 KKcoin
    "黃金種": 1500,  # 每個 1500 KKcoin
}
