import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import random
import asyncio
import json
import aiohttp
import io
from PIL import Image
from typing import Optional
import hashlib
from pathlib import Path
import time
import re
from db_adapter import get_user, set_user, get_user_field, set_user_field

load_dotenv()

class GenderSelectView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.select(
        placeholder="選擇你的性別...",
        options=[
            discord.SelectOption(label="男性", value="male", emoji="♂️"),
            discord.SelectOption(label="女性", value="female", emoji="♀️")
        ]
    )
    async def gender_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的選項！")
            return

        appearance = {
            'face': 20005 if select.values[0] == "male" else 21731,
            'hair': 30120 if select.values[0] == "male" else 34410,
            'skin': 12000,
            'top': 1040014 if select.values[0] == "male" else 1041004,
            'bottom': 1060096 if select.values[0] == "male" else 1061008,
            'shoes': 1072005,
            'gender': select.values[0]
        }

        await self.cog.update_user_data(self.user_id, appearance)
        # 不需要更新頻道訊息，僅更新當前互動回應
        await self.cog.update_welcome_message(interaction, self.user_id, edit_channel=False)
        
        gender_text = "男性" if select.values[0] == "male" else "女性"
        await interaction.followup.send(f"✅ 已設定為{gender_text}！")

class WelcomeActionView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="繳交手機身分證", style=discord.ButtonStyle.secondary, emoji="📱")
    async def submit_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！")
            return

        await self.cog.remove_items_from_inventory(self.user_id, ["手機", "身分證"])
        # 只更新當前互動回應
        await self.cog.update_welcome_message(interaction, self.user_id, edit_channel=False)
        await interaction.followup.send("✅ 已繳交手機和身分證！")

    @discord.ui.button(label="確認進入園區", style=discord.ButtonStyle.danger, emoji="🚪")
    async def confirm_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        await self.cog.handle_final_verification(interaction, interaction.user)

class PersistentWelcomeView(discord.ui.View):
    """Persistent view for welcome interactions (cross-restart)."""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    def _extract_target_user_id(self, message: discord.Message) -> Optional[int]:
        """從 embed 中解析被歡迎的 user id（fallback: None）"""
        try:
            import re
            if not message or not getattr(message, "embeds", None):
                return None
            for embed in message.embeds:
                desc = getattr(embed, "description", "") or ""
                m = re.search(r"<@!?(?P<id>\d+)>", desc)
                if m:
                    return int(m.group("id"))
                # 檢查欄位
                for field in getattr(embed, "fields", []):
                    m = re.search(r"<@!?(?P<id>\d+)>", field.value or "")
                    if m:
                        return int(m.group("id"))
        except Exception:
            return None
        return None

    @discord.ui.select(custom_id="welcome_gender_select",
                       placeholder="選擇你的性別...",
                       options=[
                           discord.SelectOption(label="男性", value="male", emoji="♂️"),
                           discord.SelectOption(label="女性", value="female", emoji="♀️")
                       ])
    async def gender_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        target_user_id = self._extract_target_user_id(interaction.message) or interaction.user.id

        if interaction.user.id != target_user_id:
            await interaction.followup.send("❌ 這不是你的選項！", ephemeral=True)
            return

        appearance = {
            "face": 20005 if select.values[0] == "male" else 21731,
            "hair": 30120 if select.values[0] == "male" else 34410,
            "skin": 12000,
            "top": 1040014 if select.values[0] == "male" else 1041004,
            "bottom": 1060096 if select.values[0] == "male" else 1061008,
            "shoes": 1072005,
            "gender": select.values[0]
        }

        await self.cog.update_user_data(target_user_id, appearance)
        await self.cog.update_welcome_message(interaction, target_user_id)

        gender_text = "男性" if select.values[0] == "male" else "女性"
        await interaction.followup.send(f"✅ 已設定為{gender_text}！", ephemeral=True)

    @discord.ui.button(custom_id="welcome_submit_items", label="繳交手機身分證", style=discord.ButtonStyle.secondary, emoji="📱")
    async def submit_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        target_user_id = self._extract_target_user_id(interaction.message) or interaction.user.id

        if interaction.user.id != target_user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        await self.cog.remove_items_from_inventory(target_user_id, ["手機", "身分證"])
        await self.cog.update_welcome_message(interaction, target_user_id)
        await interaction.followup.send("✅ 已繳交手機和身分證！", ephemeral=True)

    @discord.ui.button(custom_id="welcome_confirm_entry", label="確認進入園區", style=discord.ButtonStyle.danger, emoji="🚪")
    async def confirm_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        target_user_id = self._extract_target_user_id(interaction.message) or interaction.user.id

        print(f"🔘 【入園按鈕】按下者: {interaction.user.id} ({interaction.user.name}), 目標用戶: {target_user_id}")

        if interaction.user.id != target_user_id:
            print(f"❌ 【入園按鈕】權限檢查失敗：{interaction.user.id} != {target_user_id}")
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        member = interaction.guild.get_member(target_user_id)
        if not member:
            print(f"❌ 【入園按鈕】找不到成員: {target_user_id}")
            await interaction.followup.send("❌ 無法找到用戶，請重試", ephemeral=True)
            return
            
        print(f"✅ 【入園按鈕】權限檢查通過，開始處理 {member.name} 的入園流程...")
        await self.cog.handle_final_verification(interaction, member)

