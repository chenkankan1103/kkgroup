EQUIPMENT_SHOP = {
    "hair": {
        "常春藤髮型": {"price": 300, "id": 44943, "effects": []},
        "茶屋髮型": {"price": 300, "id": 44950, "effects": []},
        "側綁髮型": {"price": 300, "id": 47100, "effects": []},
        "糰子短髮": {"price": 300, "id": 47110, "effects": []},
        "旁分長髮": {"price": 300, "id": 48357, "effects": []}
    },
    "face": {
        "清泉臉": {"price": 300, "id": 26161, "effects": []},
        "水潤眼眸": {"price": 300, "id": 26153, "effects": []},
        "傲嬌臉": {"price": 300, "id": 26096, "effects": []},
        "童夢臉": {"price": 300, "id": 26654, "effects": []},
        "新年黑膚VIP臉": {"price": 300, "id": 25074, "effects": []}
    },
    "skin": {
        "健康膚色": {"price": 0, "id": 12002, "effects": []},
        "蜜糖膚色": {"price": 0, "id": 12008, "effects": []},
        "奶油膚色": {"price": 0, "id": 12009, "effects": []},
        "小麥膚色": {"price": 0, "id": 12010, "effects": []},
        "巧克力膚色": {"price": 0, "id": 12011, "effects": []}
    },
    "top": {
        "麻花針織上衣": {"price": 500, "id": 1042382, "effects": []},
        "企鵝T恤": {"price": 500, "id": 1042202, "effects": []},
        "橘色圍巾T恤": {"price": 500, "id": 1042203, "effects": []},
        "溫暖星星上衣": {"price": 500, "id": 1042207, "effects": []},
        "情侶上衣": {"price": 500, "id": 1048000, "effects": []}
    },
    "bottom": {
        "黃色補丁牛仔褲": {"price": 400, "id": 1062097, "effects": []},
        "水藍牛仔褲": {"price": 400, "id": 1062098, "effects": []},
        "嘻哈牛仔褲": {"price": 400, "id": 1062100, "effects": []},
        "反摺窄管褲": {"price": 400, "id": 1062101, "effects": []},
        "閃星牛仔褲": {"price": 400, "id": 1062102, "effects": []}
    },
    "shoes": {
        "可愛運動鞋": {"price": 300, "id": 1073308, "effects": []},
        "針織星星靴": {"price": 300, "id": 1073492, "effects": []},
        "花舞鞋": {"price": 300, "id": 1073523, "effects": []},
        "縫線球鞋": {"price": 300, "id": 1073237, "effects": []},
        "閃亮星光高跟鞋": {"price": 300, "id": 1071117, "effects": []}
    },
    "hat": {
        "魔法帽": {"price": 300, "id": 1003208, "effects": []},
        "靛藍兔耳貝雷帽": {"price": 300, "id": 1005334, "effects": []},
        "閃爍星星頭盔": {"price": 300, "id": 1004557, "effects": []},
        "愛心墨鏡": {"price": 300, "id": 1003807, "effects": []},
        "可愛兔兔帽": {"price": 300, "id": 1004403, "effects": []}
    },
    "overall": {
        "雪花大衣": {"price": 600, "id": 1050507, "effects": []},
        "糖果達令服": {"price": 600, "id": 1051559, "effects": []},
        "粉紅慶典禮服": {"price": 600, "id": 1051616, "effects": []},
        "湛藍泰迪裝": {"price": 600, "id": 1051612, "effects": []},
        "帕米娜的詠嘆調": {"price": 600, "id": 1051541, "effects": []}
    },
    "accessory": {
        "圓框眼鏡": {"price": 200, "id": 1022285, "effects": []},
        "極地探險墨鏡": {"price": 200, "id": 1022275, "effects": []},
        "葡萄柚光暈": {"price": 200, "id": 1012672, "effects": []},
        "三色臉部飾品": {"price": 200, "id": 1012674, "effects": []},
        "宿醉妝": {"price": 200, "id": 1012603, "effects": []}
    }
}

# 角色商店配置
ROLE_SHOP = {
    "七彩披風": {"price": 0, "role_id": 0, "duration": 86400},  # 1天 - 測試用
    "進階組員": {"price": 0, "role_id": 0, "duration": 604800},  # 1週 - 測試用
}

# 效果類型說明
EFFECT_DESCRIPTIONS = {
    "hp_bonus": "生命值 +{value}",
    "stamina_bonus": "體力 +{value}",
    "exp_bonus": "經驗值 +{value}",
    "kkcoin_bonus": "立即獲得 {value} KKcoin",
    "daily_kkcoin_bonus": "每日獲得 {value} KKcoin",
    "daily_stamina_regen": "每日體力回復 +{value}",
    "stamina_regen_rate": "體力回復速度 x{value}",
    "level_requirement": "需要等級 {min_level}",
}

# 裝備套裝效果（當穿戴多件相同系列時觸發）
EQUIPMENT_SETS = {

}