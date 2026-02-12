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
        await self.cog.update_welcome_message(interaction, self.user_id)
        
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
        await self.cog.update_welcome_message(interaction, self.user_id)
        await interaction.followup.send("✅ 已繳交手機和身分證！")

    @discord.ui.button(label="確認進入園區", style=discord.ButtonStyle.danger, emoji="🚪")
    async def confirm_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        await self.cog.handle_final_verification(interaction, interaction.user)

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
                {"itemId": 2000, "region": "GMS", "version": "217"},
                {"itemId": config['skin'], "region": "GMS", "version": "217"},
            ]

            if config['stunned'] == 1:
                items.append({"itemId": config['face'], "animationName": "stunned", "region": "GMS", "version": "217"})
            else:
                items.append({"itemId": config['face'], "animationName": "default", "region": "GMS", "version": "217"})

            items.extend([
                {"itemId": config['hair'], "region": "GMS", "version": "217"},
                {"itemId": config['top'], "region": "GMS", "version": "217"},
                {"itemId": config['bottom'], "region": "GMS", "version": "217"},
                {"itemId": config['shoes'], "region": "GMS", "version": "217"}
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

    def create_user_data(self, user_id: int):
        """Create new user data with default values"""
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
                'thread_id': 0
            }
            
            set_user(user_id, user_data)
            print(f"✅ 創建用戶資料: {user_id}")
        
        except Exception as e:
            print(f"❌ 創建用戶資料錯誤: {e}")
            import traceback
            traceback.print_exc()

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

    async def update_welcome_message(self, interaction: discord.Interaction, user_id: int):
        try:
            user_data = self.get_user_data(user_id)
            if not user_data:
                return

            user = interaction.guild.get_member(user_id)
            if not user:
                return

            embed = await self.create_welcome_embed(user_data, user)
            
            # 獲取角色圖片 URL
            character_image_url = await self.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)

            # 如果被擊暈，不顯示互動按鈕
            if user_data.get('is_stunned', 0) == 1:
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                combined_view = discord.ui.View(timeout=600)
                gender_view = GenderSelectView(self, user_id)
                action_view = WelcomeActionView(self, user_id)
                
                combined_view.add_item(gender_view.children[0])
                combined_view.add_item(action_view.children[0])
                combined_view.add_item(action_view.children[1])

                await interaction.edit_original_response(embed=embed, view=combined_view)

        except Exception as e:
            print(f"❌ 更新歡迎訊息錯誤: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            print(f"🎯 檢測到新成員加入: {member.name} (ID: {member.id})")
            
            guild = member.guild

            # 添加臨時身分組
            if self.temp_role1_id:
                temp_role1 = guild.get_role(self.temp_role1_id)
                if temp_role1:
                    await member.add_roles(temp_role1, reason="初步驗證角色")
                    print(f"✅ 已添加臨時身分組給 {member.name}")
                else:
                    print(f"⚠️ 找不到臨時身分組 ID: {self.temp_role1_id}")

            # 創建用戶資料
            self.create_user_data(member.id)
            user_data = self.get_user_data(member.id)
            
            if not user_data:
                print(f"❌ 無法獲取用戶資料: {member.name}")
                return

            # 發送歡迎訊息
            channel = self.bot.get_channel(self.welcome_channel_id)
            if not channel:
                print(f"❌ 找不到歡迎頻道 ID: {self.welcome_channel_id}")
                return
                
            print(f"📢 準備發送歡迎訊息到頻道: {channel.name}")
            
            embed = await self.create_welcome_embed(user_data, member)
            
            # 獲取角色圖片 URL
            character_image_url = await self.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)
                print(f"✅ 已設置角色圖片")
            else:
                print(f"⚠️ 無法獲取角色圖片（將不影響主功能）")

            combined_view = discord.ui.View(timeout=600)
            gender_view = GenderSelectView(self, member.id)
            action_view = WelcomeActionView(self, member.id)
            
            combined_view.add_item(gender_view.children[0])
            combined_view.add_item(action_view.children[0])
            combined_view.add_item(action_view.children[1])

            welcome_msg = await channel.send(embed=embed, view=combined_view)
            self.welcome_messages.setdefault(guild.id, {})[member.id] = welcome_msg.id
            
            print(f"✅ 成功發送歡迎訊息給 {member.name}")
            
        except Exception as e:
            print(f"❌ on_member_join 錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def handle_final_verification(self, interaction: discord.Interaction, member: discord.Member):
        try:
            guild = member.guild
            temp_role1 = guild.get_role(self.temp_role1_id)
            member_role = guild.get_role(self.member_role_id) 

            # 設置擊暈狀態
            await self.update_user_data(member.id, {
                'is_stunned': 1,
                'hp': 10,
                'stamina': 10
            })

            # 立即添加正式成員身分
            if member_role:
                await member.add_roles(member_role, reason="進入園區成為正式成員")

            scam_id = f"{random.randint(1, 99999):05d}"
            nickname = f"NO.{scam_id} {member.display_name}"
            try:
                await member.edit(nick=nickname, reason="設定園編")
            except discord.Forbidden:
                pass

            # 更新歡迎訊息為擊暈狀態
            user_data = self.get_user_data(member.id)
            embed = await self.create_welcome_embed(user_data, member)
            
            # 獲取擊暈狀態的圖片 URL
            character_image_url = await self.get_character_image_url(user_data)
            if character_image_url:
                embed.set_image(url=character_image_url)

            await interaction.edit_original_response(embed=embed, view=None)

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

            await interaction.followup.send(embed=embed_response)

            # 5分鐘後移除臨時身分組並完成處理
            await asyncio.sleep(300)
            await self.remove_temp_role_and_cleanup(member.id)
            
        except Exception as e:
            print(f"❌ handle_final_verification 錯誤: {e}")
            import traceback
            traceback.print_exc()

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












async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))