class TestWelcomeView(discord.ui.View):
    """A copy of the real welcome view that does **not** mutate any state.
    Used only for simulating button presses during debugging.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="選擇你的性別...",
        options=[
            discord.SelectOption(label="男性", value="male", emoji="♂️"),
            discord.SelectOption(label="女性", value="female", emoji="♀️")
        ]
    )
    async def gender_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_message(
            f"（模擬）已選擇性別：{select.values[0]}",
            ephemeral=True
        )

    @discord.ui.button(label="繳交手機身分證", style=discord.ButtonStyle.secondary, emoji="📱")
    async def submit_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("（模擬）已繳交手機和身分證。", ephemeral=True)

    @discord.ui.button(label="確認進入園區", style=discord.ButtonStyle.danger, emoji="🚪")
    async def confirm_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("（模擬）按下進入園區按鈕，流程結束。", ephemeral=True)


class WelcomeFlow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.welcome_channel_id = int(os.getenv("WELCOME_CHANNEL_ID", 0))
        self.image_storage_channel_id = int(os.getenv("IMAGE_STORAGE_CHANNEL_ID", 0))
        self.temp_role1_id = int(os.getenv("TEMP_ROLE1_ID", 0))
        self.member_role_id = int(os.getenv("MEMBER_ROLE_ID", 0))
        self.db_path = './user_data.db'
        self.welcome_messages = {}
        self.stunned_users = {}
        
        # 預設角色圖片配置 (4種固定組合)
        self.preset_characters = {
            'male_normal': {
                'skin': 12000, 'face': 20005, 'hair': 30120,
                'top': 1040014, 'bottom': 1060096, 'shoes': 1072005,
                'pose': 'stand1', 'stunned': 0
            },
            'male_stunned': {
                'skin': 12000, 'face': 20005, 'hair': 30120,
                'top': 1040014, 'bottom': 1060096, 'shoes': 1072005,
                'pose': 'prone', 'stunned': 1
            },
            'female_normal': {
                'skin': 12000, 'face': 21731, 'hair': 34410,
                'top': 1041004, 'bottom': 1061008, 'shoes': 1072005,
                'pose': 'stand1', 'stunned': 0
            },
            'female_stunned': {
                'skin': 12000, 'face': 21731, 'hair': 34410,
                'top': 1041004, 'bottom': 1061008, 'shoes': 1072005,
                'pose': 'prone', 'stunned': 1
            }
        }
        
        # 圖片緩存
        self.cache_dir = Path('./character_images')
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = Path('./character_images/discord_url_cache.json')
        
        self.init_database()
        # 啟動時加載持久化緩存
        self.load_persistent_cache()
        # 啟動時預載入圖片 - 延遲啟動避免阻塞
        self.bot.loop.create_task(self.delayed_preload())

        # 註冊跨重啟的 persistent view（處理 welcome 的按鈕/選單）
        try:
            self.persistent_view = PersistentWelcomeView(self)
            self.bot.add_view(self.persistent_view)
            print("✅ 已註冊 PersistentWelcomeView (跨重啟互動)")
        except Exception as e:
            print(f"⚠️ 註冊 PersistentWelcomeView 失敗: {e}")

    def load_persistent_cache(self):
        """從文件加載持久化的 Discord URL 緩存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # 轉換回內存格式
                    for cache_key, url_data in cache_data.items():
                        if isinstance(url_data, dict) and 'discord_url' in url_data:
                            self.image_cache[cache_key] = url_data
                print(f"✅ 已加載 {len(self.image_cache)} 個圖片緩存 (從文件)")
        except Exception as e:
            print(f"⚠️ 加載持久化緩存失敗: {e}")
    
    def save_persistent_cache(self):
        """保存 Discord URL 緩存到文件"""
        try:
            self.cache_dir.mkdir(exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.image_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存持久化緩存失敗: {e}")

    async def delayed_preload(self):
        """延遲預載入以避免阻塞機器人啟動"""
        try:
            await asyncio.sleep(5)  # 等待機器人完全啟動
            await self.preload_preset_images()
        except Exception as e:
            print(f"⚠️ 預載入圖片時發生錯誤（不影響主功能）: {e}")

    def init_database(self):
        """
        Initialize database using new sheet-driven architecture.
        Schema is automatically managed by db_adapter via SHEET Row 1.
        """
        try:
            # Initialize in-memory image cache (replaces SQLite table)
            # Format: {cache_key: {'discord_url': str, 'created_at': int, 'message_id': int}}
            if not hasattr(self, 'image_cache'):
                self.image_cache = {}
            print("✅ 資料庫初始化完成 (使用 Sheet-Driven 架構)")
            
        except Exception as e:
            print(f"❌ 資料庫初始化錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def preload_preset_images(self):
        """預載入 4 張預設角色圖片（如果緩存不存在）"""
        print("🖼️ 開始檢查角色圖片緩存...")
        
        for preset_name, config in self.preset_characters.items():
            try:
                # 檢查是否已有緩存（優先從文件快取）
                cached_url = self.get_cached_discord_url(preset_name)
                if cached_url:
                    print(f"✅ {preset_name} 使用已存在的緩存 (跳過上傳)")
                    continue
                
                # 檢查本地緩存
                cache_path = self.cache_dir / f"{preset_name}.png"
                if cache_path.exists():
                    try:
                        with open(cache_path, 'rb') as f:
                            image_data = f.read()
                        
                        discord_url = await self.upload_image_to_discord_storage(image_data, preset_name)
                        if discord_url:
                            print(f"✅ {preset_name} 從本地緩存上傳到 Discord")
                            continue
                    except Exception as e:
                        print(f"⚠️ 讀取本地緩存 {preset_name} 失敗: {e}")
                
                # 從 API 獲取圖片
                discord_url = await self.generate_and_cache_preset_image(preset_name, config)
                if discord_url:
                    print(f"✅ {preset_name} 從 API 獲取並緩存")
                else:
                    print(f"❌ {preset_name} 預載入失敗")
                    
                # 避免請求過於頻繁
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"❌ 預載入 {preset_name} 時發生錯誤: {e}")
        
        print("✅ 角色圖片預載入完成")

    async def generate_and_cache_preset_image(self, preset_name: str, config: dict) -> Optional[str]:
        """生成並緩存預設角色圖片"""
        try:
            items = [
                {"itemId": 2000, "region": "TWMS", "version": "256"},
                {"itemId": config['skin'], "region": "TWMS", "version": "256"},
            ]

            if config['stunned'] == 1:
                items.append({"itemId": config['face'], "animationName": "stunned", "region": "TWMS", "version": "256"})
            else:
                items.append({"itemId": config['face'], "animationName": "default", "region": "TWMS", "version": "256"})

            items.extend([
                {"itemId": config['hair'], "region": "TWMS", "version": "256"},
                {"itemId": config['top'], "region": "TWMS", "version": "256"},
                {"itemId": config['bottom'], "region": "TWMS", "version": "256"},
                {"itemId": config['shoes'], "region": "TWMS", "version": "256"}
            ])

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            api_url = f"https://maplestory.io/api/character/{item_path}/{config['pose']}/animated?showears=false&showLefEars=false&showHighLefEars=false&resize=3&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            # 保存到本地緩存
                            await self.save_image_to_cache(image_data, preset_name)
                            
                            # 上傳到 Discord
                            return await self.upload_image_to_discord_storage(image_data, preset_name)

        except Exception as e:
            print(f"❌ 生成預設圖片 {preset_name} 錯誤: {e}")
        
        return None

    def get_user_data(self, user_id: int) -> Optional[dict]:
        """Get user data from sheet-driven database"""
        try:
            user_data = get_user(user_id)
            return user_data if user_data else None
        except Exception as e:
            print(f"❌ 獲取用戶資料錯誤: {e}")
            return None

    def create_user_data(self, user_id: int) -> bool:
        """Create new user data with default values. Returns True if successful."""
        try:
            default_inventory = json.dumps(["手機", "身分證"])
            
            user_data = {
                'user_id': user_id,
                'inventory': default_inventory,
                'character_config': '{}',
                'face': 20005,
                'hair': 30120,
                'skin': 12000,
                'top': 1040014,
                'bottom': 1060096,
                'shoes': 1072005,
                'gender': 'male',
                'level': 1,
                'xp': 0,
                'kkcoin': 0,
                'title': '新手',
                'hp': 100,
                'stamina': 100,
                'is_stunned': 0,
                'thread_id': 0,
                # 初始化週統計快照字段
                'last_kkcoin_snapshot': 0,
                'last_xp_snapshot': 0,
                'last_level_snapshot': 1
            }
            
            result = set_user(user_id, user_data)
            if result:
                print(f"✅ 創建用戶資料: {user_id}")
            else:
                print(f"⚠️ 設置用戶資料返回失敗（可能已存在）: {user_id}")
            return result
        
        except Exception as e:
            print(f"❌ 創建用戶資料錯誤: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def update_user_data(self, user_id: int, data: dict):
        """Update user data fields in sheet-driven database"""
        try:
            allowed_fields = {'face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'gender', 'hp', 'stamina', 'is_stunned', 'thread_id', 'inventory', 'character_config'}
            
            for key, value in data.items():
                if key in allowed_fields:
                    set_user_field(user_id, key, value)
            
        except Exception as e:
            print(f"❌ 更新用戶資料錯誤: {e}")

    async def remove_items_from_inventory(self, user_id: int, items_to_remove: list):
        """Remove items from user inventory"""
        try:
            user_data = self.get_user_data(user_id)
            if not user_data:
                return
            
            inventory = json.loads(user_data.get('inventory', '[]')) if user_data.get('inventory') else []
            
            for item in items_to_remove:
                if item in inventory:
                    inventory.remove(item)
            
            set_user_field(user_id, 'inventory', json.dumps(inventory))
            
        except Exception as e:
            print(f"❌ 移除物品錯誤: {e}")

    def create_progress_bar(self, current: int, maximum: int, length: int = 10) -> str:
        percentage = max(0, min(1, current / maximum)) if maximum > 0 else 0
        filled = int(length * percentage)
        return '█' * filled + '░' * (length - filled)

    def get_preset_key_for_user(self, user_data: dict) -> str:
        """根據用戶數據獲取對應的預設角色鍵值"""
        gender = user_data.get('gender', 'male')
        is_stunned = user_data.get('is_stunned', 0)
        
        if is_stunned == 1:
            return f"{gender}_stunned"
        else:
            return f"{gender}_normal"

    async def save_image_to_cache(self, image_data: bytes, cache_key: str) -> bool:
        """將圖片數據保存到本地緩存"""
        try:
            cache_path = self.cache_dir / f"{cache_key}.png"
            
            if len(image_data) < 100:
                return False
                
            with io.BytesIO(image_data) as image_buffer:
                try:
                    img = Image.open(image_buffer)
                    img.verify()
                    
                    image_buffer.seek(0)
                    img = Image.open(image_buffer)
                    img.save(cache_path, 'PNG', optimize=True)
                    return True
                    
                except Exception:
                    return False
                    
        except Exception as e:
            print(f"❌ 保存本地緩存錯誤: {e}")
            return False

    def get_cached_discord_url(self, cache_key: str) -> Optional[str]:
        """從記憶體獲取 Discord URL 緩存"""
        try:
            # 清理過期的緩存 (超過30天)
            thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
            expired_keys = [key for key, data in self.image_cache.items() 
                           if data.get('created_at', 0) < thirty_days_ago]
            for key in expired_keys:
                del self.image_cache[key]
            
            # 獲取緩存
            if cache_key in self.image_cache:
                return self.image_cache[cache_key].get('discord_url')
            return None
            
        except Exception as e:
            print(f"❌ 獲取 Discord URL 緩存錯誤: {e}")
            return None

    def save_discord_url_cache(self, cache_key: str, discord_url: str, message_id: int = None):
        """保存 Discord URL 到記憶體緩存並持久化到文件"""
        try:
            current_time = int(time.time())
            self.image_cache[cache_key] = {
                'discord_url': discord_url,
                'created_at': current_time,
                'message_id': message_id
            }
            # 同時保存到文件實現持久化
            self.save_persistent_cache()
            
        except Exception as e:
            print(f"❌ 保存 Discord URL 緩存錯誤: {e}")

    async def upload_image_to_discord_storage(self, image_data: bytes, cache_key: str) -> Optional[str]:
        """將圖片上傳到 Discord 儲存頻道"""
        try:
            storage_channel_id = self.image_storage_channel_id or self.welcome_channel_id
            channel = self.bot.get_channel(storage_channel_id)
            
            if not channel:
                print(f"❌ 找不到儲存頻道: {storage_channel_id}")
                return None
            
            file_obj = discord.File(
                io.BytesIO(image_data), 
                filename=f'char_{cache_key}.png'
            )
            
            if storage_channel_id == self.welcome_channel_id:
                temp_msg = await channel.send(file=file_obj)
                
                if temp_msg.attachments:
                    discord_url = temp_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, temp_msg.id)
                    
                    try:
                        await asyncio.sleep(0.5)
                        await temp_msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass
                    
                    return discord_url
            else:
                storage_msg = await channel.send(
                    content=f"🖼️ **角色圖片** - {cache_key}",
                    file=file_obj
                )
                
                if storage_msg.attachments:
                    discord_url = storage_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, storage_msg.id)
                    return discord_url
            
        except Exception as e:
            print(f"❌ 上傳圖片到 Discord 錯誤: {e}")
        
        return None

    async def get_character_image_url(self, user_data: dict) -> Optional[str]:
        """獲取用戶對應的角色圖片 URL"""
        preset_key = self.get_preset_key_for_user(user_data)
        
        # 直接從緩存獲取 URL
        cached_url = self.get_cached_discord_url(preset_key)
        if cached_url:
            return cached_url
        
        # 如果沒有緩存，嘗試生成
        if preset_key in self.preset_characters:
            config = self.preset_characters[preset_key]
            return await self.generate_and_cache_preset_image(preset_key, config)
        
        return None

    async def create_welcome_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        if user_data.get('is_stunned', 0) == 1:
            embed = discord.Embed(
                title="💫 一陣天旋地轉...",
                description=(
                    f"💫 **{user.mention}** 一陣天旋地轉，你已倒在地上。\n\n"
                    "😵 你被擊暈了！\n"
                    "🏥 血量和體力大幅下降\n"
                    "💤 正在恢復中...\n\n"
                    "⏰ 請等待恢復，或聯繫管理員協助"
                ),
                color=0xFF6B6B
            )
        else:
            embed = discord.Embed(
                title="🎉 歡迎光臨 KK 園區™",
                description=(
                    f"🎉 歡迎 **{user.mention}** 蒞臨 KK 園區™ — 一個讓人留連忘返的樂園。\n\n"
                    "🏠 食宿無憂，大通鋪讓你夜夜安穩；\n"
                    "🤝 不怕孤單，因為你永遠有人作伴；\n"
                    "🎭 娛樂充足，幹部們會「適時」安排你的休閒時光。\n\n"
                    "📜 **入園流程如下：**\n"
                    "1️⃣ 選擇你的性別\n"
                    "2️⃣ 繳交不必要的物品\n"
                    "3️⃣ 點擊確認，即刻入住\n\n"
                    "📌 每日表現將自動記錄為積分，影響分配與待遇。\n"
                    "🎁 定期將物品上繳以獲得特別回饋。\n"
                    "🚪 出口目前維護中，開放時間未定。\n"
                    "📷 園區全程監控中，請放心生活。"
                ),
                color=0x8B0000
            )
        
        # 添加用戶資訊欄位
        embed.add_field(name="⭐ 等級", value=f"{user_data['level']}", inline=True)
        embed.add_field(name="💰 金錢", value=f"{user_data['kkcoin']} KKCoin", inline=True)
        embed.add_field(name="🏆 職位", value=user_data['title'], inline=True)

        hp_bar = self.create_progress_bar(user_data['hp'], 100)
        stamina_bar = self.create_progress_bar(user_data['stamina'], 100)
        embed.add_field(name="❤️ 血量", value=f"{hp_bar} {user_data['hp']}/100", inline=False)
        embed.add_field(name="⚡ 體力", value=f"{stamina_bar} {user_data['stamina']}/100", inline=False)

        gender_display = "男性 ♂️" if user_data.get('gender') == 'male' else "女性 ♀️"
        embed.add_field(name="👤 性別", value=gender_display, inline=True)
        embed.add_field(name="👔 上衣", value=f"ID: {user_data['top']}", inline=True)
        embed.add_field(name="👖 下裝", value=f"ID: {user_data['bottom']}", inline=True)

        # 處理物品欄顯示
        inventory = '空的'
        if user_data['inventory']:
            try:
                items = json.loads(user_data['inventory'])
                if items:
                    inventory = ', '.join(str(item) for item in items[:3])
                    if len(items) > 3:
                        inventory += f"... 等{len(items)}項"
            except:
                pass
        embed.add_field(name="🎒 物品欄", value=inventory, inline=False)

        embed.set_thumbnail(url=user.display_avatar.url)
        
        if user_data.get('is_stunned', 0) == 1:
            embed.set_footer(text="💫 你目前處於擊暈狀態，請等待恢復...")
        else:
            embed.set_footer(text="⚠️ 園區已自動為你關閉離開選項，安心享受吧。")
            
        return embed

    async def update_welcome_message(self, interaction: discord.Interaction, user_id: int, edit_channel: bool = False):
        """更新用戶的歡迎 embed。
        - 如果 edit_channel=False（預設），只編輯歡迎頻道的原始訊息
        - 如果 edit_channel=True，也會編輯歡迎頻道的訊息
        - 不編輯 ephemeral interaction 的 original response（轉而使用 followup）
        """
        try:
            user_data = self.get_user_data(user_id)
            if not user_data:
                print(f"⚠️ 無法獲取用戶資料: {user_id}")
                return

            user = interaction.guild.get_member(user_id)
            if not user:
                print(f"⚠️ 無法獲取成員資料: {user_id}")
                return

            embed = await self.create_welcome_embed(user_data, user)
            
            # 獲取角色圖片 URL
            character_image_url = await self.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)

            # 更新歡迎頻道的原始訊息（如果有紀錄）
            try:
                msg_id = self.welcome_messages.get(interaction.guild.id, {}).get(user_id)
                if msg_id:
                    channel = self.bot.get_channel(self.welcome_channel_id)
                    if channel:
                        msg = await channel.fetch_message(msg_id)
                        if user_data.get('is_stunned', 0) == 1:
                            await msg.edit(embed=embed, view=None)
                            print(f"✅ 已更新歡迎訊息為擊暈狀態: {user_id}")
                        else:
                            await msg.edit(embed=embed, view=self.persistent_view)
                            print(f"✅ 已更新歡迎訊息: {user_id}")
                    else:
                        print(f"⚠️ 找不到歡迎頻道: {self.welcome_channel_id}")
                else:
                    print(f"⚠️ 未找到歡迎訊息 ID for {user_id}")
            except discord.NotFound:
                print(f"⚠️ 歡迎訊息已被刪除: {user_id}")
            except Exception as e:
                print(f"⚠️ 編輯歡迎訊息失敗: {e}")

        except Exception as e:
            print(f"❌ 更新歡迎訊息錯誤: {e}")
            import traceback
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            print(f"🎯 檢測到新成員加入: {member.name} (ID: {member.id})")
            
            # 檢查環境變數是否正確設置
            if not self.welcome_channel_id or not self.temp_role1_id or not self.member_role_id:
                print(f"❌ 環境變數缺失: WELCOME_CHANNEL_ID={self.welcome_channel_id}, TEMP_ROLE1_ID={self.temp_role1_id}, MEMBER_ROLE_ID={self.member_role_id}")
                try:
                    await member.send("❌ 歡迎系統配置不完整，請聯繫管理員")
                except discord.Forbidden:
                    pass
                return
            
            guild = member.guild

            # 添加臨時身分組
            if self.temp_role1_id:
                temp_role1 = guild.get_role(self.temp_role1_id)
                if temp_role1:
                    try:
                        await member.add_roles(temp_role1, reason="初步驗證角色")
                        print(f"✅ 已添加臨時身分組給 {member.name}")
                    except discord.Forbidden:
                        print(f"❌ 權限不足，無法添加身分組給 {member.name}")
                else:
                    print(f"❌ 找不到臨時身分組 ID: {self.temp_role1_id}")

            # 創建用戶資料
            user_created = self.create_user_data(member.id)
            if not user_created:
                print(f"⚠️ 創建用戶資料失敗，嘗試獲取現有資料: {member.name}")
                
            user_data = self.get_user_data(member.id)
            
            if not user_data:
                print(f"❌ 無法獲取或創建用戶資料: {member.name}")
                try:
                    await member.send("❌ 無法初始化用戶資料，請聯繫管理員")
                except discord.Forbidden:
                    pass
                return

            # 發送歡迎訊息
            channel = self.bot.get_channel(self.welcome_channel_id)
            if not channel:
                print(f"❌ 找不到歡迎頻道 ID: {self.welcome_channel_id}")
                try:
                    await member.send("❌ 無法找到歡迎頻道，請聯繫管理員")
                except discord.Forbidden:
                    pass
                return
                
            print(f"📢 準備發送歡迎訊息到頻道: {channel.name}")
            
            try:
                embed = await self.create_welcome_embed(user_data, member)
                
                # 獲取角色圖片 URL（非關鍵錯誤，可以失敗）
                character_image_url = await self.get_character_image_url(user_data)
                
                if character_image_url:
                    embed.set_image(url=character_image_url)
                    print(f"✅ 已設置角色圖片")
                else:
                    print(f"⚠️ 無法獲取角色圖片（將不影響主功能）")

                # 使用跨重啟的 persistent view（已註冊）
                welcome_msg = await channel.send(embed=embed, view=self.persistent_view)
                self.welcome_messages.setdefault(guild.id, {})[member.id] = welcome_msg.id
                
                print(f"✅ 成功發送歡迎訊息給 {member.name}")
                
            except discord.Forbidden as perm_err:
                print(f"❌ 發送訊息權限不足: {perm_err}")
                print(f"🔧 檢查 bot 在頻道 {self.welcome_channel_id} 是否有 SEND_MESSAGES 權限")
            except Exception as msg_err:
                print(f"❌ 發送歡迎訊息錯誤: {msg_err}")
                import traceback
                traceback.print_exc()
            
        except Exception as e:
            print(f"❌ on_member_join 錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def handle_final_verification(self, interaction: discord.Interaction, member: discord.Member):
        try:
            print(f"🚪 開始入園流程: {member.name} (ID: {member.id})")
            
            # 檢查是否已繳交手機和身分證
            user_data = self.get_user_data(member.id)
            if not user_data:
                print(f"❌ 無法獲取用戶資料: {member.id}")
                await interaction.followup.send("❌ 無法獲取用戶資料，請聯繫管理員", ephemeral=True)
                return
            
            inventory = json.loads(user_data.get('inventory', '[]')) if user_data.get('inventory') else []
            
            if "手機" in inventory or "身分證" in inventory:
                # 使用者尚未手動上繳，先警告並自動沒收
                print(f"⚠️ {member.name} 未上繳物品，系統自動沒收")
                await interaction.followup.send(
                    "⚠️ 你尚未上繳手機或身分證，系統已自動強制沒收並繼續入園流程。",
                    ephemeral=False
                )
                await self.remove_items_from_inventory(member.id, ["手機", "身分證"])
                inventory = []

            guild = member.guild
            temp_role1 = guild.get_role(self.temp_role1_id)
            member_role = guild.get_role(self.member_role_id)
            
            if not member_role:
                print(f"❌ 正式成員身分組不存在: {self.member_role_id}")
                await interaction.followup.send("❌ 正式成員身分組配置錯誤，請聯繫管理員", ephemeral=True)
                return

            # 設置擊暈狀態
            print(f"💫 設置 {member.name} 為擊暈狀態")
            await self.update_user_data(member.id, {
                'is_stunned': 1,
                'hp': 10,
                'stamina': 10
            })

            # 立即添加正式成員身分
            try:
                print(f"🎯 嘗試添加正式成員身分給 {member.name}...")
                await member.add_roles(member_role, reason="進入園區成為正式成員")
                print(f"✅ 成功添加正式成員身分給 {member.name}")
            except discord.Forbidden as e:
                print(f"❌ 權限不足，無法添加身分組: {e}")
                await interaction.followup.send(
                    f"❌ 無法添加身分組，可能是權限問題。請檢查機器人角色位置。",
                    ephemeral=True
                )
                return
            except discord.HTTPException as e:
                print(f"❌ 添加身分組時出現 HTTP 錯誤: {e}")
                await interaction.followup.send(
                    f"❌ 添加身分組失敗，請聯繫管理員。",
                    ephemeral=True
                )
                return

            scam_id = f"{random.randint(1, 99999):05d}"
            nickname = f"NO.{scam_id} {member.display_name}"
            try:
                print(f"📝 設定昵稱: {nickname}")
                await member.edit(nick=nickname, reason="設定園編")
            except discord.Forbidden:
                print(f"⚠️ 權限不足，無法修改昵稱")
            except Exception as e:
                print(f"⚠️ 修改昵稱失敗: {e}")

            # 更新歡迎訊息為擊暈狀態
            print(f"📢 更新歡迎訊息...")
            await self.update_welcome_message(interaction, member.id, edit_channel=True)

            # 記錄擊暈用戶資訊
            self.stunned_users[member.id] = {
                'guild_id': guild.id,
                'temp_role1': temp_role1,
                'message_id': self.welcome_messages.get(guild.id, {}).get(member.id)
            }

            embed_response = discord.Embed(
                title="💫 擊暈成功！",
                description=(
                    f"園編：**{nickname}**\n"
                    "💫 已被成功擊暈！\n"
                    "✅ 已獲得正式成員身分\n"
                    "⏰ 5分鐘後將移除臨時身分組\n"
                    "🏥 血量和體力已降至10"
                ),
                color=0x696969
            )
            embed_response.set_thumbnail(url=member.display_avatar.url)

            print(f"✅ 發送入園成功訊息給 {member.name}")
            await interaction.followup.send(embed=embed_response, ephemeral=True)

            # 5分鐘後移除臨時身分組並完成處理
            print(f"⏱️ 排隊 5 分鐘後的清理任務")
            await asyncio.sleep(300)
            await self.remove_temp_role_and_cleanup(member.id)
            
        except Exception as e:
            print(f"❌ handle_final_verification 錯誤: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    f"❌ 入園流程發生錯誤: {str(e)[:100]}\n請聯繫管理員",
                    ephemeral=True
                )
            except:
                pass

    async def remove_temp_role_and_cleanup(self, user_id: int):
        """5分鐘後移除臨時身分組並清理歡迎訊息"""
        try:
            if user_id not in self.stunned_users:
                return

            stun_data = self.stunned_users[user_id]
            guild = self.bot.get_guild(stun_data['guild_id'])
            if not guild:
                return

            member = guild.get_member(user_id)
            if not member:
                return

            # 移除臨時身分組
            if stun_data['temp_role1'] and stun_data['temp_role1'] in member.roles:
                await member.remove_roles(stun_data['temp_role1'], reason="5分鐘後移除臨時身分組")

            # 恢復擊暈狀態 (但血量體力保持在10)
            await self.update_user_data(user_id, {'is_stunned': 0})

            # 清理歡迎訊息
            if stun_data['message_id']:
                try:
                    channel = self.bot.get_channel(self.welcome_channel_id)
                    if channel:
                        msg = await channel.fetch_message(stun_data['message_id'])
                        await msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            # 發送完成通知
            channel = self.bot.get_channel(self.welcome_channel_id)
            if channel:
                embed = discord.Embed(
                    title="✨ 入園完成！",
                    description=(
                        f"🎊 **{member.mention}** 已完成入園程序！\n"
                        "✅ 正式成員身分已確認\n"
                        "🗑️ 臨時身分組已移除\n"
                        "💤 已從擊暈狀態恢復\n"
                        "⚠️ 血量和體力仍處於虛弱狀態\n"
                        "🏥 請尋求治療或使用道具恢復\n"
                        "🎯 歡迎正式加入園區大家庭！"
                    ),
                    color=0x32CD32
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                
                completion_msg = await channel.send(embed=embed)
                
                # 5分鐘後刪除完成訊息
                await asyncio.sleep(300)
                try:
                    await completion_msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            # 清理記錄
            if user_id in self.stunned_users:
                del self.stunned_users[user_id]
            
            guild_messages = self.welcome_messages.get(stun_data['guild_id'], {})
            if user_id in guild_messages:
                del guild_messages[user_id]

        except Exception as e:
            print(f"❌ 移除臨時身分組錯誤: {e}")

    # ---------- debug helpers (slash commands) ----------
    @app_commands.command(name="debug_welcome")
    @app_commands.describe(
        member="目標成員（預設自己）",
        simulate="是否立刻模擬按下確認按鈕並執行流程"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_welcome(self, interaction: discord.Interaction, member: Optional[discord.Member] = None, simulate: Optional[bool] = False):
        """在頻道中顯示目標成員的歡迎 embed 並附加真實按鈕，用於測試。

        如果選擇 `simulate=True`，機器人會在發送之後自動執行一次
        `handle_final_verification`（相當於按下「確認進入園區」）。
        """
        target = member or interaction.user
        user_data = self.get_user_data(target.id)
        if not user_data:
            self.create_user_data(target.id)
            user_data = self.get_user_data(target.id)
        embed = await self.create_welcome_embed(user_data, target)
        # 必須帶上 persistent_view，才能在測試訊息中顯示按鈕
        await interaction.response.send_message(embed=embed, view=self.persistent_view)

        if simulate:
            # 略微等候確保前一條訊息已處理
            await asyncio.sleep(0.5)
            # 使用原始互動做為模板，產生一個小型假互動
            await self.handle_final_verification(interaction, target)

    @app_commands.command(name="debug_confirm")
    @app_commands.describe(member="目標成員（預設自己）")
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_confirm(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """模擬按下「確認進入園區」按鈕的流程。"""
        target = member or interaction.user
        # 可以直接呼叫 handle_final_verification 使用真實 interaction
        await interaction.response.defer(ephemeral=True)
        await self.handle_final_verification(interaction, target)
    @app_commands.command(name="debug_press_buttons")
    @app_commands.describe(member="要測試的成員(預設自己)", gender="模擬選擇的性別(male/female)")
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_press_buttons(self, interaction: discord.Interaction, member: Optional[discord.Member] = None, gender: Optional[str] = None):
        """模擬按鈕流程（會改變資料），保留於此供需要時使用。"""
        target = member or interaction.user
        await interaction.response.defer(ephemeral=True)

        # 1. 設定性別（若提供）
        if gender in ("male", "female"):
            appearance = {
                'face': 20005 if gender == "male" else 21731,
                'hair': 30120 if gender == "male" else 34410,
                'skin': 12000,
                'top': 1040014 if gender == "male" else 1041004,
                'bottom': 1060096 if gender == "male" else 1061008,
                'shoes': 1072005,
                'gender': gender
            }
            await self.update_user_data(target.id, appearance)

        # 2. 移除手機和身分證（模擬按下繳交按鈕）
        await self.remove_items_from_inventory(target.id, ["手機", "身分證"])

        # 3. 呼叫最終驗證
        await self.handle_final_verification(interaction, target)

    @app_commands.command(name="debug_simulate_buttons")
    @app_commands.describe(member="要測試的成員(預設自己)")
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_simulate_buttons(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """發送一條查看原始按鈕視覺但完全不改變資料的模擬訊息。"""
        target = member or interaction.user
        user_data = self.get_user_data(target.id) or {}
        embed = await self.create_welcome_embed(user_data, target)
        # 測試用 view，只回復而不修改任何資料
        view = TestWelcomeView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)












async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))
