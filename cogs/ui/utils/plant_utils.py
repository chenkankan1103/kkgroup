import json
from typing import Optional
from db_adapter import get_user, set_user

from . import paperdoll_manager


def ensure_user_exists(user_id: int) -> bool:
    """確保使用者在資料庫中存在"""
    try:
        user_data = get_user(user_id)

        if user_data:
            return True

        random_appearance = paperdoll_manager.get_random()

        # 創建新使用者
        set_user(
            user_id,
            {
                "user_id": user_id,
                "level": 1,
                "xp": 0,
                "kkcoin": 0,
                "title": "新手",
                "hp": 100,
                "stamina": 100,
                "inventory": json.dumps(["手機", "身分證"], ensure_ascii=False),
                "character_config": "{}",
                "face": int(random_appearance["face"]),
                "hair": int(random_appearance["hair"]),
                "skin": int(random_appearance["skin"]),
                "top": int(random_appearance["top"]),
                "bottom": int(random_appearance["bottom"]),
                "shoes": int(random_appearance["shoes"]),
                "is_stunned": 0,
                "gender": random_appearance["gender"],
                "thread_id": 0,
                # 初始化週統計快照字段
                "last_kkcoin_snapshot": 0,
                "last_xp_snapshot": 0,
                "last_level_snapshot": 1,
            },
        )

        return True

    except Exception:
        return False


def get_user_data(user_id: int) -> Optional[dict]:
    """獲取用戶資料"""
    try:
        user = get_user(user_id)
        if not user:
            return None

        return {
            "user_id": user.get("user_id") or user_id,
            "level": user.get("level", 1),
            "xp": user.get("xp", 0),
            "kkcoin": user.get("kkcoin", 0),
            "title": user.get("title", "新手"),
            "hp": user.get("hp", 100),
            "stamina": user.get("stamina", 100),
            "inventory": user.get("inventory", "{}"),
            "character_config": user.get("character_config", "{}"),
            "face": user.get("face", 20000),
            "hair": user.get("hair", 30000),
            "skin": user.get("skin", 12000),
            "top": user.get("top", 1040010),
            "bottom": user.get("bottom", 1060096),
            "shoes": user.get("shoes", 1072288),
            "is_stunned": user.get("is_stunned", 0),
            "gender": user.get("gender", "male"),
            "thread_id": user.get("thread_id", 0),
        }
    except Exception:
        return None
