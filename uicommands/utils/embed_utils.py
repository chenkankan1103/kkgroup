import discord
import json
from typing import Optional
from db_adapter import get_user, get_user_field


def create_progress_bar(current: int, maximum: int, length: int = 10) -> str:
    """創建進度條"""
    if maximum == 0:
        percentage = 0
    else:
        percentage = max(0, min(1, current / maximum))
    filled = int(length * percentage)
    return '█' * filled + '░' * (length - filled)


def _get_growth_stage_emoji(progress: float) -> str:
    """根據進度返回生長階段emoji"""
    if progress >= 95:
        return "🌾"  # 成熟/即將收割
    elif progress >= 75:
        return "🌿"  # 茁壯期
    elif progress >= 50:
        return "🌱"  # 發芽期
    elif progress >= 25:
        return "🌱"  # 嫩芽期
    else:
        return "⚪"  # 初始階段


def _calculate_plant_progress(plant: dict) -> float:
    """計算植物的成長進度百分比"""
    if plant.get("status") == "harvested":
        return 100.0
    
    try:
        from datetime import datetime
        planted_time = plant.get("planted_at", 0)
        matured_time = plant.get("matured_at", 0)
        
        if isinstance(planted_time, str):
            planted_time = datetime.fromisoformat(planted_time).timestamp()
        if isinstance(matured_time, str):
            matured_time = datetime.fromisoformat(matured_time).timestamp()
        
        now = datetime.now().timestamp()
        elapsed = now - planted_time
        total = matured_time - planted_time
        
        progress = min(100, (elapsed / total * 100)) if total > 0 else 0
        return progress
    except Exception:
        return 0.0


def generate_locker_grid(plants, total_slots: int = 5) -> str:
    """生成置物櫃格子視圖"""
    # 轉換植物為網格位置
    plant_positions = {}
    for idx, plant in enumerate(plants):
        if idx < total_slots:
            plant_positions[idx] = plant
    
    # 生成置物櫃視圖
    grid = ""
    for i in range(total_slots):
        if i in plant_positions:
            plant = plant_positions[i]
            progress_percent = _calculate_plant_progress(plant)
            stage_emoji = _get_growth_stage_emoji(progress_percent)
            grid += f"[{stage_emoji}]  "
        else:
            grid += "[⬜]  "
    
    return f"`{grid}`\n位置 1-5"


async def get_plant_progress_info(plant: dict) -> dict:
    """獲取植物的進度詳細信息"""
    from datetime import datetime
    
    try:
        if plant.get("status") == "harvested":
            return {
                'progress': 100.0,
                'stage_name': '已成熟',
                'progress_bar': '█████████████████████ 100%',
                'time_left': '準備收割',
                'fertilizer': plant.get('fertilizer_applied', 0)
            }
        
        planted_time = plant.get("planted_at", 0)
        matured_time = plant.get("matured_at", 0)
        
        if isinstance(planted_time, str):
            planted_time = datetime.fromisoformat(planted_time).timestamp()
        if isinstance(matured_time, str):
            matured_time = datetime.fromisoformat(matured_time).timestamp()
        
        now = datetime.now().timestamp()
        elapsed = now - planted_time
        total = matured_time - planted_time
        progress = min(100, (elapsed / total * 100)) if total > 0 else 0
        
        # 生成進度條
        filled = int(progress / 5)
        empty = 20 - filled
        progress_bar_text = f"{'█' * filled}{'░' * empty} {progress:.0f}%"
        
        # 計算剩餘時間
        remaining = max(0, matured_time - now)
        if remaining > 0:
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            time_left = f"剩餘 {hours}h {mins}m"
        else:
            time_left = "✅ 已成熟"
        
        # 確定生長階段名稱
        if progress >= 75:
            stage_name = "茁壯中 🌿"
        elif progress >= 40:
            stage_name = "發芽中 🌱"
        else:
            stage_name = "嫩芽期 🌱"
        
        return {
            'progress': progress,
            'stage_name': stage_name,
            'progress_bar': progress_bar_text,
            'time_left': time_left,
            'fertilizer': plant.get('fertilizer_applied', 0)
        }
    except Exception as e:
        print(f"⚠️ 計算植物進度失敗: {e}")
        return {
            'progress': 0.0,
            'stage_name': '未知',
            'progress_bar': '░░░░░░░░░░░░░░░░░░░░ 0%',
            'time_left': '未知',
            'fertilizer': 0
        }


