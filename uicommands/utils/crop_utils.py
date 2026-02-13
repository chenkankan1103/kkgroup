# 大麻種植系統工具函數

import discord
from datetime import datetime
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP


def format_plant_progress(plant):
    """
    格式化植物成長進度

    Args:
        plant (dict): 植物數據

    Returns:
        str: 格式化的進度字符串
    """
    if plant["status"] == "harvested":
        return "✅ 已成熟 100%"

    planted_time = plant["planted_at"]
    matured_time = plant["matured_at"]

    # 處理時間戳格式（可能是字符串或float）
    if isinstance(planted_time, str):
        planted_time = datetime.fromisoformat(planted_time).timestamp()
    if isinstance(matured_time, str):
        matured_time = datetime.fromisoformat(matured_time).timestamp()

    now = datetime.now().timestamp()
    elapsed = now - planted_time
    total = matured_time - planted_time
    progress = min(100, (elapsed / total * 100)) if total > 0 else 0

    filled = int(progress / 5)
    empty = 20 - filled
    progress_text = f"{'█' * filled}{'░' * empty} {progress:.0f}%"

    remaining = max(0, matured_time - now)
    if remaining > 0:
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        status_info = f"剩餘 {hours}h {mins}m"
    else:
        status_info = "✅ 已成熟"

    return f"{progress_text}\n{status_info}"


def create_plant_embed(plant, idx=None):
    """
    創建植物狀態的embed字段

    Args:
        plant (dict): 植物數據
        idx (int, optional): 植物編號

    Returns:
        dict: embed字段數據
    """
    seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
    progress_text = format_plant_progress(plant)

    name = f"#{idx} {seed_config['emoji']}" if idx else f"{seed_config['emoji']}"
    value = (
        f"🌾 種類：{plant['seed_type']}\n"
        f"📊 進度：{progress_text}\n"
        f"💧 施肥：{plant['fertilizer_applied']}次"
    )

    return {"name": name, "value": value, "inline": False}


def calculate_harvest_value(plant):
    """
    計算收割價值

    Args:
        plant (dict): 植物數據

    Returns:
        dict: 包含數量、單價、總價的字典
    """
    from shop_commands import CANNABIS_HARVEST_PRICES

    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
    yield_amount = plant.get("yield", config["max_yield"])
    price = CANNABIS_HARVEST_PRICES[plant["seed_type"]]
    total_value = yield_amount * price

    return {
        "yield_amount": yield_amount,
        "price": price,
        "total_value": total_value
    }


def validate_plant_operation(user_id, plant_id, operation_type):
    """
    驗證植物操作

    Args:
        user_id (int): 用戶ID
        plant_id (int): 植物ID
        operation_type (str): 操作類型 ('fertilize', 'harvest')

    Returns:
        dict: 驗證結果 {'valid': bool, 'reason': str, 'plant': dict or None}
    """
    from shop_commands import get_user_plants, get_inventory

    try:
        plants = get_user_plants(user_id)
        plant = next((p for p in plants if p['id'] == plant_id), None)

        if not plant:
            return {"valid": False, "reason": "找不到指定的植物", "plant": None}

        if operation_type == "fertilize":
            if plant["status"] == "harvested":
                return {"valid": False, "reason": "植物已成熟，無法施肥", "plant": plant}

            inventory = get_inventory(user_id)
            if not inventory.get("肥料"):
                return {"valid": False, "reason": "沒有肥料", "plant": plant}

        elif operation_type == "harvest":
            if plant["status"] != "harvested":
                return {"valid": False, "reason": "植物尚未成熟", "plant": plant}

        return {"valid": True, "reason": "", "plant": plant}

    except Exception as e:
        return {"valid": False, "reason": f"驗證失敗: {str(e)}", "plant": None}