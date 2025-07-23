import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
import os
import aiohttp
import urllib.parse
import io
import asyncio
from typing import Optional
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

class UserPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        self.INTRODUCE_CHANNEL_ID = int(os.getenv('INTRODUCE_CHANNEL_ID', '0'))
        self.user_embed_messages = {}
        
        self.assets_path = './assets'
        self.equipment_path = os.path.join(self.assets_path, 'equipment')
        
        os.makedirs(self.equipment_path, exist_ok=True)
        
        self.init_database()

    def init_database(self):
        """初始化資料庫，添加新欄位"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            new_columns = [
                ("face", "INTEGER DEFAULT 20000"),
                ("hair", "INTEGER DEFAULT 30000"), 
                ("skin", "INTEGER DEFAULT 12000"),
                ("top", "INTEGER DEFAULT 1040010"),
                ("bottom", "INTEGER DEFAULT 1060096"),
                ("shoes", "INTEGER DEFAULT 1072288")
            ]
            
            for column_name, column_def in new_columns:
                if column_name not in columns:
                    try:
                        cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
                        print(f"✅ 添加欄位: {column_name}")
                    except Exception as e:
                        print(f"添加欄位 {column_name} 時發生錯誤: {e}")
            
            conn.commit()
            conn.close()
            print("✅ 資料庫初始化完成")
            
        except Exception as e:
            print(f"資料庫初始化錯誤: {e}")

    def get_user_data(self, user_id: int) -> Optional[dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = """
                SELECT user_id, level, xp, kkcoin, title, hp, stamina, 
                inventory, character_config, face, hair, skin, 
                top, bottom, shoes, is_stunned, gender
                FROM users 
                WHERE user_id = ?
            """
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    'user_id': row[0],
                    'level': row[1],
                    'xp': row[2],
                    'kkcoin': row[3],
                    'title': row[4],
                    'hp': row[5],
                    'stamina': row[6],
                    'inventory': row[7],
                    'character_config': row[8],
                    'face': row[9] or 20000,
                    'hair': row[10] or 30000,
                    'skin': row[11] or 12000,
                    'top': row[12] or 1040010,
                    'bottom': row[13] or 1060096,
                    'shoes': row[14] or 1072288,
                    'is_stunned': row[15] or 0,  # 修復：索引錯誤
                    'gender': row[16] or 'male'   # 修復：索引錯誤
                }
            return None
        except Exception as e:
            print(f"資料庫錯誤: {e}")
            return None

    def create_progress_bar(self, current: int, maximum: int, length: int = 10) -> str:
        if maximum == 0:
            percentage = 0
        else:
            percentage = max(0, min(1, current / maximum))
        filled = int(length * percentage)
        empty = length - filled
        return '█' * filled + '░' * empty

    async def fetch_character_image(self, user_data: dict) -> Optional[discord.File]:
        """使用與歡迎訊息相同的 MapleStory.io API 獲取角色圖片"""
        try:
            items = [
                {"itemId": 2000, "region": "GMS", "version": "217"},
                {"itemId": user_data.get('skin', 12000), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('face', 20005), "animationName": "default", "region": "GMS", "version": "217"},
                {"itemId": user_data.get('hair', 30120), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('top', 1040014), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('bottom', 1060096), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('shoes', 1072005), "region": "GMS", "version": "217"}
            ]

            # 檢查是否被擊暈，添加眩暈效果道具
            if user_data.get('is_stunned', 0) == 1:
                items.append({"itemId": 1005411, "region": "GMS", "version": "217"})

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            
            # 如果被擊暈，使用prone姿勢，否則使用stand1
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            return discord.File(io.BytesIO(image_data), filename='character.gif')

        except Exception as e:
            print(f"獲取角色圖片錯誤: {e}")
        return None

    async def test_api_request(self):
        """測試 API 請求是否正常工作"""
        test_data = {
            'face': 20000,
            'hair': 30000,
            'skin': 12000,
            'top': 1040010,
            'bottom': 1060096,
            'shoes': 1072288
        }
        
        print("🧪 開始測試 MapleStory API...")
        result = await self.fetch_character_image(test_data)
        
        if result:
            print("✅ API 測試成功！")
            return True
        else:
            print("❌ API 測試失敗！")
            return False

    async def create_user_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 {user.display_name or user.name} 的面板資訊",
            color=0x00ff88,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="🆔 使用者ID", value=f"`{user_data['user_id']}`", inline=True)
        embed.add_field(name="⭐ 等級", value=f"**{user_data['level'] or 1}**", inline=True)
        embed.add_field(name="✨ 經驗值", value=f"{user_data['xp'] or 0} XP", inline=True)
        embed.add_field(name="💰 金錢", value=f"{user_data['kkcoin'] or 0} KKCoin", inline=True)
        embed.add_field(name="🏆 職位", value=user_data['title'] or '新手', inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        hp = user_data['hp'] or 100
        stamina = user_data['stamina'] or 100
        hp_bar = self.create_progress_bar(hp, 100)
        stamina_bar = self.create_progress_bar(stamina, 100)
        embed.add_field(name="❤️ 血量", value=f"{hp_bar} {hp}/100", inline=False)
        embed.add_field(name="⚡ 體力", value=f"{stamina_bar} {stamina}/100", inline=False)

        embed.add_field(name="👔 上身裝備", value=f"ID: {user_data['top']}", inline=True)
        embed.add_field(name="👖 下身裝備", value=f"ID: {user_data['bottom']}", inline=True)
        embed.add_field(name="👟 鞋子", value=f"ID: {user_data['shoes']}", inline=True)
        
        embed.add_field(name="💇 髮型", value=f"ID: {user_data['hair']}", inline=True)
        embed.add_field(name="😊 臉型", value=f"ID: {user_data['face']}", inline=True)
        embed.add_field(name="🎨 膚色", value=f"ID: {user_data['skin']}", inline=True)

        inventory = '空的'
        if user_data['inventory']:
            try:
                items = json.loads(user_data['inventory'])
                if isinstance(items, list) and len(items) > 0:
                    inventory = ', '.join(str(item) for item in items[:5])
                    if len(items) > 5:
                        inventory += f"... 等 {len(items)} 項物品"
            except json.JSONDecodeError:
                inventory_str = str(user_data['inventory'])
                if len(inventory_str) > 50:
                    inventory = inventory_str[:50] + '...'
                else:
                    inventory = inventory_str
        embed.add_field(name="🎒 物品欄", value=inventory, inline=False)
        
        embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
        
        return embed

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.INTRODUCE_CHANNEL_ID:
            return
        if message.author.bot:
            return
        try:
            user_data = self.get_user_data(message.author.id)
            if not user_data:
                print(f"沒有找到使用者 {message.author.id} 的資料")
                return

            embed = await self.create_user_embed(user_data, message.author)
            character_image = await self.fetch_character_image(user_data)
            
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.gif")

            existing_message_id = self.user_embed_messages.get(message.author.id)
            if existing_message_id:
                try:
                    existing_message = await message.channel.fetch_message(existing_message_id)
                    await existing_message.edit(embed=embed, attachments=files)
                    print(f"更新了使用者 {message.author.name} 的面板資訊")
                except discord.NotFound:
                    sent_message = await message.reply(embed=embed, files=files)
                    self.user_embed_messages[message.author.id] = sent_message.id
                    print(f"發送了使用者 {message.author.name} 的新面板資訊")
                except Exception as e:
                    print(f"編輯訊息時發生錯誤: {e}")
            else:
                sent_message = await message.reply(embed=embed, files=files)
                self.user_embed_messages[message.author.id] = sent_message.id
                print(f"發送了使用者 {message.author.name} 的面板資訊")

        except Exception as error:
            print(f"處理使用者面板時發生錯誤: {error}")

    @app_commands.command(name="面板", description="查看自己或指定使用者的面板資訊")
    @app_commands.describe(user="要查看的使用者 (可不填，預設自己)")
    async def show_panel(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        target_user = user or interaction.user
        user_data = self.get_user_data(target_user.id)
        if not user_data:
            await interaction.response.send_message(f"沒有找到 {target_user.mention} 的資料！", ephemeral=True)
            return
        
        embed = await self.create_user_embed(user_data, target_user)
        character_image = await self.fetch_character_image(user_data)
        
        files = []
        if character_image:
            files.append(character_image)
            embed.set_image(url="attachment://character.gif")
        
        await interaction.response.send_message(embed=embed, files=files)

    @app_commands.command(name="設定外觀", description="設定角色外觀")
    @app_commands.describe(
        hair="髮型ID (可選)",
        face="臉型ID (可選)", 
        skin="膚色ID (可選)",
        top="上衣ID (可選)",
        bottom="下裝ID (可選)",
        shoes="鞋子ID (可選)"
    )
    async def set_appearance(self, interaction: discord.Interaction, 
                           hair: Optional[int] = None,
                           face: Optional[int] = None,
                           skin: Optional[int] = None,
                           top: Optional[int] = None,
                           bottom: Optional[int] = None,
                           shoes: Optional[int] = None):
        try:
            user_data = self.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.response.send_message("沒有找到你的資料！", ephemeral=True)
                return
            
            # 準備更新的欄位
            updates = []
            params = []
            
            if hair is not None:
                updates.append("hair = ?")
                params.append(hair)
            if face is not None:
                updates.append("face = ?")
                params.append(face)
            if skin is not None:
                updates.append("skin = ?")
                params.append(skin)
            if top is not None:
                updates.append("top = ?")
                params.append(top)
            if bottom is not None:
                updates.append("bottom = ?")
                params.append(bottom)
            if shoes is not None:
                updates.append("shoes = ?")
                params.append(shoes)
            
            if not updates:
                await interaction.response.send_message("請至少指定一個要更新的外觀選項！", ephemeral=True)
                return
            
            params.append(interaction.user.id)
            
            # 更新資料庫
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
            cursor.execute(query, params)
            conn.commit()
            conn.close()
            
            # 建構回應訊息
            updated_items = []
            if hair is not None:
                updated_items.append(f"髮型: {hair}")
            if face is not None:
                updated_items.append(f"臉型: {face}")
            if skin is not None:
                updated_items.append(f"膚色: {skin}")
            if top is not None:
                updated_items.append(f"上衣: {top}")
            if bottom is not None:
                updated_items.append(f"下裝: {bottom}")
            if shoes is not None:
                updated_items.append(f"鞋子: {shoes}")
            
            response_text = f"✅ 角色外觀已更新！\n{chr(10).join(updated_items)}"
            await interaction.response.send_message(response_text, ephemeral=True)
            
        except Exception as e:
            print(f"設定外觀時發生錯誤: {e}")
            await interaction.response.send_message("❌ 設定外觀時發生錯誤！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserPanel(bot))