import hashlib
import json
import time
from typing import Optional


def generate_character_cache_key(user_data: dict) -> str:
    """生成角色快取鍵（包含 gender，使性別變更會使快取失效）"""
    key_parts = [
        str(user_data.get("face", 20000)),
        str(user_data.get("hair", 30000)),
        str(user_data.get("skin", 12000)),
        str(user_data.get("top", 1040010)),
        str(user_data.get("bottom", 1060096)),
        str(user_data.get("shoes", 1072288)),
        str(user_data.get("is_stunned", 0)),
        str(user_data.get("gender", "male")),
    ]
    key_string = "_".join(key_parts)
    return f"char_{hashlib.md5(key_string.encode()).hexdigest()}"


def get_cached_discord_url(image_cache: dict, cache_key: str) -> Optional[str]:
    """獲取快取的Discord URL"""
    try:
        # 清理過期快取
        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
        expired_keys = [
            key
            for key, data in image_cache.items()
            if data.get("created_at", 0) < thirty_days_ago
        ]
        for key in expired_keys:
            del image_cache[key]

        # 獲取快取的URL
        if cache_key in image_cache:
            return image_cache[cache_key].get("discord_url")
        return None

    except Exception:
        return None


def save_discord_url_cache(
    image_cache: dict, cache_key: str, discord_url: str, message_id: int = None
):
    """保存Discord URL到快取"""
    try:
        current_time = int(time.time())
        image_cache[cache_key] = {
            "discord_url": discord_url,
            "created_at": current_time,
            "message_id": message_id,
        }

    except Exception:
        pass


def build_maplestory_api_url(user_data: dict, animated: bool = True) -> str:
    """
    構建 MapleStory API URL（不實際發送請求）
    直接返回 API URL 用於在 Embed 中顯示
    """
    items = [
        {"itemId": 2000, "region": "TWMS", "version": "256"},
        {"itemId": user_data.get("skin", 12000), "region": "TWMS", "version": "256"},
        {
            "itemId": user_data.get("face", 20005),
            "animationName": "default",
            "region": "TWMS",
            "version": "256",
        },
        {"itemId": user_data.get("hair", 30120), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get("top", 1040014), "region": "TWMS", "version": "256"},
        {
            "itemId": user_data.get("bottom", 1060096),
            "region": "TWMS",
            "version": "256",
        },
        {"itemId": user_data.get("shoes", 1072005), "region": "TWMS", "version": "256"},
    ]

    if user_data.get("is_stunned", 0) == 1:
        items.append({"itemId": 1005411, "region": "TWMS", "version": "256"})

    item_path = ",".join([json.dumps(item, separators=(",", ":")) for item in items])
    pose = "prone" if user_data.get("is_stunned", 0) == 1 else "stand1"

    if animated:
        return f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"
    return f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"


def build_maplestory_api_url(user_data: dict, animated: bool = True) -> str:
    """生成 MapleStory.io API 的請求 URL（僅返回 URL 字串，**不發出網路請求**）"""
    items = [
        {"itemId": 2000, "region": "TWMS", "version": "256"},
        {"itemId": user_data.get("skin", 12000), "region": "TWMS", "version": "256"},
        {
            "itemId": user_data.get("face", 20005),
            "animationName": "default",
            "region": "TWMS",
            "version": "256",
        },
        {"itemId": user_data.get("hair", 30120), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get("top", 1040014), "region": "TWMS", "version": "256"},
        {
            "itemId": user_data.get("bottom", 1060096),
            "region": "TWMS",
            "version": "256",
        },
        {"itemId": user_data.get("shoes", 1072005), "region": "TWMS", "version": "256"},
    ]

    if user_data.get("is_stunned", 0) == 1:
        items.append({"itemId": 1005411, "region": "TWMS", "version": "256"})

    item_path = ",".join([json.dumps(item, separators=(",", ":")) for item in items])
    pose = "prone" if user_data.get("is_stunned", 0) == 1 else "stand1"

    if animated:
        return f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"
    return f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"


async def get_character_image_url(
    bot,
    user_data: dict,
    image_cache: dict,
    image_storage_channel_id: int,
    welcome_channel_id: int,
) -> Optional[str]:
    """獲取角色圖片 API URL，委派給 paperdoll_manager"""
    try:
        from . import paperdoll_manager

        api_url = paperdoll_manager.build_api_url(user_data)
        return api_url

    except Exception as e:
        print(f"❌ 構建圖片 URL 失敗: {e}")

    return None


async def restore_image_cache_from_storage(
    bot, image_cache: dict, image_storage_channel_id: int
):
    """啟動時掃描存儲頻道，恢復快取URL"""
    try:
        if not image_storage_channel_id:
            return

        channel = bot.get_channel(image_storage_channel_id)
        if not channel:
            print(f"⚠️ 無法找到存儲頻道: {image_storage_channel_id}")
            return

        print("🔄 正在掃描存儲頻道以恢復圖片快取...")
        recovered_count = 0

        async for message in channel.history(limit=500):
            try:
                if not message.attachments:
                    continue

                for attachment in message.attachments:
                    filename = attachment.filename or ""
                    if filename.endswith(".png") and len(filename) > 10:
                        cache_key = filename.replace(".png", "")

                        if cache_key.replace(",", "").isdigit():
                            discord_url = attachment.url
                            save_discord_url_cache(
                                image_cache, cache_key, discord_url, message.id
                            )
                            recovered_count += 1

            except Exception:
                continue

        print(f"✅ 成功恢復 {recovered_count} 個圖片快取")

    except Exception as e:
        print(f"⚠️ 恢復快取時出錯: {e}")