async def create_user_embed(cog, user_data: dict, user: discord.User) -> discord.Embed:
    """創建用戶置物櫃embed"""
    embed = discord.Embed(
        title=f"📊 {user.display_name or user.name} 的置物櫃",
        color=0x00ff88,
        timestamp=discord.utils.utcnow()
    )
    
    try:
        embed.set_thumbnail(url=user.display_avatar.url)
    except:
        pass
    
    # 添加角色圖片（優先順序：DB.embed_image_source -> Discord cached URL -> MapleStory API 回退）
    try:
        db_src = None
        try:
            db_src = get_user_field(user_data.get('user_id'), 'embed_image_source', default=None)
        except Exception:
            db_src = None

        if db_src:
            # 優先使用 DB 中儲存的 image source（避免被 cache/其他更新覆寫）
            embed.set_image(url=db_src)
            try:
                embed.add_field(name="image_source", value=f"`{db_src}`", inline=False)
            except Exception:
                pass
        else:
            # 原先邏輯：先使用 Discord cached/upload 的 URL，再回退到 MapleStory API
            character_image_url = await cog.get_character_image_url(user_data)
            if character_image_url:
                embed.set_image(url=character_image_url)
                try:
                    embed.add_field(name="image_source", value=f"`{character_image_url}`", inline=False)
                except Exception:
                    pass
            else:
                try:
                    from .image_utils import build_maplestory_api_url
                    api_url = build_maplestory_api_url(user_data, animated=True)
                    embed.set_image(url=api_url)
                    try:
                        embed.add_field(name="image_source", value=f"`{api_url}`", inline=False)
                    except Exception:
                        pass
                except Exception:
                    pass
    except Exception as e:
        print(f"獲取角色圖片URL失敗: {e}")



    embed.add_field(name="🆔 使用者ID", value=f"`{user_data['user_id']}`", inline=True)
    embed.add_field(name="⭐ 等級", value=f"**{user_data['level'] or 1}**", inline=True)
    embed.add_field(name="✨ 經驗值", value=f"{user_data['xp'] or 0} XP", inline=True)
    embed.add_field(name="💰 金錢", value=f"{user_data['kkcoin'] or 0} KKCoin", inline=True)
    embed.add_field(name="🏆 職位", value=user_data['title'] or '新手', inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    hp = user_data['hp'] or 100
    stamina = user_data['stamina'] or 100
    hp_bar = create_progress_bar(hp, 100)
    stamina_bar = create_progress_bar(stamina, 100)
    embed.add_field(name="❤️ 血量", value=f"{hp_bar} {hp}/100", inline=False)
    embed.add_field(name="⚡ 體力", value=f"{stamina_bar} {stamina}/100", inline=False)

    embed.add_field(name="👔 上身裝備", value=f"ID: {user_data['top']}", inline=True)
    embed.add_field(name="👖 下身裝備", value=f"ID: {user_data['bottom']}", inline=True)
    embed.add_field(name="👟 鞋子", value=f"ID: {user_data['shoes']}", inline=True)
    
    embed.add_field(name="💇 髮型", value=f"ID: {user_data['hair']}", inline=True)
    embed.add_field(name="😊 臉型", value=f"ID: {user_data['face']}", inline=True)
    embed.add_field(name="🎨 膚色", value=f"ID: {user_data['skin']}", inline=True)

    # 合併顯示常規庫存與大麻系統庫存（把兩個合併為單一「物品欄」）
    inventory_lines = []

    # 1) 使用者主庫存（users.inventory，通常是 JSON list）
    try:
        if user_data.get('inventory'):
            items = json.loads(user_data['inventory'])
            if isinstance(items, list) and items:
                inventory_lines.extend(str(i) for i in items[:5])
                if len(items) > 5:
                    inventory_lines.append(f"... 等 {len(items)} 項其他物品")
    except Exception:
        if user_data.get('inventory'):
            inventory_lines.append(str(user_data.get('inventory'))[:100])

    # 2) 大麻系統庫存（若存在則合併）
    try:
        from shop_commands.merchant.cannabis_farming import get_inventory as _get_cannabis_inventory
        from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES

        cannabis_inv = await _get_cannabis_inventory(user_data.get('user_id'))
        # 種子
        for seed_name, qty in (cannabis_inv.get('種子') or {}).items():
            if qty and qty > 0:
                emoji = CANNABIS_SHOP.get('種子', {}).get(seed_name, {}).get('emoji', '🌱')
                inventory_lines.append(f"{emoji} {seed_name} x{qty}")
        # 大麻（收割品）
        for seed_name, qty in (cannabis_inv.get('大麻') or {}).items():
            if qty and qty > 0:
                price = CANNABIS_HARVEST_PRICES.get(seed_name, 0)
                inventory_lines.append(f"💰 {seed_name} x{qty} ({price}/個)")
        # 肥料
        for fert_name, qty in (cannabis_inv.get('肥料') or {}).items():
            if qty and qty > 0:
                emoji = CANNABIS_SHOP.get('肥料', {}).get(fert_name, {}).get('emoji', '🧂')
                inventory_lines.append(f"{emoji} {fert_name} x{qty}")
    except Exception:
        # 若取不到 cannabis 庫存則忽略（保持原樣）
        pass

    # 組合輸出（限制顯示行數以免過長）
    if not inventory_lines:
        inventory = '空的'
    else:
        max_lines = 10
        shown = inventory_lines[:max_lines]
        inventory = '\n'.join(shown)
        if len(inventory_lines) > max_lines:
            inventory += '\n...更多'

    embed.add_field(name="🎒 物品欄", value=inventory, inline=False)
    
    embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
    return embed
