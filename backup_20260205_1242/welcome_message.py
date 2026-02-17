import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import random
import asyncio
import sqlite3
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
        
        self.init_database()
        # 啟動時預載入圖片 - 延遲啟動避免阻塞
        self.bot.loop.create_task(self.delayed_preload())

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
            # Create image_cache table (local cache only, not in SHEET)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create image_cache table for Discord URL caching
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_cache (
                    cache_key TEXT PRIMARY KEY,
                    discord_url TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    message_id INTEGER
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ 資料庫初始化完成 (使用 Sheet-Driven 架構)")
            
        except Exception as e:
            print(f"❌ 資料庫初始化錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def preload_preset_images(self):
        """預載入 4 張預設角色圖片"""
        print("🖼️ 開始預載入角色圖片...")
        
        for preset_name, config in self.preset_characters.items():
            try:
                # 檢查是否已有緩存
                cached_url = self.get_cached_discord_url(preset_name)
                if cached_url:
                    print(f"✅ {preset_name} 已有緩存")
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
            allowed_fields = {'face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'gender', 'hp', 'stamina', 'is_stunned', 'thread_id', 'inventory'}
            
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
        """從資料庫獲取 Discord URL 緩存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 清理過期的緩存 (超過30天)
            thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
            cursor.execute("DELETE FROM image_cache WHERE created_at < ?", (thirty_days_ago,))
            
            cursor.execute("SELECT discord_url FROM image_cache WHERE cache_key = ?", (cache_key,))
            result = cursor.fetchone()
            
            conn.commit()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            print(f"❌ 獲取 Discord URL 緩存錯誤: {e}")
            return None

    def save_discord_url_cache(self, cache_key: str, discord_url: str, message_id: int = None):
        """保存 Discord URL 到資料庫緩存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            cursor.execute('''
                INSERT OR REPLACE INTO image_cache 
                (cache_key, discord_url, created_at, message_id) 
                VALUES (?, ?, ?, ?)
            ''', (cache_key, discord_url, current_time, message_id))
            
            conn.commit()
            conn.close()
            
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

    @app_commands.command(name="測試歡迎", description="測試歡迎訊息功能")
    async def test_welcome(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user_id = interaction.user.id
        user_data = self.get_user_data(user_id)
        
        if not user_data:
            self.create_user_data(user_id)
            user_data = self.get_user_data(user_id)

        if not user_data:
            await interaction.followup.send("❌ 無法創建測試資料！", ephemeral=True)
            return

        embed = await self.create_welcome_embed(user_data, interaction.user)
        
        # 獲取角色圖片 URL
        character_image_url = await self.get_character_image_url(user_data)
        
        if character_image_url:
            embed.set_image(url=character_image_url)

        combined_view = discord.ui.View(timeout=600)
        gender_view = GenderSelectView(self, user_id)
        action_view = WelcomeActionView(self, user_id)
        
        combined_view.add_item(gender_view.children[0])
        combined_view.add_item(action_view.children[0])
        combined_view.add_item(action_view.children[1])

        await interaction.followup.send(embed=embed, view=combined_view)

    @app_commands.command(name="重新載入角色圖片", description="重新載入預設角色圖片（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def reload_preset_images(self, interaction: discord.Interaction):
        """重新載入預設角色圖片"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            embed = discord.Embed(
                title="🔄 重新載入角色圖片",
                description="正在重新生成4張預設角色圖片...",
                color=0xFF9900
            )
            await interaction.followup.send(embed=embed)
            
            success_count = 0
            failed_presets = []
            
            for preset_name, config in self.preset_characters.items():
                try:
                    # 清除現有緩存
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM image_cache WHERE cache_key = ?", (preset_name,))
                    conn.commit()
                    conn.close()
                    
                    # 刪除本地緩存
                    cache_path = self.cache_dir / f"{preset_name}.png"
                    if cache_path.exists():
                        cache_path.unlink()
                    
                    # 重新生成
                    discord_url = await self.generate_and_cache_preset_image(preset_name, config)
                    if discord_url:
                        success_count += 1
                        print(f"✅ {preset_name} 重新載入成功")
                    else:
                        failed_presets.append(preset_name)
                        print(f"❌ {preset_name} 重新載入失敗")
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    failed_presets.append(preset_name)
                    print(f"❌ {preset_name} 重新載入錯誤: {e}")
            
            # 更新結果
            result_embed = discord.Embed(
                title="📊 重新載入完成",
                color=0x00FF00 if success_count == 4 else 0xFF9900
            )
            
            result_embed.add_field(
                name="✅ 成功", 
                value=f"{success_count}/4 張圖片", 
                inline=True
            )
            
            if failed_presets:
                result_embed.add_field(
                    name="❌ 失敗", 
                    value="\n".join(failed_presets), 
                    inline=True
                )
            
            await interaction.edit_original_response(embed=result_embed)
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ 重新載入失敗",
                description=f"發生錯誤: {str(e)}",
                color=0xFF0000
            )
            await interaction.edit_original_response(embed=error_embed)

    @app_commands.command(name="查看預設圖片", description="查看當前預設角色圖片狀態")
    async def view_preset_images(self, interaction: discord.Interaction):
        """查看預設圖片狀態"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            embed = discord.Embed(
                title="🖼️ 預設角色圖片狀態",
                color=0x0099FF
            )
            
            cached_count = 0
            for preset_name in self.preset_characters.keys():
                cached_url = self.get_cached_discord_url(preset_name)
                status = "✅ 已緩存" if cached_url else "❌ 未緩存"
                
                if cached_url:
                    cached_count += 1
                
                # 描述預設外觀
                config = self.preset_characters[preset_name]
                gender = "男性" if "male" in preset_name else "女性"
                state = "擊暈" if "stunned" in preset_name else "正常"
                
                embed.add_field(
                    name=f"{gender} - {state}",
                    value=f"{status}\n面部: {config['face']}\n上衣: {config['top']}",
                    inline=True
                )
            
            embed.description = f"📊 已緩存: {cached_count}/4 張圖片"
            
            # 如果有緩存的圖片，顯示其中一張作為示例
            if cached_count > 0:
                for preset_name in self.preset_characters.keys():
                    cached_url = self.get_cached_discord_url(preset_name)
                    if cached_url:
                        embed.set_image(url=cached_url)
                        embed.set_footer(text=f"示例圖片: {preset_name}")
                        break
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 查看預設圖片時發生錯誤: {str(e)}")

    @app_commands.command(name="清理緩存", description="清理圖片緩存（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def clear_cache(self, interaction: discord.Interaction):
        """清理圖片緩存"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            deleted_files = 0
            deleted_db_records = 0
            
            # 清理本地文件緩存
            cache_files = list(self.cache_dir.glob("*.png"))
            for cache_file in cache_files:
                try:
                    cache_file.unlink()
                    deleted_files += 1
                except:
                    pass
            
            # 清理資料庫緩存
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM image_cache")
            deleted_db_records = cursor.fetchone()[0]
            cursor.execute("DELETE FROM image_cache")
            conn.commit()
            conn.close()
            
            embed = discord.Embed(
                title="🗑️ 緩存清理完成",
                description=(
                    f"📁 已清理 {deleted_files} 個本地緩存文件\n"
                    f"💾 已清理 {deleted_db_records} 個 Discord URL 緩存\n"
                    "⚠️ 請使用 `/重新載入角色圖片` 重新生成預設圖片"
                ),
                color=0x00FF00
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 清理緩存時發生錯誤: {str(e)}")

    @app_commands.command(name="測試資料庫", description="測試資料庫結構（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def test_database(self, interaction: discord.Interaction):
        """測試資料庫結構 - 使用 Sheet-Driven 架構"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get a sample user to check available fields
            sample_user = get_user(123456789)  # Test with arbitrary user_id
            
            embed = discord.Embed(
                title="🗄️ 資料庫結構檢查 (Sheet-Driven)",
                color=0x0099FF
            )
            
            if sample_user:
                column_names = list(sample_user.keys())
                required_columns = ['user_id', 'level', 'xp', 'kkcoin', 'title', 'hp', 'stamina', 
                                  'inventory', 'face', 'hair', 'skin', 'top', 'bottom', 'shoes', 
                                  'gender', 'is_stunned', 'thread_id']
                
                missing_columns = [col for col in required_columns if col not in column_names]
                
                embed.add_field(
                    name="📋 現有欄位",
                    value=f"共 {len(column_names)} 個欄位\n" + ", ".join(sorted(column_names)[:5]) + "...",
                    inline=False
                )
                
                if missing_columns:
                    embed.add_field(
                        name="⚠️ 可能缺少的欄位",
                        value=", ".join(missing_columns),
                        inline=False
                    )
                    embed.color = 0xFFAA00
                else:
                    embed.add_field(
                        name="✅ 資料庫結構",
                        value="所有必要欄位都存在",
                        inline=False
                    )
                    embed.color = 0x00FF00
            else:
                embed.add_field(
                    name="📊 狀態",
                    value="Sheet-Driven DB 系統正常 (無示例數據)",
                    inline=False
                )
                embed.color = 0x00FF00
            
            embed.add_field(
                name="🔧 架構",
                value="使用 Sheet-Driven 架構\n同步來源: Google Sheets",
                inline=True
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 測試資料庫時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))
