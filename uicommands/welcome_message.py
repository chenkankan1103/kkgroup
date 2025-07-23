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

    async def fetch_character_image(self, user_data: dict) -> Optional[discord.File]:
        try:
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

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
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

async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))