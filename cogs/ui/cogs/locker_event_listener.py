"""
Locker Event Listener Cog
監聽置物櫃事件，根據事件類型進行局部或完整 embed 更新
"""
import discord
from discord.ext import commands
from typing import Optional

from uicommands.events import (
    EquipmentChangedEvent,
    CurrencyChangedEvent,
    HealthChangedEvent,
    InventoryChangedEvent,
    FullRefreshEvent,
    SyncRequestedEvent,
)
from db_adapter import get_user, set_user_field, get_user_field
from uicommands.utils.locker_cache import locker_cache


class LockerEventListenerCog(commands.Cog):
    """置物櫃事件監聽器"""
    
    def __init__(self, bot, user_panel_cog):
        """
        Args:
            bot: Discord bot instance
            user_panel_cog: UserPanel cog 實例（提供 create_user_embed、get_character_image_url 等方法）
        """
        self.bot = bot
        self.cog = user_panel_cog
        self.FORUM_CHANNEL_ID = user_panel_cog.FORUM_CHANNEL_ID
    
    async def _get_locker_message(self, user_id: int) -> Optional[discord.Message]:
        """
        根據 user_id 從資料庫取得 locker_message_id，
        進而 fetch Discord 訊息物件
        """
        locker_message_id = get_user_field(user_id, 'locker_message_id')
        thread_id = get_user_field(user_id, 'thread_id')
        
        if not locker_message_id or not thread_id:
            return None
        
        try:
            thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
            if not thread or not isinstance(thread, discord.Thread):
                return None
            
            message = await thread.fetch_message(locker_message_id)
            return message
        except discord.NotFound:
            # 訊息已被刪除，清除 DB 紀錄
            set_user_field(user_id, 'locker_message_id', None)
            return None
        except Exception as e:
            print(f"⚠️ [LockerEventListener] 無法取得 locker message: {e}")
            return None
    
    async def _render_summary_embed(self, user_data: dict, user_obj: discord.User) -> discord.Embed:
        """
        生成 Summary Embed
        包含：ID、等級、KK幣、血量、體力、職稱等文字資訊
        不包含紙娃娃圖片
        """
        embed = await self.cog.create_user_embed(user_data, user_obj)
        # 移除圖片設定（紙娃娃由 appearance embed 負責）
        if embed.image:
            embed.set_image(url=None)
        return embed
    
    async def _render_appearance_embed(self, user_data: dict, user_obj: discord.User) -> discord.Embed:
        """
        生成 Appearance Embed
        包含：紙娃娃圖片 + 全部裝備格子
        """
        embed = discord.Embed(
            title=f"📦 {user_obj.display_name or user_obj.name} - 裝備",
            color=0x9933ff,
        )
        
        # 設定紙娃娃圖片（使用快取）
        paperdoll_image_url = await locker_cache.get_paperdoll_image(user_data)
        if paperdoll_image_url:
            embed.set_image(url=paperdoll_image_url)
        
        # 添加裝備資訊欄位
        equip_text = self._format_equipment_fields(user_data)
        embed.add_field(name="🎽 裝備", value=equip_text, inline=False)
        
        return embed
    
    @staticmethod
    def _format_equipment_fields(user_data: dict) -> str:
        """
        格式化裝備欄位為可讀的文字
        例：武器: 劍 (ID: 1234), 頭盔: 王冠 (ID: 5678) ...
        """
        equip_slots = [
            ("武器", 0),
            ("頭盔", 1),
            ("上衣", 2),
            ("褲子", 3),
            ("靴子", 4),
            ("手套", 5),
            ("腰帶", 6),
            ("肩甲", 7),
            ("戒指", 8),
            ("項鍊", 9),
        ]
        
        lines = []
        for slot_name, slot_idx in equip_slots:
            equip_key = f'equip_{slot_idx}'
            equip_id = user_data.get(equip_key)
            if equip_id:
                lines.append(f"• {slot_name}: `{equip_id}`")
            else:
                lines.append(f"• {slot_name}: 無")
        
        return '\n'.join(lines) if lines else "無裝備"
    
    # ──────────────────────────────────────
    # 事件監聽器方法
    # ──────────────────────────────────────
    
    @commands.Cog.listener()
    async def on_equipment_changed(self, event: EquipmentChangedEvent):
        """
        裝備更新事件監聽器
        
        觸發：
        - 紙娃娃 hash 改變 → 重新請求 MapleStory API
        - 更新 appearance embed 及紙娃娃圖片
        """
        try:
            user_data = get_user(event.user_id)
            if not user_data:
                return
            
            message = await self._get_locker_message(event.user_id)
            if not message:
                print(f"⚠️ [EquipmentChangedEvent] 找不到 locker message for user {event.user_id}")
                return
            
            try:
                user_obj = self.bot.get_user(event.user_id) or await self.bot.fetch_user(event.user_id)
            except:
                return
            
            # 生成新的 appearance embed
            appearance_embed = await self._render_appearance_embed(user_data, user_obj)
            
            # 編輯訊息（更新 embeds[1] 或新增）
            current_embeds = list(message.embeds) if message.embeds else []
            
            # 若現在只有 1 個 embed，表示還未拆分 → 新增第二個 embed
            if len(current_embeds) == 1:
                current_embeds.append(appearance_embed)
            else:
                # 若已有 2 個 embed，更新第二個
                current_embeds[1] = appearance_embed
            
            await message.edit(embeds=current_embeds)
            print(f"✅ [EquipmentChangedEvent] 已更新 user {event.user_id} 的裝備 embed")
        
        except Exception as e:
            print(f"❌ [EquipmentChangedEvent] 錯誤: {e}")
    
    @commands.Cog.listener()
    async def on_currency_changed(self, event: CurrencyChangedEvent):
        """
        KK幣/經驗值更新事件監聽器
        
        觸發：
        - 只更新 summary embed 的 KK幣/經驗值欄位
        - 不涉及圖片、不請求 API
        """
        try:
            user_data = get_user(event.user_id)
            if not user_data:
                return
            
            message = await self._get_locker_message(event.user_id)
            if not message:
                return
            
            try:
                user_obj = self.bot.get_user(event.user_id) or await self.bot.fetch_user(event.user_id)
            except:
                return
            
            # 生成新的 summary embed（只包含文字欄位）
            summary_embed = await self._render_summary_embed(user_data, user_obj)
            
            # 編輯訊息（更新 embeds[0]）
            current_embeds = list(message.embeds) if message.embeds else []
            if len(current_embeds) >= 1:
                current_embeds[0] = summary_embed
            else:
                current_embeds = [summary_embed]
            
            await message.edit(embeds=current_embeds)
            print(f"✅ [CurrencyChangedEvent] 已更新 user {event.user_id} 的 KK幣/經驗")
        
        except Exception as e:
            print(f"❌ [CurrencyChangedEvent] 錯誤: {e}")
    
    @commands.Cog.listener()
    async def on_health_changed(self, event: HealthChangedEvent):
        """
        血量/體力更新事件監聽器
        
        觸發：
        - 只更新 summary embed 的進度條欄位
        """
        try:
            user_data = get_user(event.user_id)
            if not user_data:
                return
            
            message = await self._get_locker_message(event.user_id)
            if not message:
                return
            
            try:
                user_obj = self.bot.get_user(event.user_id) or await self.bot.fetch_user(event.user_id)
            except:
                return
            
            # 生成新的 summary embed
            summary_embed = await self._render_summary_embed(user_data, user_obj)
            
            # 編輯訊息（更新 embeds[0]）
            current_embeds = list(message.embeds) if message.embeds else []
            if len(current_embeds) >= 1:
                current_embeds[0] = summary_embed
            else:
                current_embeds = [summary_embed]
            
            await message.edit(embeds=current_embeds)
            print(f"✅ [HealthChangedEvent] 已更新 user {event.user_id} 的血量/體力")
        
        except Exception as e:
            print(f"❌ [HealthChangedEvent] 錯誤: {e}")
    
    @commands.Cog.listener()
    async def on_inventory_changed(self, event: InventoryChangedEvent):
        """
        物品欄更新事件監聽器
        
        觸發：
        - 只更新 summary embed 的物品欄資訊
        """
        # TODO: 實作物品欄更新邏輯
        print(f"📌 [InventoryChangedEvent] user {event.user_id} 物品欄已更新")
    
    @commands.Cog.listener()
    async def on_full_refresh(self, event: FullRefreshEvent):
        """
        完整刷新事件監聽器
        
        觸發：
        - 清除該使用者的紙娃娃快取
        - 重新生成 summary + appearance embeds
        - 同時更新兩個 embeds
        """
        try:
            user_data = get_user(event.user_id)
            if not user_data:
                return
            
            message = await self._get_locker_message(event.user_id)
            if not message:
                return
            
            try:
                user_obj = self.bot.get_user(event.user_id) or await self.bot.fetch_user(event.user_id)
            except:
                return
            
            # 強制清除快取
            paperdoll_hash = locker_cache.build_paperdoll_hash(user_data)
            locker_cache.invalidate_hash(paperdoll_hash)
            
            # 生成新的 embeds
            summary_embed = await self._render_summary_embed(user_data, user_obj)
            appearance_embed = await self._render_appearance_embed(user_data, user_obj)
            
            # 編輯訊息
            await message.edit(embeds=[summary_embed, appearance_embed])
            print(f"✅ [FullRefreshEvent] 已完整刷新 user {event.user_id}")
        
        except Exception as e:
            print(f"❌ [FullRefreshEvent] 錯誤: {e}")
    
    @commands.Cog.listener()
    async def on_sync_requested(self, event: SyncRequestedEvent):
        """
        同步請求事件監聽器
        
        觸發：
        - 檢查資料庫中的資料是否有變更
        - 若有變更，觸發對應的更新事件
        """
        # TODO: 實作增量同步邏輯
        # 可能需要檢查 DB 中的 last_* 欄位，比對 message 中的值
        print(f"📌 [SyncRequestedEvent] user {event.user_id} 同步請求")


async def setup(bot):
    """從 uibody.py 中呼叫 await bot.add_cog(LockerEventListenerCog(...))"""
    # 此函數由主 Cog 載入時呼叫
    pass
