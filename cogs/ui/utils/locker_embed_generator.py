"""
置物櫃 Embed 生成器 - 中心化邏輯

所有置物櫃相關的 embed 生成都應通過此模塊
確保一致性和動態 MapleStory API URL 的使用
"""

import discord
from typing import Optional, Dict, Any
from db_adapter import get_user


async def generate_canonical_locker_embed(
    cog,
    user_data: Dict[str, Any],
    user_obj: Optional[discord.User] = None,
    include_cannabis_info: bool = False,
    plants: Optional[list] = None,
    inventory: Optional[dict] = None
) -> discord.Embed:
    """
    生成置物櫃的 canonical embed
    
    此函數確保所有置物櫃 embed 都使用相同的邏輯：
    1. 首先嘗試使用 UserPanel.create_user_embed（含紙娃娃 + MapleStory API）
    2. Fallback 時使用 build_maplestory_api_url() 來保證動態圖片
    3. 若提供 cannabis 數據，附加植物和庫存欄位
    
    Args:
        cog: UserPanel cog 或具有 create_user_embed 方法的對象
        user_data: 用戶數據字典
        user_obj: discord.User 對象（可選，用於顯示名稱等）
        include_cannabis_info: 是否附加大麻系統信息
        plants: 植物列表（若 include_cannabis_info=True）
        inventory: 庫存字典（若 include_cannabis_info=True）
        
    Returns:
        discord.Embed: 生成的 canonical embed
    """
    embed = None
    
    # Step 1: 優先使用 UserPanel.create_user_embed
    try:
        if hasattr(cog, 'create_user_embed'):
            embed = await cog.create_user_embed(user_data, user_obj)
        else:
            # 嘗試從 utils 導入
            from uicommands.utils.embed_utils import create_user_embed as util_create
            embed = await util_create(cog, user_data, user_obj or discord.Object(id=user_data.get('user_id')))
    except Exception as e:
        print(f"⚠️ [Locker Embed Generator] 無法呼叫 create_user_embed: {e}")
        embed = None
    
    # Step 2: 確保 embed 有圖片（Fallback with dynamic API）
    if embed:
        try:
            img_url = (embed.image.url if getattr(embed, 'image', None) else None)
        except Exception:
            img_url = None
            
        if not img_url:
            try:
                from uicommands.utils.image_utils import build_maplestory_api_url
                api_url = build_maplestory_api_url(user_data, animated=True)
                if api_url:
                    embed.set_image(url=api_url)
                    embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
            except Exception as img_err:
                print(f"⚠️ [Locker Embed Generator] Embed 無法添加圖片: {img_err}")
    
    # Step 3: 若完全失敗，建立基本 embed + 動態圖片
    if not embed:
        user_id = user_data.get('user_id')
        try:
            user_name = (await cog.bot.fetch_user(user_id)).name if hasattr(cog, 'bot') else f"用戶{user_id}"
        except Exception:
            user_name = f"用戶{user_id}"
        
        embed = discord.Embed(
            title=f"📦 {user_name} 的置物櫃",
            description="個人置物櫃",
            color=discord.Color.from_str("#00ff88")
        )
        
        # 仍然嘗試添加動態圖片
        try:
            from uicommands.utils.image_utils import build_maplestory_api_url
            api_url = build_maplestory_api_url(user_data, animated=True)
            if api_url:
                embed.set_image(url=api_url)
                embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
        except Exception as img_err:
            print(f"⚠️ [Locker Embed Generator] Fallback embed 無法添加圖片: {img_err}")
    
    # Step 4: 附加大麻系統信息（可選）
    if include_cannabis_info and plants:
        from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
        from datetime import datetime
        
        for plant in plants:
            seed_config = CANNABIS_SHOP.get('種子', {}).get(plant.get('seed_type'), {})
            
            # 計算進度與狀態
            if plant.get('status') == 'harvested':
                status_text = '✅ 已成熟，可以收割！'
                progress_bar = '████████████████████ 100%'
            else:
                planted_time = plant.get('planted_at')
                matured_time = plant.get('matured_at')
                try:
                    if isinstance(planted_time, str):
                        planted_time = datetime.fromisoformat(planted_time).timestamp()
                    if isinstance(matured_time, str):
                        matured_time = datetime.fromisoformat(matured_time).timestamp()
                except Exception:
                    planted_time = planted_time or 0
                    matured_time = matured_time or 0
                
                now = datetime.now().timestamp()
                elapsed = max(0, now - (planted_time or now))
                total = max(1, (matured_time or now) - (planted_time or now))
                progress = min(100, (elapsed / total * 100)) if total > 0 else 0
                filled = int(progress / 5)
                empty = 20 - filled
                progress_bar = '█' * filled + '░' * empty + f" {progress:.0f}%"
                remaining = max(0, (matured_time or now) - now)
                
                if remaining > 0:
                    hours = int(remaining // 3600)
                    mins = int((remaining % 3600) // 60)
                    status_text = f"🌱 成長中... 剩餘 {hours}h {mins}m"
                else:
                    status_text = '✅ 已成熟，可以收割！'
            
            field_value = (
                f"種子：{seed_config.get('emoji','🌱')} {plant.get('seed_type')}\n"
                f"進度：{progress_bar}\n"
                f"狀態：{status_text}"
            )
            embed.add_field(name=f"植物 #{plant.get('id')}", value=field_value, inline=False)
    
    # 附加庫存信息（可選）
    if include_cannabis_info and inventory:
        from shop_commands.merchant.cannabis_config import CANNABIS_HARVEST_PRICES
        
        if inventory.get('種子'):
            seeds_info = ''.join(f"  🌱 {k} x{v}\n" for k, v in (inventory.get('種子') or {}).items() if v)
            if seeds_info:
                embed.add_field(name='🌾 種子庫存', value=seeds_info.strip(), inline=True)
        
        if inventory.get('肥料'):
            fert_info = ''.join(f"  💧 {k} x{v}\n" for k, v in (inventory.get('肥料') or {}).items() if v)
            if fert_info:
                embed.add_field(name='💧 肥料庫存', value=fert_info.strip(), inline=True)
        
        if inventory.get('大麻'):
            cannabis_info = ''.join(
                f"  💰 {k} x{v} ({CANNABIS_HARVEST_PRICES.get(k,0)}/個)\n"
                for k, v in (inventory.get('大麻') or {}).items() if v
            )
            if cannabis_info:
                embed.add_field(name='📦 大麻庫存', value=cannabis_info.strip(), inline=False)
    
    return embed


def _has_legacy_button_components(components) -> bool:
    try:
        for row in components or []:
            # row can be ActionRow (discord) or dict (API JSON)
            children = None
            if isinstance(row, dict):
                children = row.get('components', [])
            else:
                children = getattr(row, 'children', [])

            for comp in children:
                cid = None
                if isinstance(comp, dict):
                    cid = comp.get('custom_id')
                else:
                    cid = getattr(comp, 'custom_id', None)
                if cid == 'locker_crop_info':
                    return True
    except Exception:
        pass
    return False


def message_json_needs_update(msg_json: dict) -> bool:
    """判斷從 Discord API 取得的 message JSON 是否需要被更新（用於 tools）。"""
    try:
        embeds = msg_json.get('embeds') or []
        current_embed = embeds[0] if embeds else None
        current_image = None
        current_footer = ''
        if current_embed:
            current_image = (current_embed.get('image') or {}).get('url')
            current_footer = (current_embed.get('footer') or {}).get('text', '') or ''

        # missing image or missing MapleStory footer -> needs update
        if not current_image:
            return True
        if 'MapleStory' not in (current_footer or ''):
            return True

        # legacy buttons present -> needs update
        if _has_legacy_button_components(msg_json.get('components') or []):
            return True

        return False
    except Exception:
        return True


def message_needs_update(message: discord.Message) -> bool:
    """判斷 discord.Message 是否需要更新（用於在 bot 內的檢查）。"""
    try:
        current_embed = message.embeds[0] if message.embeds else None
        current_image = None
        current_footer = ''
        if current_embed:
            img = getattr(current_embed, 'image', None)
            current_image = getattr(img, 'url', None) if img else None
            footer = getattr(current_embed, 'footer', None)
            current_footer = (getattr(footer, 'text', '') or '')

        if not current_image:
            return True
        if 'MapleStory' not in (current_footer or ''):
            return True

        # components: check for legacy custom_id
        for row in message.components or []:
            for child in getattr(row, 'children', []):
                cid = getattr(child, 'custom_id', None) or (child.get('custom_id') if isinstance(child, dict) else None)
                if cid == 'locker_crop_info':
                    return True

        return False
    except Exception:
        return True

async def update_locker_message(
    thread: discord.Thread,
    user_id: int,
    message_obj: Optional[discord.Message] = None,
    bot = None,
    cog = None,
    plants: Optional[list] = None,
    inventory: Optional[dict] = None
) -> bool:
    """
    統一的置物櫃訊息編輯邏輯
    
    嘗試編輯現有訊息或發送新訊息，並更新數據庫中的 locker_message_id
    
    Args:
        thread: Discord 線程對象
        user_id: 使用者 ID
        message_obj: 現有的 Message 對象（如果有）
        bot: Discord bot 對象
        cog: UserPanel cog
        plants: 植物列表
        inventory: 庫存字典
        
    Returns:
        bool: 是否成功更新
    """
    try:
        from db_adapter import get_user, set_user_field
        from uicommands.views import LockerPanelView
        
        # 獲取用戶數據
        user_data = get_user(user_id)
        if not user_data:
            print(f"❌ [Update Locker Message] 無法找到用戶 {user_id} 的數據")
            return False
        
        # 生成 canonical embed
        user_obj = None
        if bot:
            try:
                user_obj = await bot.fetch_user(user_id)
            except Exception:
                pass
        
        embed = await generate_canonical_locker_embed(
            cog or bot,
            user_data,
            user_obj,
            include_cannabis_info=bool(plants or inventory),
            plants=plants,
            inventory=inventory
        )
        
        # 建立 view
        if cog and bot:
            view = LockerPanelView(cog, user_id, thread)
        else:
            view = None
        
        # 嘗試編輯現有訊息
        if message_obj:
            try:
                await message_obj.edit(embed=embed, view=view)
                print(f"✅ [Update Locker Message] 已編輯用戶 {user_id} 的置物櫃訊息")
                return True
            except discord.NotFound:
                print(f"⚠️ [Update Locker Message] 訊息已被刪除，將發送新訊息")
                message_obj = None
            except Exception as e:
                print(f"⚠️ [Update Locker Message] 編輯訊息失敗: {e}")
                message_obj = None
        
        # 若無現有訊息，發送新訊息並更新 DB
        if not message_obj:
            try:
                new_msg = await thread.send(embed=embed, view=view)
                try:
                    set_user_field(user_id, 'locker_message_id', new_msg.id)
                except Exception:
                    pass
                print(f"✅ [Update Locker Message] 已發送新置物櫃訊息給用戶 {user_id}")
                return True
            except Exception as e:
                print(f"❌ [Update Locker Message] 發送新訊息失敗: {e}")
                return False
    
    except Exception as e:
        print(f"❌ [Update Locker Message] 異常: {e}")
        return False
