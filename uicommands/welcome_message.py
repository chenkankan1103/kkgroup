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
        self.temp_role1_id = int(os.getenv("TEMP_ROLE1_ID", 0))
        self.member_role_id = int(os.getenv("MEMBER_ROLE_ID", 0))
        self.db_path = './user_data.db'
        self.welcome_messages = {}
        self.stunned_users = {}  # 記錄被擊暈的用戶
        
        # 圖片緩存設定
        self.cache_dir = Path('./character_images')
        self.cache_dir.mkdir(exist_ok=True)
        
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
        
            # 修正：設置完整的預設值，包括角色外觀
            cursor.execute('''
                INSERT OR REPLACE INTO users (
                    user_id, inventory, face, hair, skin, top, bottom, shoes, gender,
                    level, xp, kkcoin, title, hp, stamina, is_stunned
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, default_inventory,
                20005,      # face (男性預設)
                30120,      # hair (男性預設)
                12000,      # skin
                1040014,    # top (男性預設)
                1060096,    # bottom (男性預設)
                1072005,    # shoes
                'male',     # gender
                1,          # level
                0,          # xp
                0,          # kkcoin
                '新手',      # title
                100,        # hp
                100,        # stamina
                0           # is_stunned
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
        """根據角色數據生成緩存鍵值（使用ID組合）"""
        skin = user_data.get('skin', 12000)
        face = user_data.get('face', 20005)
        hair = user_data.get('hair', 30120)
        top = user_data.get('top', 1040014)
        bottom = user_data.get('bottom', 1060096)
        shoes = user_data.get('shoes', 1072005)
        stunned = user_data.get('is_stunned', 0)
        
        # 使用ID組合生成文件名，格式: skin_face_hair_top_bottom_shoes_stunned
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
            
            # 驗證圖片數據
            if len(image_data) < 100:
                return False
                
            # 使用PIL驗證圖片格式並保存為PNG
            with io.BytesIO(image_data) as image_buffer:
                try:
                    img = Image.open(image_buffer)
                    img.verify()  # 驗證圖片
                    
                    # 重新讀取圖片（verify後需要重新開啟）
                    image_buffer.seek(0)
                    img = Image.open(image_buffer)
                    
                    # 保存為PNG格式
                    img.save(cache_path, 'PNG', optimize=True)
                    print(f"圖片已緩存: {cache_path}")
                    return True
                    
                except Exception as img_error:
                    print(f"圖片處理錯誤: {img_error}")
                    return False
                    
        except Exception as e:
            print(f"保存緩存圖片錯誤: {e}")
            return False

    async def load_cached_image(self, cache_key: str) -> Optional[discord.File]:
        """從緩存載入圖片"""
        try:
            cache_path = self.get_cached_image_path(cache_key)
            if cache_path.exists():
                print(f"使用緩存圖片: {cache_path}")
                return discord.File(cache_path, filename='character.png')
        except Exception as e:
            print(f"載入緩存圖片錯誤: {e}")
        return None

    async def fetch_character_image(self, user_data: dict) -> Optional[discord.File]:
        try:
            # 生成緩存鍵值
            cache_key = self.generate_cache_key(user_data)
            
            # 檢查是否已有緩存
            if self.is_image_cached(cache_key):
                cached_image = await self.load_cached_image(cache_key)
                if cached_image:
                    return cached_image
                else:
                    print(f"緩存圖片損壞，重新下載: {cache_key}")
                    # 刪除損壞的緩存文件
                    try:
                        self.get_cached_image_path(cache_key).unlink()
                    except:
                        pass
            
            # 構建API請求
            items = [
                {"itemId": 2000, "region": "GMS", "version": "217"},
                {"itemId": user_data.get('skin', 12000), "region": "GMS", "version": "217"},
            ]

            # 根據是否被擊暈設定臉部表情
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
            
            # 如果被擊暈，使用prone姿勢
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&showLefEars=false&showHighLefEars=false&resize=3&flipX=true"

            print(f"請求API圖片: {cache_key}")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            # 保存到緩存
                            await self.save_image_to_cache(image_data, cache_key)
                            
                            # 返回圖片文件
                            return discord.File(io.BytesIO(image_data), filename='character.png')

        except Exception as e:
            print(f"獲取角色圖片錯誤: {e}")
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
                color=0x696969
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
            character_image = await self.fetch_character_image(user_data)
            
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.png")

            # 如果被擊暈，不顯示互動按鈕
            if user_data.get('is_stunned', 0) == 1:
                await interaction.edit_original_response(embed=embed, attachments=files, view=None)
            else:
                combined_view = discord.ui.View(timeout=600)
                gender_view = GenderSelectView(self, user_id)
                action_view = WelcomeActionView(self, user_id)
                
                combined_view.add_item(gender_view.children[0])
                combined_view.add_item(action_view.children[0])
                combined_view.add_item(action_view.children[1])

                await interaction.edit_original_response(embed=embed, attachments=files, view=combined_view)

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
            character_image = await self.fetch_character_image(user_data)
            
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.png")

            combined_view = discord.ui.View(timeout=600)
            gender_view = GenderSelectView(self, member.id)
            action_view = WelcomeActionView(self, member.id)
            
            combined_view.add_item(gender_view.children[0])
            combined_view.add_item(action_view.children[0])
            combined_view.add_item(action_view.children[1])

            welcome_msg = await channel.send(embed=embed, files=files, view=combined_view)
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
        character_image = await self.fetch_character_image(user_data)
        
        files = []
        if character_image:
            files.append(character_image)
            embed.set_image(url="attachment://character.png")

        await interaction.edit_original_response(embed=embed, attachments=files, view=None)

        # 記錄擊暈用戶資訊 (用於5分鐘後移除臨時身分組)
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
            color=0xFF6B6B
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
        character_image = await self.fetch_character_image(user_data)
        
        files = []
        if character_image:
            files.append(character_image)
            embed.set_image(url="attachment://character.png")

        combined_view = discord.ui.View(timeout=600)
        gender_view = GenderSelectView(self, user_id)
        action_view = WelcomeActionView(self, user_id)
        
        combined_view.add_item(gender_view.children[0])
        combined_view.add_item(action_view.children[0])
        combined_view.add_item(action_view.children[1])

        await interaction.followup.send(embed=embed, files=files, view=combined_view)

    @app_commands.command(name="清理緩存", description="清理圖片緩存（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def clear_cache(self, interaction: discord.Interaction, 
                         cache_type: str = app_commands.Choice(name="全部", value="all")):
        """清理圖片緩存"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            cache_files = list(self.cache_dir.glob("*.png"))
            deleted_count = 0
            
            for cache_file in cache_files:
                try:
                    cache_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"刪除緩存文件失敗 {cache_file}: {e}")
            
            embed = discord.Embed(
                title="🗑️ 緩存清理完成",
                description=f"已清理 {deleted_count} 個緩存圖片文件",
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
            cache_files = list(self.cache_dir.glob("*.png"))
            total_files = len(cache_files)
            total_size = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)  # MB
            
            embed = discord.Embed(
                title="📊 圖片緩存狀態",
                color=0x0099FF
            )
            
            embed.add_field(name="📁 緩存目錄", value=str(self.cache_dir), inline=False)
            embed.add_field(name="📄 緩存文件數", value=f"{total_files} 個", inline=True)
            embed.add_field(name="💾 總大小", value=f"{total_size:.2f} MB", inline=True)
            
            if total_files > 0:
                # 顯示最近的幾個緩存文件，並解析ID
                recent_files = sorted(cache_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]
                recent_list = []
                for f in recent_files:
                    size_kb = f.stat().st_size / 1024
                    filename_without_ext = f.stem  # 移除.png副檔名
                    
                    # 嘗試解析ID組合
                    try:
                        parts = filename_without_ext.split('_')
                        if len(parts) == 7:  # skin_face_hair_top_bottom_shoes_stunned
                            skin, face, hair, top, bottom, shoes, stunned = parts
                            status = "擊暈" if stunned == "1" else "正常"
                            display_info = f"👤{face} 👕{top} 👖{bottom} ({status})"
                        else:
                            display_info = filename_without_ext
                    except:
                        display_info = filename_without_ext
                    
                    recent_list.append(f"• {display_info}")
                    recent_list.append(f"  📁 {f.name} ({size_kb:.1f} KB)")
                
                embed.add_field(
                    name="🕒 最近緩存", 
                    value="\n".join(recent_list), 
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 查看緩存狀態時發生錯誤: {str(e)}")

    @app_commands.command(name="查找緩存", description="根據裝備ID查找緩存圖片")
    async def find_cache(self, interaction: discord.Interaction, 
                        face_id: int = None,
                        top_id: int = None, 
                        bottom_id: int = None):
        """根據裝備ID查找緩存圖片"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            cache_files = list(self.cache_dir.glob("*.png"))
            matching_files = []
            
            for f in cache_files:
                filename_without_ext = f.stem
                try:
                    parts = filename_without_ext.split('_')
                    if len(parts) == 7:  # skin_face_hair_top_bottom_shoes_stunned
                        skin, face, hair, top, bottom, shoes, stunned = parts
                        
                        # 檢查是否符合搜尋條件
                        match = True
                        if face_id is not None and int(face) != face_id:
                            match = False
                        if top_id is not None and int(top) != top_id:
                            match = False
                        if bottom_id is not None and int(bottom) != bottom_id:
                            match = False
                            
                        if match:
                            size_kb = f.stat().st_size / 1024
                            status = "擊暈" if stunned == "1" else "正常"
                            matching_files.append({
                                'file': f,
                                'skin': skin, 'face': face, 'hair': hair,
                                'top': top, 'bottom': bottom, 'shoes': shoes,
                                'status': status, 'size': size_kb
                            })
                except:
                    continue
            
            if not matching_files:
                embed = discord.Embed(
                    title="🔍 搜尋結果",
                    description="沒有找到符合條件的緩存圖片",
                    color=0xFF9900
                )
            else:
                embed = discord.Embed(
                    title=f"🔍 找到 {len(matching_files)} 個匹配的緩存",
                    color=0x00FF00
                )
                
                for i, item in enumerate(matching_files[:10]):  # 最多顯示10個
                    info = (f"👤面部: {item['face']} | 👕上衣: {item['top']} | 👖下裝: {item['bottom']}\n"
                           f"💇髮型: {item['hair']} | 👟鞋子: {item['shoes']} | 🎭皮膚: {item['skin']}\n"
                           f"📁檔案: {item['file'].name} ({item['size']:.1f} KB) | 狀態: {item['status']}")
                    
                    embed.add_field(
                        name=f"匹配 #{i+1}",
                        value=info,
                        inline=False
                    )
                
                if len(matching_files) > 10:
                    embed.set_footer(text=f"還有 {len(matching_files) - 10} 個匹配項目未顯示")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 搜尋緩存時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))
