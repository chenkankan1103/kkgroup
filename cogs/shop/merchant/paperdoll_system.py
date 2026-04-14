# shop_commands/merchant/paperdoll_system.py
import discord
import aiohttp
import asyncio
import json
import io
import hashlib
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta

class EnhancedPaperDollSystem:
    def __init__(self, bot):
        self.bot = bot
        self.image_cache = {}  # 簡單的記憶體快取
        self.cache_expiry = {}  # 快取過期時間
        self.api_base_url = "https://maplestory.io/api/character"
        self.default_timeout = 15
        
    def _generate_cache_key(self, user_data: dict, category: str = None, item_id: int = None) -> str:
        """生成快取鍵值"""
        if category and item_id:
            # 為試穿生成特殊鍵值
            temp_data = user_data.copy()
            temp_data[category] = item_id
            key_data = {
                'skin': temp_data.get('skin', 12000),
                'face': temp_data.get('face', 20005),
                'hair': temp_data.get('hair', 30120),
                'top': temp_data.get('top', 1040014),
                'bottom': temp_data.get('bottom', 1060096),
                'shoes': temp_data.get('shoes', 1072005),
                'is_stunned': temp_data.get('is_stunned', 0)
            }
        else:
            key_data = {
                'skin': user_data.get('skin', 12000),
                'face': user_data.get('face', 20005),
                'hair': user_data.get('hair', 30120),
                'top': user_data.get('top', 1040014),
                'bottom': user_data.get('bottom', 1060096),
                'shoes': user_data.get('shoes', 1072005),
                'is_stunned': user_data.get('is_stunned', 0)
            }
        
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """檢查快取是否有效"""
        if cache_key not in self.cache_expiry:
            return False
        return datetime.now() < self.cache_expiry[cache_key]
    
    def _build_character_items(self, user_data: dict) -> List[dict]:
        """構建角色裝備列表 - 支援所有 25 個部件類別"""
        items = [
            {"itemId": 2000, "region": "TWMS", "version": "256"},  # 基礎身體
        ]
        
        # 定義部件優先順序及預設值（避免衝突，如上衣/連身衣不能同時顯示）
        equipment_order = [
            # skin 已從允許清單移除
            ('face', 20005, 'default'),  # face 有 animationName
            ('hair', 30120),
            ('hat', None),               # 帽子（如果有）
            ('overall', 1040014),        # 連身衣（優先於上衣）
            ('top', 1040014),            # 上衣（次優先）
            ('bottom', 1060096),         # 下裝
            ('glove', None),             # 手套
            ('cape', None),              # 斗篷
            ('shoes', 1072005),          # 鞋子
            ('earrings', None),          # 耳環
            ('eye_decoration', None),    # 眼睛裝飾
            ('face_accessory', None),    # 臉部配件
            ('belt', None),              # 腰帶
            ('katara', None),            # 卡塔納
            ('mount', None),             # 坐騎
            ('one_handed_sword', None),  # 單手劍
            ('pendant', None),           # 項鍊
            ('pet_equipment', None),     # 寵物裝備
            ('pet_use', None),           # 寵物用品
            ('pole_arm', None),          # 長柄武器
            ('ring', None),              # 戒指
            ('shield', None),            # 盾牌
            ('shoulder_accessory', None), # 肩膀配件
            ('skill_effect', None),      # 技能效果
        ]
        
        # 構建裝備列表（只包含已設定的項目）
        skip_alternatives = set()  # 跟蹤跳過的替代項
        
        for equipment in equipment_order:
            field_name = equipment[0]
            default_value = equipment[1] if len(equipment) > 1 else None
            item_value = user_data.get(field_name) or default_value
            
            # 檢查衝突（上衣/連身衣）
            if field_name == 'top' and 'overall' in skip_alternatives:
                continue
            if field_name == 'overall' and item_value:
                skip_alternatives.add('top')
            
            if item_value:  # 只在有值時添加
                if field_name == 'face' and len(equipment) > 2:
                    # face 需要 animationName
                    items.append({
                        "itemId": item_value,
                        "animationName": equipment[2],
                        "region": "TWMS",
                        "version": "256"
                    })
                else:
                    items.append({
                        "itemId": item_value,
                        "region": "TWMS",
                        "version": "256"
                    })
        
        # 檢查是否被擊暈，添加眩暈效果道具
        if user_data.get('is_stunned', 0) == 1:
            items.append({"itemId": 1005411, "region": "TWMS", "version": "256"})
        
        return items
    
    def _build_api_url(self, items: List[dict], is_stunned: bool = False) -> str:
        """構建 API URL"""
        item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
        pose = "prone" if is_stunned else "stand1"
        return f"{self.api_base_url}/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"
    
    async def fetch_character_image(self, user_data: dict, use_cache: bool = True) -> Optional[discord.File]:
        """獲取角色圖片（帶快取功能）"""
        cache_key = self._generate_cache_key(user_data)
        
        # 檢查快取
        if use_cache and self._is_cache_valid(cache_key):
            cached_data = self.image_cache.get(cache_key)
            if cached_data:
                return discord.File(io.BytesIO(cached_data), filename='character.png')
        
        try:
            items = self._build_character_items(user_data)
            is_stunned = user_data.get('is_stunned', 0) == 1
            url = self._build_api_url(items, is_stunned)
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.default_timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:  # 確保圖片有效
                            # 儲存到快取
                            if use_cache:
                                self.image_cache[cache_key] = image_data
                                self.cache_expiry[cache_key] = datetime.now() + timedelta(hours=1)
                            
                            return discord.File(io.BytesIO(image_data), filename='character.png')
                    else:
                        print(f"API 請求失敗，狀態碼: {response.status}")
                        
        except asyncio.TimeoutError:
            print("API 請求超時")
        except Exception as e:
            print(f"獲取角色圖片錯誤: {e}")
        
        return None
    
    async def fetch_try_on_image(self, user_data: dict, category: str, item_id: int) -> Optional[discord.File]:
        """獲取試穿圖片"""
        cache_key = self._generate_cache_key(user_data, category, item_id)
        
        # 檢查快取
        if self._is_cache_valid(cache_key):
            cached_data = self.image_cache.get(cache_key)
            if cached_data:
                return discord.File(io.BytesIO(cached_data), filename='try_on.png')
        
        try:
            # 創建試穿數據
            try_on_data = user_data.copy()
            try_on_data[category] = item_id
            
            items = self._build_character_items(try_on_data)
            is_stunned = try_on_data.get('is_stunned', 0) == 1
            url = self._build_api_url(items, is_stunned)
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.default_timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            # 儲存到快取
                            self.image_cache[cache_key] = image_data
                            self.cache_expiry[cache_key] = datetime.now() + timedelta(hours=1)
                            
                            return discord.File(io.BytesIO(image_data), filename='try_on.png')
                    else:
                        print(f"試穿 API 請求失敗，狀態碼: {response.status}")
                        
        except asyncio.TimeoutError:
            print("試穿 API 請求超時")
        except Exception as e:
            print(f"獲取試穿圖片錯誤: {e}")
        
        return None
    
    async def create_comparison_embed(self, interaction: discord.Interaction, user_data: dict, 
                                   item_name: str, item_data: dict, category: str) -> Tuple[discord.Embed, List[discord.File]]:
        """創建對比效果的 embed（當前 vs 試穿）"""
        embed = discord.Embed(
            title=f"👗 試穿對比：{item_name}",
            description=f"{interaction.user.mention} 的試穿效果對比",
            color=discord.Color.purple()
        )
        
        files = []
        
        # 嘗試獲取當前外觀圖片
        current_image = await self.fetch_character_image(user_data)
        if current_image:
            files.append(current_image)
        
        # 嘗試獲取試穿圖片
        item_id = item_data.get("id", item_data.get("item_id", 0))
        try_on_image = await self.fetch_try_on_image(user_data, category, item_id)
        if try_on_image:
            files.append(try_on_image)
        
        # 添加商品資訊
        embed.add_field(name="🎭 試穿商品", value=item_name, inline=True)
        embed.add_field(name="💰 價格", value=f"{item_data['price']} KKcoin", inline=True)
        embed.add_field(name="🏷️ 類別", value=self.get_category_name(category), inline=True)
        
        if len(files) == 2:
            embed.add_field(
                name="📸 對比說明", 
                value="第一張圖：目前外觀\n第二張圖：試穿效果", 
                inline=False
            )
        elif len(files) == 1:
            embed.add_field(
                name="📸 預覽說明", 
                value="顯示試穿後的效果", 
                inline=False
            )
        else:
            embed.add_field(
                name="⚠️ 提示", 
                value="暫時無法生成預覽圖片，但功能正常", 
                inline=False
            )
        
        return embed, files
    
    async def handle_enhanced_try_on(self, interaction: discord.Interaction, item_name: str, 
                                   item_data: dict, category: str, user_data: dict):
        """增強版試穿處理"""
        await interaction.response.defer(ephemeral=True)
        
        # 顯示載入訊息
        loading_embed = discord.Embed(
            title="👗 正在生成試穿效果...",
            description=f"正在為 {interaction.user.mention} 生成 **{item_name}** 的試穿效果！\n\n⏳ 請稍候...",
            color=discord.Color.orange()
        )
        loading_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=loading_embed
        )
        
        try:
            # 添加一點延遲以改善用戶體驗
            await asyncio.sleep(1)
            
            # 創建對比效果
            embed, files = await self.create_comparison_embed(
                interaction, user_data, item_name, item_data, category
            )
            
            # 檢查用戶購買能力
            from .database import get_user_kkcoin
            user_kkcoin = await get_user_kkcoin(interaction.user.id)
            can_afford = user_kkcoin >= item_data['price']
            
            if can_afford:
                embed.add_field(
                    name="💸 購買狀態", 
                    value="✅ 你有足夠的 KKcoin 購買此商品", 
                    inline=False
                )
            else:
                needed = item_data['price'] - user_kkcoin
                embed.add_field(
                    name="💸 購買狀態", 
                    value=f"❌ 還需要 {needed} KKcoin 才能購買", 
                    inline=False
                )
            
            # 創建操作視圖
            from .views import TryOnResultView
            view = TryOnResultView(self, item_name, item_data, category)
            
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view,
                files=files
            )
            
        except Exception as e:
            print(f"增強版試穿功能錯誤: {e}")
            
            # 錯誤處理
            error_embed = discord.Embed(
                title="❌ 試穿功能暫時無法使用",
                description="抱歉，試穿功能目前遇到技術問題。\n你仍然可以查看商品預覽或直接購買。",
                color=discord.Color.red()
            )
            
            # 添加錯誤詳情（僅在開發環境）
            if hasattr(self.bot, 'debug_mode') and self.bot.debug_mode:
                error_embed.add_field(name="錯誤詳情", value=str(e)[:1000], inline=False)
            
            from .views import ItemDetailView
            from .database import get_user_kkcoin
            
            kkcoin = await get_user_kkcoin(interaction.user.id)
            can_afford = kkcoin >= item_data['price']
            view = ItemDetailView(self, item_name, item_data, category, can_afford)
            
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=error_embed,
                view=view
            )
    
    def get_category_name(self, category: str) -> str:
        """獲取分類中文名稱"""
        names = {
            # 基本部件
            "hair": "💇 髮型", 
            "face": "😊 臉型", 
            "skin": "🎨 膚色", 
            "top": "👔 上衣", 
            "bottom": "👖 下裝", 
            "shoes": "👟 鞋子",
            # 新增部件
            "belt": "⏱️ 腰帶",
            "cape": "🌊 斗篷",
            "earrings": "💎 耳環",
            "eye_decoration": "👁️ 眼睛裝飾",
            "face_accessory": "😷 臉部配件",
            "glove": "🧤 手套",
            "hat": "🎩 帽子",
            "katara": "⚔️ 卡塔納",
            "mount": "🐴 坐騎",
            "one_handed_sword": "🗡️ 單手劍",
            "overall": "👗 連身衣",
            "pendant": "💍 項鍊",
            "pet_equipment": "🎀 寵物裝備",
            "pet_use": "🐾 寵物用品",
            "pole_arm": "🎯 長柄武器",
            "ring": "💍 戒指",
            "shield": "🛡️ 盾牌",
            "shoulder_accessory": "🎒 肩膀配件",
            "skill_effect": "✨ 技能效果"
        }
        return names.get(category, category)
    
    def clear_expired_cache(self):
        """清除過期的快取"""
        now = datetime.now()
        expired_keys = [
            key for key, expiry_time in self.cache_expiry.items() 
            if now >= expiry_time
        ]
        
        for key in expired_keys:
            self.image_cache.pop(key, None)
            self.cache_expiry.pop(key, None)
        
        print(f"清除了 {len(expired_keys)} 個過期快取項目")
    
    async def preload_user_image(self, user_data: dict):
        """預載入用戶圖片到快取"""
        try:
            await self.fetch_character_image(user_data, use_cache=True)
        except Exception as e:
            print(f"預載入圖片失敗: {e}")