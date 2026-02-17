import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
import random
import json
import io
from typing import Optional
from utils.persona import build_persona_prompt, analyze_tone
from utils.memory import add_to_history, get_history
from dotenv import load_dotenv
import logging

# 匯入新的 DB 適配層
from db_adapter import get_user, set_user_field, get_user_field

load_dotenv()

AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gpt-3.5-turbo")
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID", 0))
PUNISHMENT_CHANNEL_ID = int(os.getenv("PUNISHMENT_CHANNEL_ID", 0))

# 設置日誌記錄
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Ai(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.punishment_tasks = {}
        self.punishment_messages = {}  # 存储用戶專屬的懲罰消息ID
        self.admin_notification_messages = {}  # 存储管理員通知消息ID
        self.cached_punishment_images = {}  # 缓存惩罚状态图片
        
        # 預設的眩晕状态图片配置
        self.punishment_presets = {
            'male_stunned': {
                'skin': 12000, 'face': 20005, 'hair': 30120,
                'top': 1040014, 'bottom': 1060096, 'shoes': 1072005,
                'pose': 'prone', 'face_animation': 'stunned'
            },
            'female_stunned': {
                'skin': 12000, 'face': 21731, 'hair': 34410,
                'top': 1041004, 'bottom': 1061008, 'shoes': 1072005,
                'pose': 'prone', 'face_animation': 'stunned'
            },
            'male_normal': {
                'skin': 12000, 'face': 20005, 'hair': 30120,
                'top': 1040014, 'bottom': 1060096, 'shoes': 1072005,
                'pose': 'stand1', 'face_animation': 'default'
            },
            'female_normal': {
                'skin': 12000, 'face': 21731, 'hair': 34410,
                'top': 1041004, 'bottom': 1061008, 'shoes': 1072005,
                'pose': 'stand1', 'face_animation': 'default'
            }
        }

    def get_user_data(self, user_id: int) -> dict:
        """從資料庫獲取使用者資料"""
        try:
            user_data = get_user(user_id)
            return user_data if user_data else {}
        except Exception as e:
            logger.error(f"獲取使用者資料錯誤: {e}")
            return {}

    def update_user_stats(self, user_id: int, hp_damage: int = 0, stamina_damage: int = 0) -> dict:
        """更新使用者的HP和體力值"""
        try:
            # 獲取當前值
            current_hp = get_user_field(user_id, 'hp', default=100)
            current_stamina = get_user_field(user_id, 'stamina', default=100)
            
            # 計算新值
            new_hp = max(0, current_hp - hp_damage)
            new_stamina = max(0, current_stamina - stamina_damage)
            
            # 更新到 DB
            set_user_field(user_id, 'hp', new_hp)
            set_user_field(user_id, 'stamina', new_stamina)
            
            return {
                'hp': new_hp, 
                'stamina': new_stamina, 
                'old_hp': current_hp, 
                'old_stamina': current_stamina
            }
        except Exception as e:
            logger.error(f"更新使用者數據資料庫錯誤: {e}")
            return {}
        except Exception as e:
            logger.error(f"更新使用者數據錯誤: {e}")
            return {}

    def steal_user_items(self, user_id: int) -> dict:
        """偷取使用者財物 - 包含 KKCoin 和物品"""
        try:
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            
            # 獲取當前資料 - 確保欄位存在
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # 檢查必要欄位是否存在
            has_kkcoin = 'kkcoin' in columns
            has_inventory = 'inventory' in columns
            
            if not has_kkcoin and not has_inventory:
                conn.close()
                logger.warning(f"使用者 {user_id} 沒有 kkcoin 或 inventory 欄位")
                return {}
            
            # 構建查詢語句
            select_fields = []
            if has_kkcoin:
                select_fields.append('kkcoin')
            if has_inventory:
                select_fields.append('inventory')
            
            if not select_fields:
                conn.close()
                return {}
            
            query = f"SELECT {', '.join(select_fields)} FROM users WHERE user_id = ?"
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                logger.warning(f"找不到使用者 {user_id} 的資料")
                return {}
            
            # 解析資料
            current_coins = 0
            inventory = []
            
            if has_kkcoin and has_inventory:
                current_coins, inventory_str = result
            elif has_kkcoin:
                current_coins = result[0]
                inventory_str = None
            elif has_inventory:
                current_coins = 0
                inventory_str = result[0]
            else:
                inventory_str = None
            
            # 安全解析 inventory JSON
            if inventory_str:
                try:
                    if isinstance(inventory_str, str):
                        inventory = json.loads(inventory_str)
                    elif isinstance(inventory_str, list):
                        inventory = inventory_str
                    else:
                        inventory = []
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"使用者 {user_id} inventory JSON 解析失敗: {e}, 原始資料: {inventory_str}")
                    inventory = []
            
            # 確保 inventory 是列表
            if not isinstance(inventory, list):
                inventory = []
            
            stolen_items = []
            stolen_coins = 0
            
            # 偷取 KKCoin (5-10%)
            if has_kkcoin and current_coins > 0:
                try:
                    steal_percentage = random.uniform(0.05, 0.1)
                    stolen_coins = max(1, int(current_coins * steal_percentage))  # 至少偷 1 個
                    new_coins = max(0, current_coins - stolen_coins)
                except Exception as e:
                    logger.warning(f"計算偷取金幣錯誤: {e}")
                    stolen_coins = 0
                    new_coins = current_coins
            else:
                new_coins = current_coins
            
            # 偷取物品 (隨機0-2個，避免空列表錯誤)
            if has_inventory and inventory and len(inventory) > 0:
                try:
                    # 過濾掉空值和無效項目
                    valid_inventory = [item for item in inventory if item and str(item).strip()]
                    
                    if valid_inventory:
                        steal_count = min(random.randint(0, 2), len(valid_inventory))
                        if steal_count > 0:
                            stolen_items = random.sample(valid_inventory, steal_count)
                            # 從原始 inventory 中移除被偷的物品
                            for item in stolen_items:
                                if item in inventory:
                                    inventory.remove(item)
                except Exception as e:
                    logger.warning(f"偷取物品錯誤: {e}")
                    stolen_items = []
            
            # 更新資料庫 - 只更新存在的欄位
            update_fields = []
            update_values = []
            
            if has_kkcoin:
                update_fields.append("kkcoin = ?")
                update_values.append(new_coins)
            
            if has_inventory:
                update_fields.append("inventory = ?")
                try:
                    inventory_json = json.dumps(inventory, ensure_ascii=False)
                    update_values.append(inventory_json)
                except Exception as e:
                    logger.warning(f"序列化 inventory 失敗: {e}")
                    update_values.append(json.dumps([]))
            
            if update_fields:
                update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = ?"
                update_values.append(user_id)
                cursor.execute(update_query, tuple(update_values))
                conn.commit()
            
            conn.close()
            
            result = {
                'stolen_coins': stolen_coins,
                'stolen_items': stolen_items,
                'remaining_coins': new_coins,
                'remaining_items': inventory
            }
            
            logger.info(f"偷取完成 - 使用者: {user_id}, 偷取金幣: {stolen_coins}, 偷取物品: {len(stolen_items)}個")
            return result
            
        except sqlite3.Error as e:
            logger.error(f"偷取物品資料庫錯誤: {e}")
            return {}
        except Exception as e:
            logger.error(f"偷取物品未知錯誤: {e}")
            return {}

    async def generate_punishment_character_image(self, user_data: dict, is_stunned: bool = True) -> Optional[str]:
        """生成懲罰狀態的角色圖片"""
        try:
            gender = user_data.get('gender', 'male')
            preset_key = f"{gender}_{'stunned' if is_stunned else 'normal'}"
            
            # 檢查緩存
            if preset_key in self.cached_punishment_images:
                return self.cached_punishment_images[preset_key]
            
            preset = self.punishment_presets.get(preset_key)
            if not preset:
                return None
            
            # 使用用戶的外觀數據，但應用懲罰狀態的姿勢和面部動畫
            items = [
                {"itemId": 2000, "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('skin', preset['skin']), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('face', preset['face']), "animationName": preset['face_animation'], "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('hair', preset['hair']), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('top', preset['top']), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('bottom', preset['bottom']), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('shoes', preset['shoes']), "region": "TWMS", "version": "256"}
            ]
            
            # 如果是眩晕状态，添加眩晕效果
            if is_stunned:
                items.append({"itemId": 1005411, "region": "TWMS", "version": "256"})
            
            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            api_url = f"https://maplestory.io/api/character/{item_path}/{preset['pose']}/animated?showears=false&resize=2&flipX=true"
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            # 上传到Discord存储
                            discord_url = await self.upload_punishment_image_to_storage(image_data, preset_key)
                            if discord_url:
                                self.cached_punishment_images[preset_key] = discord_url
                                return discord_url
        
        except Exception as e:
            logger.error(f"生成懲罰角色圖片錯誤: {e}")
        
        return None

    async def upload_punishment_image_to_storage(self, image_data: bytes, cache_key: str) -> Optional[str]:
        """上傳懲罰圖片到Discord存儲"""
        try:
            if PUNISHMENT_CHANNEL_ID == 0:
                logger.warning("懲罰頻道 ID 未設置")
                return None
                
            channel = self.bot.get_channel(PUNISHMENT_CHANNEL_ID)
            if not channel:
                logger.error(f"找不到懲罰頻道 ID: {PUNISHMENT_CHANNEL_ID}")
                return None
            
            file_obj = discord.File(
                io.BytesIO(image_data), 
                filename=f'punishment_{cache_key}.gif'
            )
            
            # 發送圖片到存儲頻道並立即刪除消息，只保留URL
            temp_msg = await channel.send(file=file_obj)
            
            if temp_msg.attachments:
                discord_url = temp_msg.attachments[0].url
                
                try:
                    await asyncio.sleep(0.1)
                    await temp_msg.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    logger.warning("沒有權限刪除臨時訊息")
                
                return discord_url
        
        except Exception as e:
            logger.error(f"上傳懲罰圖片錯誤: {e}")
        
        return None

    def create_admin_notification_embed(self, member: discord.Member) -> discord.Embed:
        """創建管理員通知 Embed"""
        embed = discord.Embed(
            title="🚨 禁閉室收容通知",
            description=f"**{member.display_name}** (`{member.mention}`) 已被幹部抓進禁閉室",
            color=0xff4444
        )
        
        embed.add_field(
            name="👤 收容對象",
            value=f"{member.display_name}\n`ID: {member.id}`",
            inline=True
        )
        
        embed.add_field(
            name="📅 收容時間",
            value=f"<t:{int(asyncio.get_event_loop().time())}:F>",
            inline=True
        )
        
        embed.add_field(
            name="⚡ 狀態",
            value="🔴 **正在進行私人制裁**\n懲罰進度將持續更新",
            inline=False
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="禁閉室收容通知")
        
        return embed

    def create_punishment_embed(self, member: discord.Member, user_data: dict, damage_info: dict, attack_message: str, theft_info: dict = None) -> discord.Embed:
        """創建懲罰狀態的 Embed"""
        # 根據HP狀態決定顏色
        if damage_info.get('hp', 100) <= 0:
            color = 0xff0000  # 紅色 - 重傷
        elif damage_info.get('hp', 100) <= 30:
            color = 0xff8800  # 橙色 - 危險
        elif damage_info.get('hp', 100) <= 60:
            color = 0xffff00  # 黃色 - 警告
        else:
            color = 0x00ff00  # 綠色 - 安全

        embed = discord.Embed(
            title="🚨 禁閉懲罰進行中 🚨",
            description=f"**{member.display_name}** 正在接受幹部的制裁...",
            color=color
        )

        # 狀態欄
        hp_bar = self.create_health_bar(damage_info.get('hp', 100), 100)
        stamina_bar = self.create_health_bar(damage_info.get('stamina', 100), 100)
        
        embed.add_field(
            name="❤️ 生命值",
            value=f"{hp_bar} `{damage_info.get('hp', 100)}/100`",
            inline=False
        )
        
        embed.add_field(
            name="⚡ 體力值", 
            value=f"{stamina_bar} `{damage_info.get('stamina', 100)}/100`",
            inline=False
        )

        # 傷害訊息
        if damage_info.get('old_hp', 100) > damage_info.get('hp', 100):
            hp_damage = damage_info.get('old_hp', 100) - damage_info.get('hp', 100)
            embed.add_field(
                name="💥 造成傷害",
                value=f"生命值 -{hp_damage}",
                inline=True
            )
            
        if damage_info.get('old_stamina', 100) > damage_info.get('stamina', 100):
            stamina_damage = damage_info.get('old_stamina', 100) - damage_info.get('stamina', 100)
            embed.add_field(
                name="😵 體力耗盡",
                value=f"體力值 -{stamina_damage}",
                inline=True
            )

        # AI羞辱訊息 - 截斷過長的訊息
        if len(attack_message) > 1000:
            attack_message = attack_message[:997] + "..."
            
        embed.add_field(
            name="🦹‍♂️ 幹部人員訊息",
            value=f"*{attack_message}*",
            inline=False
        )

        # 如果有偷取財物的訊息
        if theft_info and (theft_info.get('stolen_coins', 0) > 0 or theft_info.get('stolen_items', [])):
            theft_text = "🦹‍♂️ **幹部偷取行為：**\n"
            
            if theft_info.get('stolen_coins', 0) > 0:
                theft_text += f"💰 偷取了 {theft_info['stolen_coins']} KKCoin\n"
            
            stolen_items = theft_info.get('stolen_items', [])
            if stolen_items and len(stolen_items) > 0:
                # 安全處理物品名稱顯示
                try:
                    stolen_items_display = []
                    for item in stolen_items[:3]:  # 最多顯示3個
                        if item and str(item).strip():
                            stolen_items_display.append(str(item).strip())
                    
                    if stolen_items_display:
                        stolen_items_str = ', '.join(stolen_items_display)
                        if len(stolen_items) > 3:
                            stolen_items_str += f"... 等{len(stolen_items)}項"
                        theft_text += f"🎒 偷取物品: {stolen_items_str}\n"
                except Exception as e:
                    logger.warning(f"處理偷取物品顯示錯誤: {e}")
                    theft_text += f"🎒 偷取了 {len(stolen_items)} 個物品\n"
            
            theft_text += f"💸 剩餘金錢: {theft_info.get('remaining_coins', 0)} KKCoin"
            
            embed.add_field(
                name="🚨 財物損失警報",
                value=theft_text,
                inline=False
            )

        # 狀態提示
        if damage_info.get('hp', 100) <= 0 and damage_info.get('stamina', 100) <= 0:
            embed.add_field(
                name="💀 完全虛脫狀態",
                value="生命值和體力值都歸零！幹部們開始覬覦你的財物！",
                inline=False
            )
        elif damage_info.get('hp', 100) <= 0:
            embed.add_field(
                name="💀 重傷狀態",
                value="生命值歸零！開始消耗體力值！",
                inline=False
            )
        
        embed.set_footer(text=f"禁閉室懲罰：每分鐘更新 | {member.display_name}")
        
        return embed

    def create_health_bar(self, current: int, maximum: int, length: int = 20) -> str:
        """創建血條顯示"""
        if maximum <= 0:
            return "▱" * length
            
        percentage = max(0, min(1, current / maximum))  # 確保在 0-1 範圍內
        filled_length = int(length * percentage)
        
        if percentage > 0.6:
            bar_char = "▰"  # 綠色滿血條
        elif percentage > 0.3:
            bar_char = "▰"  # 黃色警告
        else:
            bar_char = "▰"  # 紅色危險
            
        empty_char = "▱"
        
        return bar_char * filled_length + empty_char * (length - filled_length)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """監聽成員更新事件（角色變化）"""
        try:
            if MUTE_ROLE_ID == 0:
                logger.warning("MUTE_ROLE_ID 未設置或為0，跳過角色檢查")
                return
                
            # 檢查是否被添加了禁言角色
            if MUTE_ROLE_ID in [role.id for role in after.roles] and MUTE_ROLE_ID not in [role.id for role in before.roles]:
                logger.info(f"檢測到 {after.display_name} 被添加禁言角色，開始懲罰")
                await self.start_punishment(after)
            # 檢查是否被移除了禁言角色  
            elif MUTE_ROLE_ID not in [role.id for role in after.roles] and MUTE_ROLE_ID in [role.id for role in before.roles]:
                logger.info(f"檢測到 {after.display_name} 被移除禁言角色，停止懲罰")
                await self.stop_punishment(after)
        except Exception as e:
            logger.error(f"成員更新事件錯誤: {e}")

    async def start_punishment(self, member: discord.Member):
        """開始懲罰流程"""
        try:
            if member.id in self.punishment_tasks:
                logger.info(f"{member.display_name} 的懲罰任務已存在，跳過")
                return
            
            logger.info(f"開始為 {member.display_name} 設置懲罰")
            
            # 檢查配置
            if PUNISHMENT_CHANNEL_ID == 0:
                logger.error("PUNISHMENT_CHANNEL_ID 未設置，無法發送懲罰訊息")
                return
                
            # 先設置眩暈狀態 - 使用 db_adapter
            try:
                set_user_field(member.id, 'is_stunned', 1)
                logger.info(f"已設置 {member.display_name} 的眩暈狀態")
            except Exception as e:
                logger.error(f"設置眩暈狀態失敗: {e}")
            
            # 在禁閉室頻道發送管理員通知
            punishment_channel = self.bot.get_channel(PUNISHMENT_CHANNEL_ID)
            if punishment_channel:
                try:
                    admin_embed = self.create_admin_notification_embed(member)
                    admin_message = await punishment_channel.send(embed=admin_embed)
                    self.admin_notification_messages[member.id] = admin_message.id
                    logger.info(f"已發送管理員通知給 {member.display_name}")
                except Exception as e:
                    logger.error(f"發送管理員通知失敗: {e}")
            else:
                logger.error(f"找不到懲罰頻道 ID: {PUNISHMENT_CHANNEL_ID}")
            
            # 創建懲罰任務
            self.punishment_tasks[member.id] = self.bot.loop.create_task(self.send_punishment(member))
            logger.info(f"開始懲罰任務：{member.display_name} ({member.id})")
            
        except Exception as e:
            logger.error(f"開始懲罰錯誤: {e}")

    async def stop_punishment(self, member: discord.Member):
        """停止懲罰並恢復正常狀態"""
        try:
            if member.id in self.punishment_tasks:
                self.punishment_tasks[member.id].cancel()
                del self.punishment_tasks[member.id]
                logger.info(f"停止懲罰任務：{member.display_name} ({member.id})")
            
            # 恢復正常狀態 - 使用 db_adapter
            try:
                set_user_field(member.id, 'is_stunned', 0)
                logger.info(f"已恢復 {member.display_name} 的正常狀態")
            except Exception as e:
                logger.error(f"恢復正常狀態失敗: {e}")
            
            if PUNISHMENT_CHANNEL_ID == 0:
                return
                
            punishment_channel = self.bot.get_channel(PUNISHMENT_CHANNEL_ID)
            if not punishment_channel:
                return
            
            # 更新管理員通知訊息
            if member.id in self.admin_notification_messages:
                try:
                    admin_message_id = self.admin_notification_messages[member.id]
                    admin_message = await punishment_channel.fetch_message(admin_message_id)
                    
                    # 更新管理員通知為釋放狀態
                    release_embed = discord.Embed(
                        title="✅ 禁閉室釋放通知",
                        description=f"**{member.display_name}** 已從禁閉室釋放",
                        color=0x00ff00
                    )
                    
                    release_embed.add_field(
                        name="👤 釋放對象",
                        value=f"{member.display_name}\n`ID: {member.id}`",
                        inline=True
                    )
                    
                    release_embed.add_field(
                        name="📅 釋放時間",
                        value=f"<t:{int(asyncio.get_event_loop().time())}:F>",
                        inline=True
                    )
                    
                    release_embed.add_field(
                        name="⚡ 狀態",
                        value="🟢 **已恢復正常**\n懲罰已結束",
                        inline=False
                    )
                    
                    release_embed.set_thumbnail(url=member.display_avatar.url)
                    release_embed.set_footer(text="釋放通知")
                    
                    await admin_message.edit(embed=release_embed)
                    
                except (discord.NotFound, discord.Forbidden) as e:
                    logger.warning(f"無法編輯管理員通知訊息: {e}")
                
                del self.admin_notification_messages[member.id]
            
            # 清理用戶懲罰訊息
            if member.id in self.punishment_messages:
                try:
                    punishment_message_id = self.punishment_messages[member.id]
                    punishment_message = await punishment_channel.fetch_message(punishment_message_id)
                    
                    # 發送恢復訊息
                    user_data = self.get_user_data(member.id)
                    recovery_image_url = await self.generate_punishment_character_image(user_data, is_stunned=False)
                    
                    recovery_embed = discord.Embed(
                        title="✨ 懲罰結束",
                        description=f"**{member.display_name}** 已從禁閉中釋放，恢復正常狀態！",
                        color=0x00ff00
                    )
                    
                    recovery_embed.set_footer(text=f"禁閉室釋放通知 | {member.display_name}")
                    
                    if recovery_image_url:
                        recovery_embed.set_image(url=recovery_image_url)
                    
                    await punishment_message.edit(embed=recovery_embed)
                    
                except (discord.NotFound, discord.Forbidden) as e:
                    logger.warning(f"無法編輯懲罰訊息: {e}")
                
                del self.punishment_messages[member.id]
                
        except Exception as e:
            logger.error(f"停止懲罰錯誤: {e}")

    async def send_punishment(self, member: discord.Member):
        """在禁閉室頻道發送懲罰訊息並定期更新"""
        persona_prompt = build_persona_prompt(bot_name="KK園區中控室", tone="嚴厲")
        
        # 預設的羞辱話語模板
        punishment_templates = [
            f"請用一句帶著譏諷和鄙視的話，嘲笑 {member.display_name} 因為行為不當被私人禁閉，血量正在下降。",
            f"請用一句充滿嘲弄的話，諷刺 {member.display_name} 這種水準居然還敢在群裡亂來，現在被私下攻擊活該。",
            f"請用一句輕蔑且帶點挖苦的話，告訴 {member.display_name} 這就是不守規矩的下場，繼續在私下失血吧。",
            f"請用一句帶著冷嘲熱諷的話，羞辱 {member.display_name} 連基本禮貌都不懂，現在私下嚐到痛苦了。",
            f"請用一句嘲諷且帶點瞧不起的話，告誡 {member.display_name} 這種行為的代價就是私下持續受傷。"
        ]

        if PUNISHMENT_CHANNEL_ID == 0:
            logger.error("懲罰頻道 ID 未設置")
            return

        punishment_channel = self.bot.get_channel(PUNISHMENT_CHANNEL_ID)
        if not punishment_channel:
            logger.error(f"找不到懲罰頻道: {PUNISHMENT_CHANNEL_ID}")
            return

        punishment_message = None
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                while MUTE_ROLE_ID in [role.id for role in member.roles]:
                    try:
                        # 檢查任務是否被取消
                        if asyncio.current_task().cancelled():
                            break
                            
                        # 獲取使用者資料
                        user_data = self.get_user_data(member.id)
                        if not user_data:
                            logger.warning(f"找不到使用者資料: {member.id}")
                            # 使用預設值
                            user_data = {'hp': 100, 'stamina': 100, 'gender': 'male'}
                        
                        # 計算傷害
                        current_hp = user_data.get('hp', 100)
                        current_stamina = user_data.get('stamina', 100)
                        
                        hp_damage = 5 if current_hp > 0 else 0
                        stamina_damage = 10 if current_hp <= 0 else 0
                        
                        # 更新數值
                        damage_info = self.update_user_stats(member.id, hp_damage, stamina_damage)
                        if not damage_info:
                            # 如果更新失敗，使用當前值
                            damage_info = {
                                'hp': max(0, current_hp - hp_damage),
                                'stamina': max(0, current_stamina - stamina_damage),
                                'old_hp': current_hp,
                                'old_stamina': current_stamina
                            }
                        
                        # 檢查是否需要偷取財物 - 添加額外檢查
                        theft_info = None
                        try:
                            if damage_info.get('hp', 100) <= 0 and damage_info.get('stamina', 100) <= 0:
                                theft_info = self.steal_user_items(member.id)
                                if theft_info:
                                    logger.info(f"偷取財物成功: {member.display_name}, 金幣: {theft_info.get('stolen_coins', 0)}, 物品: {len(theft_info.get('stolen_items', []))}")
                        except Exception as e:
                            logger.warning(f"偷取財物失敗: {e}")
                            theft_info = None
                        
                        # 隨機選擇一個模板
                        template = random.choice(punishment_templates)
                        attack_message = ""
                        
                        # 嘗試獲取 AI 回應
                        if AI_API_KEY and AI_API_URL:
                            try:
                                headers = {
                                    "Authorization": f"Bearer {AI_API_KEY}",
                                    "Content-Type": "application/json"
                                }
                                payload = {
                                    "model": AI_API_MODEL,
                                    "messages": [
                                        {"role": "system", "content": persona_prompt},
                                        {"role": "user", "content": template}
                                    ]
                                }
                                
                                async with session.post(AI_API_URL, headers=headers, json=payload) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        if "choices" in data and len(data["choices"]) > 0:
                                            attack_message = data["choices"][0]["message"]["content"].strip()
                                    else:
                                        logger.warning(f"AI API 回應狀態: {resp.status}")
                                        
                            except Exception as e:
                                logger.warning(f"AI API 請求錯誤: {e}")
                        
                        # 如果 AI 回應失敗，使用備用回應
                        if not attack_message:
                            backup_responses = [
                                f"{member.display_name} 血量下降中，這就是作亂的代價。",
                                f"{member.display_name} 感受痛苦吧，這是你應得的懲罰。",
                                f"{member.display_name} 每一滴血都在私下提醒你的愚蠢。",
                                f"{member.display_name} 現在私下知道疼了？太遲了。",
                                f"{member.display_name} 在禁閉中繼續受苦吧。"
                            ]
                            attack_message = random.choice(backup_responses)

                        # 創建用戶專屬 Embed
                        embed = self.create_punishment_embed(member, user_data, damage_info, attack_message, theft_info)
                        
                        # 獲取眩暈狀態角色圖片
                        try:
                            character_image_url = await self.generate_punishment_character_image(user_data, is_stunned=True)
                            if character_image_url:
                                embed.set_image(url=character_image_url)
                        except Exception as e:
                            logger.warning(f"生成角色圖片失敗: {e}")
                        
                        # 第一次發送或編輯現有訊息
                        if punishment_message is None:
                            try:
                                punishment_message = await punishment_channel.send(f"{member.mention}", embed=embed)
                                self.punishment_messages[member.id] = punishment_message.id
                                logger.info(f"發送懲罰訊息: {member.display_name}")
                            except discord.Forbidden:
                                logger.error("沒有權限發送懲罰訊息")
                                break
                            except Exception as e:
                                logger.error(f"發送懲罰訊息錯誤: {e}")
                                break
                        else:
                            try:
                                await punishment_message.edit(content=f"{member.mention}", embed=embed)
                            except discord.NotFound:
                                # 如果訊息被刪除，重新發送
                                try:
                                    punishment_message = await punishment_channel.send(f"{member.mention}", embed=embed)
                                    self.punishment_messages[member.id] = punishment_message.id
                                except Exception as e:
                                    logger.error(f"重新發送懲罰訊息錯誤: {e}")
                                    break
                            except discord.Forbidden:
                                logger.error("沒有權限編輯懲罰訊息")
                                break
                            except Exception as e:
                                logger.error(f"編輯懲罰訊息錯誤: {e}")
                                break
                        
                        # 等待一分鐘
                        await asyncio.sleep(60)

                    except asyncio.CancelledError:
                        logger.info(f"懲罰任務被取消: {member.display_name}")
                        break
                    except Exception as e:
                        logger.error(f"懲罰循環錯誤: {e}")
                        await asyncio.sleep(10)  # 出錯時短暫等待

        except asyncio.CancelledError:
            logger.info(f"懲罰任務被取消: {member.display_name}")
        except Exception as e:
            logger.error(f"懲罰系統錯誤: {e}")
        finally:
            # 清理任務
            if member.id in self.punishment_tasks:
                del self.punishment_tasks[member.id]
            
            # 恢復正常狀態
            try:
                conn = sqlite3.connect('user_data.db')
                set_user_field(member.id, 'is_stunned', 0)
            except Exception as e:
                logger.error(f"恢復使用者狀態錯誤: {e}")
            
            logger.info(f"懲罰任務結束: {member.display_name}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """處理成員離開伺服器的事件"""
        try:
            if member.id in self.punishment_tasks:
                self.punishment_tasks[member.id].cancel()
                del self.punishment_tasks[member.id]
                logger.info(f"成員離開，取消懲罰任務: {member.display_name}")
            
            if member.id in self.punishment_messages:
                del self.punishment_messages[member.id]
                
            if member.id in self.admin_notification_messages:
                del self.admin_notification_messages[member.id]
        except Exception as e:
            logger.error(f"處理成員離開事件錯誤: {e}")

async def setup(bot):
    await bot.add_cog(Ai(bot))
