import discord
import aiohttp
import json
import io
import asyncio
import time
import hashlib
from pathlib import Path
from typing import Optional
from db_adapter import set_user_field, get_user_field


def generate_character_cache_key(user_data: dict) -> str:
    """生成角色快取鍵"""
    key_parts = [
        str(user_data.get('face', 20000)), str(user_data.get('hair', 30000)),
        str(user_data.get('skin', 12000)), str(user_data.get('top', 1040010)),
        str(user_data.get('bottom', 1060096)), str(user_data.get('shoes', 1072288)),
        str(user_data.get('is_stunned', 0))
    ]
    key_string = "_".join(key_parts)
    return f"char_{hashlib.md5(key_string.encode()).hexdigest()}"


def get_cached_discord_url(image_cache: dict, cache_key: str) -> Optional[str]:
    """獲取快取的Discord URL"""
    try:
        # 清理過期快取
        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
        expired_keys = [key for key, data in image_cache.items() 
                       if data.get('created_at', 0) < thirty_days_ago]
        for key in expired_keys:
            del image_cache[key]
        
        # 獲取快取的URL
        if cache_key in image_cache:
            return image_cache[cache_key].get('discord_url')
        return None
        
    except Exception:
        return None


def save_discord_url_cache(image_cache: dict, cache_key: str, discord_url: str, message_id: int = None):
    """保存Discord URL到快取"""
    try:
        current_time = int(time.time())
        image_cache[cache_key] = {
            'discord_url': discord_url,
            'created_at': current_time,
            'message_id': message_id
        }
        
    except Exception:
        pass


async def upload_image_to_discord_storage(bot, image_data: bytes, cache_key: str, image_cache: dict, 
                                          image_storage_channel_id: int, welcome_channel_id: int) -> Optional[str]:
    """上傳圖片到Discord存儲頻道"""
    try:
        storage_channel_id = image_storage_channel_id or welcome_channel_id
        
        channel = bot.get_channel(storage_channel_id)
        if not channel:
            print(f"❌ 找不到存儲頻道: {storage_channel_id}")
            return None
        
        file_obj = discord.File(io.BytesIO(image_data), filename=f'{cache_key}.png')
        
        if image_storage_channel_id and image_storage_channel_id != welcome_channel_id:
            # 專用存儲頻道：保留訊息以維持 URL 永久有效
            storage_msg = await channel.send(content=f"🖼️ **角色圖片** - {cache_key}", file=file_obj)
            if storage_msg.attachments:
                discord_url = storage_msg.attachments[0].url
                save_discord_url_cache(image_cache, cache_key, discord_url, storage_msg.id)
                print(f"✅ 圖片已存儲至存儲頻道: {storage_msg.id}")
                return discord_url
        else:
            # 備用：歡迎頻道臨時訊息
            temp_msg = await channel.send(file=file_obj)
            if temp_msg.attachments:
                discord_url = temp_msg.attachments[0].url
                save_discord_url_cache(image_cache, cache_key, discord_url, temp_msg.id)
                try:
                    await asyncio.sleep(0.5)
                    await temp_msg.delete()
                except discord.NotFound:
                    pass
                return discord_url
        
    except Exception as e:
        print(f"❌ 上傳圖片失敗: {e}")
    return None


def build_maplestory_api_url(user_data: dict, animated: bool = True) -> str:
    """生成 MapleStory.io API 的請求 URL（僅返回 URL 字串，**不發出網路請求**）"""
    items = [
        {"itemId": 2000, "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('skin', 12000), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('face', 20005), "animationName": "default", "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('hair', 30120), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('top', 1040014), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('bottom', 1060096), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('shoes', 1072005), "region": "TWMS", "version": "256"}
    ]

    if user_data.get('is_stunned', 0) == 1:
        items.append({"itemId": 1005411, "region": "TWMS", "version": "256"})

    item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
    pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"

    if animated:
        return f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"
    return f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"


async def get_character_image_url(bot, user_data: dict, image_cache: dict, image_storage_channel_id: int, 
                                  welcome_channel_id: int) -> Optional[str]:
    """獲取角色圖片URL（優先使用快取，再用API）"""
    cache_key = generate_character_cache_key(user_data)
    user_id = user_data.get('user_id')
    
    # 1. 先檢查記憶體快取
    cached_url = get_cached_discord_url(image_cache, cache_key)
    if cached_url:
        return cached_url
    
    # 2. 檢查資料庫中的快取
    try:
        cached_char_data = get_user_field(user_id, 'cached_character_image', default=None)
        if cached_char_data:
            try:
                char_cache = json.loads(cached_char_data)
                current_key = generate_character_cache_key(user_data)
                if char_cache.get('cache_key') == current_key and char_cache.get('discord_url'):
                    stored_url = char_cache['discord_url']
                    save_discord_url_cache(image_cache, cache_key, stored_url)
                    return stored_url
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    
    # 3. 呼叫API獲取圖片
    try:
        items = [
            {"itemId": 2000, "region": "GMS", "version": "217"},
            {"itemId": user_data.get('skin', 12000), "region": "GMS", "version": "217"},
            {"itemId": user_data.get('face', 20005), "animationName": "default", "region": "GMS", "version": "217"},
            {"itemId": user_data.get('hair', 30120), "region": "GMS", "version": "217"},
            {"itemId": user_data.get('top', 1040014), "region": "GMS", "version": "217"},
            {"itemId": user_data.get('bottom', 1060096), "region": "GMS", "version": "217"},
            {"itemId": user_data.get('shoes', 1072005), "region": "GMS", "version": "217"}
        ]

        if user_data.get('is_stunned', 0) == 1:
            items.append({"itemId": 1005411, "region": "GMS", "version": "217"})

        item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
        pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
        url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    if len(image_data) > 100:
                        discord_url = await upload_image_to_discord_storage(
                            bot, image_data, cache_key, image_cache, 
                            image_storage_channel_id, welcome_channel_id
                        )
                        if discord_url:
                            char_cache = {
                                'cache_key': cache_key,
                                'discord_url': discord_url,
                                'timestamp': int(time.time())
                            }
                            try:
                                set_user_field(user_id, 'cached_character_image', json.dumps(char_cache))
                            except Exception:
                                pass
                            return discord_url

    except asyncio.TimeoutError:
        print(f"⏱️ 楓之谷 API 超時 (用戶 {user_id})")
    except Exception as e:
        print(f"❌ 獲取角色圖片失敗: {e}")
    
    return None


async def restore_image_cache_from_storage(bot, image_cache: dict, image_storage_channel_id: int):
    """啟動時掃描存儲頻道，恢復快取URL"""
    try:
        if not image_storage_channel_id:
            return
        
        channel = bot.get_channel(image_storage_channel_id)
        if not channel:
            print(f"⚠️ 無法找到存儲頻道: {image_storage_channel_id}")
            return
        
        print(f"🔄 正在掃描存儲頻道以恢復圖片快取...")
        recovered_count = 0
        
        async for message in channel.history(limit=500):
            try:
                if not message.attachments:
                    continue
                
                for attachment in message.attachments:
                    filename = attachment.filename or ""
                    if filename.endswith('.png') and len(filename) > 10:
                        cache_key = filename.replace('.png', '')
                        
                        if cache_key.replace(',', '').isdigit():
                            discord_url = attachment.url
                            save_discord_url_cache(image_cache, cache_key, discord_url, message.id)
                            recovered_count += 1
                
            except Exception:
                continue
        
        print(f"✅ 成功恢復 {recovered_count} 個圖片快取")
    
    except Exception as e:
        print(f"⚠️ 恢復快取時出錯: {e}")
