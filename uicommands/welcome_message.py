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
        self.image_storage_channel_id = int(os.getenv("IMAGE_STORAGE_CHANNEL_ID", 0))  # 新增：專用圖片儲存頻道
        self.temp_role1_id = int(os.getenv("TEMP_ROLE1_ID", 0))
        self.member_role_id = int(os.getenv("MEMBER_ROLE_ID", 0))
        self.db_path = './user_data.db'
        self.welcome_messages = {}
        self.stunned_users = {}
        
        # 圖片緩存設定
        self.cache_dir = Path('./character_images')
        self.cache_dir.mkdir(exist_ok=True)
        
        # 優化的圖片 URL 緩存系統
        self.discord_url_cache = {}  # 儲存 Discord 永久圖片連結
        
        self.init_database()

    def init_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    level INTEGER DEFAULT 1,
                    xp INTEGER DEFAULT 0,
                    kkcoin INTEGER DEFAULT 0,
                    title TEXT DEFAULT '新手',
                    hp INTEGER DEFAULT 100,
                    stamina INTEGER DEFAULT 100,
                    inventory TEXT DEFAULT '[]',
                    character_config TEXT DEFAULT '{}',
                    face INTEGER DEFAULT 20005,
                    hair INTEGER DEFAULT 30120,
                    skin INTEGER DEFAULT 12000,
                    top INTEGER DEFAULT 1040014,
                    bottom INTEGER DEFAULT 1060096,
                    shoes INTEGER DEFAULT 1072005,
                    gender TEXT DEFAULT 'male',
                    is_stunned INTEGER DEFAULT 0
                )
            ''')
            
            # 新增圖片URL緩存表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_cache (
                    cache_key TEXT PRIMARY KEY,
                    discord_url TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    message_id INTEGER
                )
            ''')
            
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if "gender" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN gender TEXT DEFAULT 'male'")
            if "is_stunned" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN is_stunned INTEGER DEFAULT 0")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"資料庫初始化錯誤: {e}")

    def get_user_data(self, user_id: int) -> Optional[dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            print(f"資料庫錯誤: {e}")
            return None

    def create_user_data(self, user_id: int):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
        
            default_inventory = json.dumps(["手機", "身分證"])
        
            cursor.execute('''
                INSERT OR REPLACE INTO users (
                    user_id, inventory, face, hair, skin, top, bottom, shoes, gender,
                    level, xp, kkcoin, title, hp, stamina, is_stunned
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, default_inventory,
                20005, 30120, 12000, 1040014, 1060096, 1072005, 'male',
                1, 0, 0, '新手', 100, 100, 0
            ))
        
            conn.commit()
            conn.close()
        
        except Exception as e:
            print(f"創建使用者資料錯誤: {e}")

    async def update_user_data(self, user_id: int, data: dict):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            for key, value in data.items():
                if key in ['face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'gender', 'hp', 'stamina', 'is_stunned']:
                    updates.append(f"{key} = ?")
                    params.append(value)
            
            if updates:
                params.append(user_id)
                query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
                cursor.execute(query, params)
                conn.commit()
            
            conn.close()
            
        except Exception as e:
            print(f"更新使用者資料錯誤: {e}")

    async def remove_items_from_inventory(self, user_id: int, items_to_remove: list):
        try:
            user_data = self.get_user_data(user_id)
            if not user_data:
                return
            
            inventory = json.loads(user_data['inventory']) if user_data['inventory'] else []
            
            for item in items_to_remove:
                if item in inventory:
                    inventory.remove(item)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET inventory = ? WHERE user_id = ?", 
                         (json.dumps(inventory), user_id))
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"移除物品錯誤: {e}")

    def create_progress_bar(self, current: int, maximum: int, length: int = 10) -> str:
        percentage = max(0, min(1, current / maximum)) if maximum > 0 else 0
        filled = int(length * percentage)
        return '█' * filled + '░' * (length - filled)

    def generate_cache_key(self, user_data: dict) -> str:
        """根據角色數據生成緩存鍵值"""
        skin = user_data.get('skin', 12000)
        face = user_data.get('face', 20005)
        hair = user_data.get('hair', 30120)
        top = user_data.get('top', 1040014)
        bottom = user_data.get('bottom', 1060096)
        shoes = user_data.get('shoes', 1072005)
        stunned = user_data.get('is_stunned', 0)
        
        cache_key = f"{skin}_{face}_{hair}_{top}_{bottom}_{shoes}_{stunned}"
        return cache_key

    def get_cached_image_path(self, cache_key: str) -> Path:
        """獲取緩存圖片路徑"""
        return self.cache_dir / f"{cache_key}.png"

    def is_image_cached(self, cache_key: str) -> bool:
        """檢查圖片是否已緩存"""
        cache_path = self.get_cached_image_path(cache_key)
        return cache_path.exists() and cache_path.is_file()

    async def save_image_to_cache(self, image_data: bytes, cache_key: str) -> bool:
        """將圖片數據保存到緩存"""
        try:
            cache_path = self.get_cached_image_path(cache_key)
            
            if len(image_data) < 100:
                return False
                
            with io.BytesIO(image_data) as image_buffer:
                try:
                    img = Image.open(image_buffer)
                    img.verify()
                    
                    image_buffer.seek(0)
                    img = Image.open(image_buffer)
                    img.save(cache_path, 'PNG', optimize=True)
                    print(f"圖片已緩存: {cache_path}")
                    return True
                    
                except Exception as img_error:
                    print(f"圖片處理錯誤: {img_error}")
                    return False
                    
        except Exception as e:
            print(f"保存緩存圖片錯誤: {e}")
            return False

    def get_cached_discord_url(self, cache_key: str) -> Optional[str]:
        """從資料庫獲取 Discord URL 緩存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 清理過期的緩存 (超過30天)
            thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
            cursor.execute("DELETE FROM image_cache WHERE created_at < ?", (thirty_days_ago,))
            
            # 獲取緩存
            cursor.execute("SELECT discord_url FROM image_cache WHERE cache_key = ?", (cache_key,))
            result = cursor.fetchone()
            
            conn.commit()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            print(f"獲取 Discord URL 緩存錯誤: {e}")
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
            print(f"Discord URL 已緩存: {cache_key}")
            
        except Exception as e:
            print(f"保存 Discord URL 緩存錯誤: {e}")

    async def upload_image_to_discord_storage(self, image_data: bytes, cache_key: str) -> Optional[str]:
        """將圖片上傳到 Discord 儲存頻道並獲取永久 URL"""
        try:
            # 使用專用儲存頻道，如果沒有則使用歡迎頻道
            storage_channel_id = self.image_storage_channel_id or self.welcome_channel_id
            channel = self.bot.get_channel(storage_channel_id)
            
            if not channel:
                print(f"找不到儲存頻道 ID: {storage_channel_id}")
                return None
            
            # 創建文件對象
            file_obj = discord.File(
                io.BytesIO(image_data), 
                filename=f'char_{cache_key}.png'
            )
            
            # 上傳到儲存頻道（不在歡迎頻道發送可見訊息）
            if storage_channel_id == self.welcome_channel_id:
                # 如果使用歡迎頻道，發送後立即刪除
                temp_msg = await channel.send(file=file_obj)
                
                if temp_msg.attachments:
                    discord_url = temp_msg.attachments[0].url
                    
                    # 保存到緩存
                    self.save_discord_url_cache(cache_key, discord_url, temp_msg.id)
                    
                    # 快速刪除訊息（可選，URL 仍然有效）
                    try:
                        await asyncio.sleep(0.1)  # 稍等確保上傳完成
                        await temp_msg.delete()
                    except discord.NotFound:
                        pass
                    
                    print(f"圖片已上傳到 Discord: {cache_key}")
                    return discord_url
            else:
                # 使用專用儲存頻道
                storage_msg = await channel.send(
                    content=f"🖼️ **圖片儲存** - 緩存鍵: `{cache_key}`",
                    file=file_obj
                )
                
                if storage_msg.attachments:
                    discord_url = storage_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, storage_msg.id)
                    print(f"圖片已上傳到 Discord 儲存頻道: {cache_key}")
                    return discord_url
            
        except Exception as e:
            print(f"上傳圖片到 Discord 錯誤: {e}")
        
        return None

    async def fetch_character_image_url(self, user_data: dict) -> Optional[str]:
        """獲取角色圖片 URL（優先使用 Discord 緩存）"""
        try:
            cache_key = self.generate_cache_key(user_data)
            
            # 1. 檢查 Discord URL 緩存
            cached_url = self.get_cached_discord_url(cache_key)
            if cached_url:
                print(f"使用 Discord URL 緩存: {cache_key}")
                return cached_url
            
            # 2. 檢查本地緩存
            if self.is_image_cached(cache_key):
                cache_path = self.get_cached_image_path(cache_key)
                with open(cache_path, 'rb') as f:
                    image_data = f.read()
                
                # 上傳到 Discord 並獲取 URL
                discord_url = await self.upload_image_to_discord_storage(image_data, cache_key)
                if discord_url:
                    return discord_url
            
            # 3. 從 API 獲取圖片
            print(f"從 API 獲取圖片: {cache_key}")
            
            items = [
                {"itemId": 2000, "region": "GMS", "version": "217"},
                {"itemId": user_data.get('skin', 12000), "region": "GMS", "version": "217"},
            ]

            if user_data.get('is_stunned', 0) == 1:
                items.append({"itemId": user_data.get('face', 20005), "animationName": "stunned", "region": "GMS", "version": "217"})
            else:
                items.append({"itemId": user_data.get('face', 20005), "animationName": "default", "region": "GMS", "version": "217"})

            items.extend([
                {"itemId": user_data.get('hair', 30120), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('top', 1040014), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('bottom', 1060096), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('shoes', 1072005), "region": "GMS", "version": "217"}
            ])

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            api_url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&showLefEars=false&showHighLefEars=false&resize=3&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            # 保存到本地緩存
                            await self.save_image_to_cache(image_data, cache_key)
                            
                            # 上傳到 Discord 並獲取 URL
                            discord_url = await self.upload_image_to_discord_storage(image_data, cache_key)
                            if discord_url:
                                return discord_url

        except Exception as e:
            print(f"獲取角色圖片 URL 錯誤: {e}")
        
        return None

    async def create_welcome_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        # 檢查是否被擊暈
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
            character_image_url = await self.fetch_character_image_url(user_data)
            
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
            print(f"更新歡迎訊息錯誤: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild

        if self.temp_role1_id:
            temp_role1 = guild.get_role(self.temp_role1_id)
            if temp_role1:
                await member.add_roles(temp_role1, reason="初步驗證角色")

        self.create_user_data(member.id)
        user_data = self.get_user_data(member.id)
        
        if not user_data:
            return

        channel = self.bot.get_channel(self.welcome_channel_id)
        if channel:
            embed = await self.create_welcome_embed(user_data, member)
            
            # 獲取角色圖片 URL
            character_image_url = await self.fetch_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)

            combined_view = discord.ui.View(timeout=600)
            gender_view = GenderSelectView(self, member.id)
            action_view = WelcomeActionView(self, member.id)
            
            combined_view.add_item(gender_view.children[0])
            combined_view.add_item(action_view.children[0])
            combined_view.add_item(action_view.children[1])

            welcome_msg = await channel.send(embed=embed, view=combined_view)
            self.welcome_messages.setdefault(guild.id, {})[member.id] = welcome_msg.id

    async def handle_final_verification(self, interaction: discord.Interaction, member: discord.Member):
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
        character_image_url = await self.fetch_character_image_url(user_data)
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
        await asyncio.sleep(300)  # 5分鐘
        await self.remove_temp_role_and_cleanup(member.id)

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
            await self.update_user_data(user_id, {
                'is_stunned': 0
            })

            # 清理歡迎訊息
            if stun_data['message_id']:
                try:
                    channel = self.bot.get_channel(self.welcome_channel_id)
                    if channel:
                        msg = await channel.fetch_message(stun_data['message_id'])
                        await msg.delete()
                except discord.NotFound:
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
                except discord.NotFound:
                    pass

            # 清理記錄
            if user_id in self.stunned_users:
                del self.stunned_users[user_id]
            
            guild_messages = self.welcome_messages.get(stun_data['guild_id'], {})
            if user_id in guild_messages:
                del guild_messages[user_id]

        except Exception as e:
            print(f"移除臨時身分組錯誤: {e}")

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
        character_image_url = await self.fetch_character_image_url(user_data)
        
        if character_image_url:
            embed.set_image(url=character_image_url)

        combined_view = discord.ui.View(timeout=600)
        gender_view = GenderSelectView(self, user_id)
        action_view = WelcomeActionView(self, user_id)
        
        combined_view.add_item(gender_view.children[0])
        combined_view.add_item(action_view.children[0])
        combined_view.add_item(action_view.children[1])

        await interaction.followup.send(embed=embed, view=combined_view)

    @app_commands.command(name="清理緩存", description="清理圖片緩存（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def clear_cache(self, interaction: discord.Interaction, 
                         cache_type: str = None):
        """清理圖片緩存"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            deleted_files = 0
            deleted_db_records = 0
            
            if cache_type != "database_only":
                # 清理本地文件緩存
                cache_files = list(self.cache_dir.glob("*.png"))
                
                for cache_file in cache_files:
                    try:
                        cache_file.unlink()
                        deleted_files += 1
                    except Exception as e:
                        print(f"刪除緩存文件失敗 {cache_file}: {e}")
            
            if cache_type != "files_only":
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
                    f"💾 已清理 {deleted_db_records} 個 Discord URL 緩存"
                ),
                color=0x00FF00
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 清理緩存時發生錯誤: {str(e)}")

    @app_commands.command(name="緩存狀態", description="查看圖片緩存狀態")
    async def cache_status(self, interaction: discord.Interaction):
        """查看緩存狀態"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 本地文件緩存統計
            cache_files = list(self.cache_dir.glob("*.png"))
            total_files = len(cache_files)
            total_size = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)  # MB
            
            # 資料庫緩存統計
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM image_cache")
            db_cache_count = cursor.fetchone()[0]
            
            # 獲取最近的緩存記錄
            cursor.execute("""
                SELECT cache_key, created_at FROM image_cache 
                ORDER BY created_at DESC LIMIT 3
            """)
            recent_db_cache = cursor.fetchall()
            conn.close()
            
            embed = discord.Embed(
                title="📊 圖片緩存狀態",
                color=0x0099FF
            )
            
            embed.add_field(name="📁 緩存目錄", value=str(self.cache_dir), inline=False)
            embed.add_field(name="📄 本地文件數", value=f"{total_files} 個", inline=True)
            embed.add_field(name="💾 本地總大小", value=f"{total_size:.2f} MB", inline=True)
            embed.add_field(name="🔗 Discord URL 緩存", value=f"{db_cache_count} 個", inline=True)
            
            # 配置資訊
            storage_channel_info = "專用儲存頻道" if self.image_storage_channel_id else "使用歡迎頻道"
            embed.add_field(name="⚙️ 儲存配置", value=storage_channel_info, inline=True)
            
            if total_files > 0:
                recent_files = sorted(cache_files, key=lambda x: x.stat().st_mtime, reverse=True)[:3]
                recent_list = []
                for f in recent_files:
                    size_kb = f.stat().st_size / 1024
                    filename_without_ext = f.stem
                    
                    try:
                        parts = filename_without_ext.split('_')
                        if len(parts) == 7:
                            skin, face, hair, top, bottom, shoes, stunned = parts
                            status = "擊暈" if stunned == "1" else "正常"
                            display_info = f"👤{face} 👕{top} 👖{bottom} ({status})"
                        else:
                            display_info = filename_without_ext
                    except:
                        display_info = filename_without_ext
                    
                    recent_list.append(f"• {display_info} ({size_kb:.1f} KB)")
                
                embed.add_field(
                    name="🕒 最近本地緩存", 
                    value="\n".join(recent_list), 
                    inline=False
                )
            
            if recent_db_cache:
                db_recent_list = []
                for cache_key, created_at in recent_db_cache:
                    from datetime import datetime
                    date_str = datetime.fromtimestamp(created_at).strftime("%m/%d %H:%M")
                    
                    try:
                        parts = cache_key.split('_')
                        if len(parts) == 7:
                            skin, face, hair, top, bottom, shoes, stunned = parts
                            status = "擊暈" if stunned == "1" else "正常"
                            display_info = f"👤{face} ({status})"
                        else:
                            display_info = cache_key
                    except:
                        display_info = cache_key
                    
                    db_recent_list.append(f"• {display_info} - {date_str}")
                
                embed.add_field(
                    name="🔗 最近 Discord URL 緩存", 
                    value="\n".join(db_recent_list), 
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 查看緩存狀態時發生錯誤: {str(e)}")

    @app_commands.command(name="強制刷新圖片", description="強制刷新特定用戶的圖片緩存")
    async def force_refresh_image(self, interaction: discord.Interaction, 
                                 user: discord.User = None):
        """強制刷新圖片緩存"""
        await interaction.response.defer(ephemeral=True)
        
        target_user = user or interaction.user
        user_data = self.get_user_data(target_user.id)
        
        if not user_data:
            await interaction.followup.send("❌ 找不到用戶資料！")
            return
        
        try:
            # 清除該用戶的緩存
            cache_key = self.generate_cache_key(user_data)
            
            # 刪除本地緩存
            cache_path = self.get_cached_image_path(cache_key)
            if cache_path.exists():
                cache_path.unlink()
                print(f"已刪除本地緩存: {cache_path}")
            
            # 清除 Discord URL 緩存
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM image_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()
            conn.close()
            print(f"已清除 Discord URL 緩存: {cache_key}")
            
            # 重新獲取圖片
            embed = discord.Embed(
                title="🔄 正在刷新圖片...",
                description=f"正在為 {target_user.mention} 重新生成角色圖片",
                color=0xFF9900
            )
            
            character_image_url = await self.fetch_character_image_url(user_data)
            
            if character_image_url:
                embed.title = "✅ 圖片刷新成功！"
                embed.description = f"已為 {target_user.mention} 重新生成角色圖片"
                embed.set_image(url=character_image_url)
                embed.color = 0x00FF00
            else:
                embed.title = "❌ 圖片刷新失敗"
                embed.description = "無法獲取角色圖片，請稍後再試"
                embed.color = 0xFF0000
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 刷新圖片時發生錯誤: {str(e)}")

    @app_commands.command(name="設定圖片儲存頻道", description="設定專用圖片儲存頻道（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def set_image_storage_channel(self, interaction: discord.Interaction, 
                                       channel: discord.TextChannel = None):
        """設定圖片儲存頻道"""
        await interaction.response.defer(ephemeral=True)
        
        if channel:
            # 測試頻道權限
            try:
                test_embed = discord.Embed(
                    title="🧪 頻道測試",
                    description="測試機器人是否可以在此頻道發送訊息和上傳圖片",
                    color=0x0099FF
                )
                
                test_msg = await channel.send(embed=test_embed)
                await test_msg.delete()
                
                # 儲存配置（這裡您可能需要將其儲存到資料庫或配置文件）
                self.image_storage_channel_id = channel.id
                
                embed = discord.Embed(
                    title="✅ 圖片儲存頻道設定成功",
                    description=(
                        f"📁 已設定 {channel.mention} 為圖片儲存頻道\n"
                        "🖼️ 之後的角色圖片將上傳至此頻道\n"
                        "💾 現有的緩存不會受到影響"
                    ),
                    color=0x00FF00
                )
                
            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ 權限不足",
                    description=f"機器人沒有權限在 {channel.mention} 發送訊息或上傳文件",
                    color=0xFF0000
                )
            except Exception as e:
                embed = discord.Embed(
                    title="❌ 設定失敗",
                    description=f"發生錯誤: {str(e)}",
                    color=0xFF0000
                )
        else:
            # 重置為使用歡迎頻道
            self.image_storage_channel_id = 0
            embed = discord.Embed(
                title="🔄 已重置圖片儲存設定",
                description="圖片將上傳到歡迎頻道（並立即刪除訊息）",
                color=0xFF9900
            )
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))
