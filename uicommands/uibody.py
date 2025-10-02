import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import json
import os
import aiohttp
import io
import asyncio
from typing import Optional
from dotenv import load_dotenv
from PIL import Image
import time
import hashlib
from pathlib import Path
import datetime

load_dotenv()

class UpdatePanelView(discord.ui.View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        if not hasattr(UpdatePanelView, 'last_update'):
            UpdatePanelView.last_update = {}
        
    @discord.ui.button(label="更新面板", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="update_panel_button")
    async def update_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_time = time.time()
        last_update_time = UpdatePanelView.last_update.get(interaction.user.id, 0)
        
        if current_time - last_update_time < 5:
            remaining_time = 5 - (current_time - last_update_time)
            await interaction.response.send_message(f"⏰ 請等待 {remaining_time:.1f} 秒後再更新面板！", ephemeral=True)
            return
            
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 你只能更新自己的面板！", ephemeral=True)
            return
            
        try:
            await interaction.response.defer()
            UpdatePanelView.last_update[interaction.user.id] = current_time
            
            user_data = self.cog.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.followup.send("❌ 沒有找到你的資料！", ephemeral=True)
                return
            
            embed = await self.cog.create_user_embed(user_data, interaction.user)
            character_image_url = await self.cog.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)
            
            async for message in interaction.channel.history(limit=50, oldest_first=True):
                if (message.embeds and message.author == self.cog.bot.user and
                    f"{interaction.user.display_name or interaction.user.name} 的置物櫃" in message.embeds[0].title):
                    try:
                        await message.edit(embed=embed)
                        await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
                        return
                    except (discord.NotFound, Exception):
                        break
            
            await interaction.followup.send("❌ 找不到面板訊息，請聯繫管理員！", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send("❌ 更新面板時發生錯誤！", ephemeral=True)

class UserPanel(commands.Cog):
def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        self.FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
        self.image_storage_channel_id = int(os.getenv('IMAGE_STORAGE_CHANNEL_ID', '0'))
        self.welcome_channel_id = int(os.getenv('WELCOME_CHANNEL_ID', '0'))
        
        # AI 設定
        self.AI_API_KEY = os.getenv('AI_API_KEY')
        self.AI_API_URL = os.getenv('AI_API_URL')
        self.AI_API_MODEL = os.getenv('AI_API_MODEL')
        
        # 圖片緩存設定
        self.cache_dir = Path('./character_images')
        self.cache_dir.mkdir(exist_ok=True)
        
        # 註冊永久視圖
        self.bot.add_view(UpdatePanelView(self, 0))
        
        self.init_database()

    def init_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        level INTEGER DEFAULT 1,
                        xp INTEGER DEFAULT 0,
                        kkcoin INTEGER DEFAULT 0,
                        title TEXT DEFAULT '新手',
                        hp INTEGER DEFAULT 100,
                        stamina INTEGER DEFAULT 100,
                        inventory TEXT DEFAULT '[]',
                        character_config TEXT DEFAULT '{}',
                        face INTEGER DEFAULT 20000,
                        hair INTEGER DEFAULT 30000,
                        skin INTEGER DEFAULT 12000,
                        top INTEGER DEFAULT 1040010,
                        bottom INTEGER DEFAULT 1060096,
                        shoes INTEGER DEFAULT 1072288,
                        is_stunned INTEGER DEFAULT 0,
                        gender TEXT DEFAULT 'male',
                        thread_id INTEGER DEFAULT 0,
                        last_kkcoin_snapshot INTEGER DEFAULT 0,
                        last_xp_snapshot INTEGER DEFAULT 0,
                        last_level_snapshot INTEGER DEFAULT 1
                    )
                ''')
            else:
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                new_columns = [
                    ("face", "INTEGER DEFAULT 20000"), ("hair", "INTEGER DEFAULT 30000"), 
                    ("skin", "INTEGER DEFAULT 12000"), ("top", "INTEGER DEFAULT 1040010"),
                    ("bottom", "INTEGER DEFAULT 1060096"), ("shoes", "INTEGER DEFAULT 1072288"),
                    ("is_stunned", "INTEGER DEFAULT 0"), ("gender", "TEXT DEFAULT 'male'"),
                    ("thread_id", "INTEGER DEFAULT 0"), ("last_kkcoin_snapshot", "INTEGER DEFAULT 0"),
                    ("last_xp_snapshot", "INTEGER DEFAULT 0"), ("last_level_snapshot", "INTEGER DEFAULT 1")
                ]
                
                for column_name, column_def in new_columns:
                    if column_name not in columns:
                        try:
                            cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
                        except Exception:
                            pass

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_cache'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE image_cache (
                        cache_key TEXT PRIMARY KEY,
                        discord_url TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        message_id INTEGER
                    )
                ''')
            
            conn.commit()
            conn.close()
            
        except Exception:
            pass

    def generate_character_cache_key(self, user_data: dict) -> str:
        key_parts = [
            str(user_data.get('face', 20000)), str(user_data.get('hair', 30000)),
            str(user_data.get('skin', 12000)), str(user_data.get('top', 1040010)),
            str(user_data.get('bottom', 1060096)), str(user_data.get('shoes', 1072288)),
            str(user_data.get('is_stunned', 0))
        ]
        key_string = "_".join(key_parts)
        return f"char_{hashlib.md5(key_string.encode()).hexdigest()}"

    def get_cached_discord_url(self, cache_key: str) -> Optional[str]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
            cursor.execute("DELETE FROM image_cache WHERE created_at < ?", (thirty_days_ago,))
            cursor.execute("SELECT discord_url FROM image_cache WHERE cache_key = ?", (cache_key,))
            result = cursor.fetchone()
            
            conn.commit()
            conn.close()
            return result[0] if result else None
            
        except Exception:
            return None

    def save_discord_url_cache(self, cache_key: str, discord_url: str, message_id: int = None):
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
            
        except Exception:
            pass

    async def upload_image_to_discord_storage(self, image_data: bytes, cache_key: str) -> Optional[str]:
        try:
            storage_channel_id = self.image_storage_channel_id or self.welcome_channel_id
            channel = self.bot.get_channel(storage_channel_id)
            if not channel:
                return None
            
            file_obj = discord.File(io.BytesIO(image_data), filename=f'{cache_key}.png')
            
            if storage_channel_id == self.welcome_channel_id:
                temp_msg = await channel.send(file=file_obj)
                if temp_msg.attachments:
                    discord_url = temp_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, temp_msg.id)
                    try:
                        await asyncio.sleep(0.1)
                        await temp_msg.delete()
                    except discord.NotFound:
                        pass
                    return discord_url
            else:
                storage_msg = await channel.send(content=f"🖼️ **角色圖片** - {cache_key}", file=file_obj)
                if storage_msg.attachments:
                    discord_url = storage_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, storage_msg.id)
                    return discord_url
            
        except Exception:
            pass
        return None

    async def get_character_image_url(self, user_data: dict) -> Optional[str]:
        cache_key = self.generate_character_cache_key(user_data)
        cached_url = self.get_cached_discord_url(cache_key)
        if cached_url:
            return cached_url
        
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

            if user_data.get('is_stunned', 0) == 1:
                items.append({"itemId": 1005411, "region": "GMS", "version": "217"})

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            discord_url = await self.upload_image_to_discord_storage(image_data, cache_key)
                            if discord_url:
                                return discord_url

        except Exception:
            pass
        return None

    async def cog_load(self):
        await self.bot.wait_until_ready()
        
        forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
        if forum_channel and isinstance(forum_channel, discord.ForumChannel):
            await self.create_threads_for_existing_members()
        
        # 啟動週統計任務
        if not self.weekly_summary.is_running():
            self.weekly_summary.start()

    def cog_unload(self):
        if self.weekly_summary.is_running():
            self.weekly_summary.cancel()

    @tasks.loop(minutes=1)
    async def weekly_summary(self):
        """每週日晚上 23:59 執行週統計"""
        try:
            # 獲取當前時間（使用台灣時區 UTC+8）
            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            
            # 檢查是否為週日 23:59
            if now.weekday() != 6:  # 6 = 週日 (0=週一, 6=週日)
                return
                
            if now.hour != 23 or now.minute != 59:
                return
            
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, thread_id, kkcoin, xp, level, 
                       last_kkcoin_snapshot, last_xp_snapshot, last_level_snapshot 
                FROM users WHERE thread_id != 0
            ''')
            users_data = cursor.fetchall()
            
            for user_id, thread_id, current_kkcoin, current_xp, current_level, last_kkcoin, last_xp, last_level in users_data:
                try:
                    thread = forum_channel.get_thread(thread_id)
                    member = forum_channel.guild.get_member(user_id)
                    
                    if not thread or not member:
                        continue
                    
# 計算週增長量
                    kkcoin_change = (current_kkcoin or 0) - (last_kkcoin or 0)
                    xp_change = (current_xp or 0) - (last_xp or 0)
                    level_change = (current_level or 1) - (last_level or 1)
                    
                    # 只有當有變化時才發送統計
                    if kkcoin_change > 0 or xp_change > 0 or level_change > 0:
                        # 生成 AI 評論
                        ai_comment = await self.generate_ai_comment(member, kkcoin_change, xp_change, level_change)
                        
                        # 創建統計嵌入
                        embed = discord.Embed(
                            title=f"📊 {member.display_name or member.name} 的本週統計",
                            description=f"統計週期：{(now - datetime.timedelta(days=7)).strftime('%m/%d')} - {now.strftime('%m/%d')}",
                            color=0x00ff88,
                            timestamp=discord.utils.utcnow()
                        )
                        embed.set_thumbnail(url=member.display_avatar.url)
                        
                        if kkcoin_change > 0:
                            embed.add_field(name="💰 KKCoin 增長", value=f"+{kkcoin_change}", inline=True)
                        if xp_change > 0:
                            embed.add_field(name="✨ 經驗值 增長", value=f"+{xp_change}", inline=True)
                        if level_change > 0:
                            embed.add_field(name="⭐ 等級 提升", value=f"+{level_change}", inline=True)
                        
                        if ai_comment:
                            embed.add_field(name="🤖 AI 評論", value=ai_comment, inline=False)
                        
                        embed.set_footer(text="🔄 每週日 23:59 自動統計")
                        
                        # 發送統計訊息
                        await thread.send(embed=embed)
                        await asyncio.sleep(1)
                        
                    # 更新快照數據（無論是否有變化都要更新，避免累積誤差）
                    cursor.execute('''
                        UPDATE users 
                        SET last_kkcoin_snapshot = ?, last_xp_snapshot = ?, last_level_snapshot = ?
                        WHERE user_id = ?
                    ''', (current_kkcoin, current_xp, current_level, user_id))
                    
                except Exception:
                    continue
            
            conn.commit()
            conn.close()
            
        except Exception:
            pass

    @weekly_summary.before_loop
    async def before_weekly_summary(self):
        await self.bot.wait_until_ready()

    async def generate_ai_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        try:
            if not all([self.AI_API_KEY, self.AI_API_URL, self.AI_API_MODEL]):
                return None
            
            prompt = f"""你是一個友善的遊戲助手，請為玩家 {member.display_name or member.name} 本週的表現寫一段鼓勵性的評論。

本週數據：
- KKCoin 增長: {kkcoin_change}
- 經驗值 增長: {xp_change}
- 等級 提升: {level_change}

請用繁體中文回應，語氣要活潑友善，長度控制在50字以內，可以適當使用表情符號。
"""
            
            headers = {
                'Authorization': f'Bearer {self.AI_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.AI_API_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 100,
                'temperature': 0.8
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.AI_API_URL, headers=headers, json=data, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
            
        except Exception:
            pass
        
        return f"本週表現不錯！繼續保持這個節奏 💪"

    def ensure_user_exists(self, user_id: int) -> bool:
        """確保使用者在資料庫中存在，如果不存在則創建"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 檢查使用者是否存在
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                conn.close()
                return True
            
            # 創建新使用者
            cursor.execute('''
                INSERT INTO users (user_id, level, xp, kkcoin, title, hp, stamina, inventory, 
                                 character_config, face, hair, skin, top, bottom, shoes, 
                                 is_stunned, gender, thread_id, last_kkcoin_snapshot, 
                                 last_xp_snapshot, last_level_snapshot)
                VALUES (?, 1, 0, 0, '新手', 100, 100, '[]', '{}', 20000, 30000, 12000, 
                       1040010, 1060096, 1072288, 0, 'male', 0, 0, 0, 1)
            ''', (user_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception:
            return False

    async def create_threads_for_existing_members(self):
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            guild = forum_channel.guild
            
            # 檢查機器人權限
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                return
                
            permissions = forum_channel.permissions_for(bot_member)
            if not permissions.send_messages or not permissions.create_public_threads:
                return
            
            # 獲取資料庫中的所有使用者
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, thread_id FROM users')
            all_users = cursor.fetchall()
            conn.close()
            
            for user_id, thread_id in all_users:
                try:
                    member = guild.get_member(user_id)
                    if not member:
                        continue
                    
                    needs_thread = not thread_id or thread_id == 0
                    
                    # 檢查現有文章是否仍然存在
                    if thread_id and thread_id != 0:
                        thread = forum_channel.get_thread(thread_id)
                        if thread:
                            continue
                        else:
                            # 重置 thread_id
                            conn = sqlite3.connect(self.db_path)
                            cursor = conn.cursor()
                            cursor.execute('UPDATE users SET thread_id = 0 WHERE user_id = ?', (user_id,))
                            conn.commit()
                            conn.close()
                            needs_thread = True
                    
                    # 需要創建新文章
                    if needs_thread:
                        try:
                            thread = await self.get_or_create_user_thread(member)
                            if thread:
                                await asyncio.sleep(2)
                        except discord.HTTPException as e:
                            if e.status == 429:  # Rate limit
                                await asyncio.sleep(30)
                                # 重試一次
                                try:
                                    await self.get_or_create_user_thread(member)
                                    await asyncio.sleep(5)
                                except Exception:
                                    pass
                        except Exception:
                            continue
                            
                except Exception:
                    continue
            
        except Exception:
            pass

    def get_user_data(self, user_id: int) -> Optional[dict]:
        try:
            # 先確保使用者存在
            if not self.ensure_user_exists(user_id):
                return None
                
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, level, xp, kkcoin, title, hp, stamina, 
                inventory, character_config, face, hair, skin, 
                top, bottom, shoes, is_stunned, gender, thread_id
                FROM users WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'user_id': row[0], 'level': row[1], 'xp': row[2], 'kkcoin': row[3],
                    'title': row[4], 'hp': row[5], 'stamina': row[6], 'inventory': row[7],
                    'character_config': row[8], 'face': row[9] or 20000, 'hair': row[10] or 30000,
                    'skin': row[11] or 12000, 'top': row[12] or 1040010, 'bottom': row[13] or 1060096,
                    'shoes': row[14] or 1072288, 'is_stunned': row[15] or 0, 'gender': row[16] or 'male',
                    'thread_id': row[17] or 0
                }
            return None
        except Exception:
            return None

    def create_progress_bar(self, current: int, maximum: int, length: int = 10) -> str:
        if maximum == 0:
            percentage = 0
        else:
            percentage = max(0, min(1, current / maximum))
        filled = int(length * percentage)
        return '█' * filled + '░' * (length - filled)

    async def create_user_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 {user.display_name or user.name} 的置物櫃",
            color=0x00ff88,
            timestamp=discord.utils.utcnow()
        )
        
        try:
            embed.set_thumbnail(url=user.display_avatar.url)
        except:
            pass
            
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
                inventory = inventory_str[:50] + '...' if len(inventory_str) > 50 else inventory_str
        embed.add_field(name="🎒 物品欄", value=inventory, inline=False)
        
        embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
        return embed

    async def get_or_create_user_thread(self, user: discord.User) -> Optional[discord.Thread]:
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return None

            # 確保使用者在資料庫中存在
            if not self.ensure_user_exists(user.id):
                return None

            user_data = self.get_user_data(user.id)
            if not user_data:
                return None

            # 檢查是否已有文章
            thread_id = user_data.get('thread_id', 0)
            if thread_id:
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    return thread
                else:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute('UPDATE users SET thread_id = 0 WHERE user_id = ?', (user.id,))
                    conn.commit()
                    conn.close()
            
            # 檢查機器人權限
            bot_member = forum_channel.guild.get_member(self.bot.user.id)
            if not bot_member:
                return None
                
            permissions = forum_channel.permissions_for(bot_member)
            if not permissions.send_messages or not permissions.create_public_threads:
                return None
            
            # 創建面板
            embed = await self.create_user_embed(user_data, user)
            
            # 獲取角色圖片（非阻塞）
            try:
                character_image_url = await self.get_character_image_url(user_data)
                if character_image_url:
                    embed.set_image(url=character_image_url)
            except Exception:
                pass

            # 創建文章標題
            thread_name = f"📦 {user.display_name or user.name} 的置物櫃"
            
            # 創建 View
            view = UpdatePanelView(self, user.id)
            
            # 嘗試創建文章
            try:
                thread, message = await forum_channel.create_thread(name=thread_name, embed=embed, view=view)
            except discord.HTTPException as http_e:
                if http_e.status == 400:
                    # 可能是 embed 或 view 問題，嘗試只用基本內容
                    simple_embed = discord.Embed(
                        title=f"📦 {user.display_name or user.name} 的置物櫃",
                        description="正在載入使用者資料...",
                        color=0x00ff88
                    )
                    thread, message = await forum_channel.create_thread(name=thread_name, embed=simple_embed)
                    # 然後更新為完整內容
                    await message.edit(embed=embed, view=view)
                else:
                    raise

            # 更新資料庫
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET thread_id = ? WHERE user_id = ?', (thread.id, user.id))
            conn.commit()
            conn.close()
            
            return thread

        except (discord.Forbidden, discord.HTTPException, Exception):
            pass
        
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """當有新成員加入時自動創建資料庫記錄和文章"""
        try:
            # 確保使用者在資料庫中存在
            if self.ensure_user_exists(member.id):
                # 等待一下讓成員完全加入
                await asyncio.sleep(2)
                
                # 嘗試創建文章
                await self.get_or_create_user_thread(member)
                
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            user_data = self.get_user_data(member.id)
            if not user_data or not user_data.get('thread_id'):
                return

            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            thread_id = user_data['thread_id']
            try:
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    await thread.delete()
            except (discord.NotFound, Exception):
                pass

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET thread_id = 0 WHERE user_id = ?', (member.id,))
            conn.commit()
            conn.close()

        except Exception:
            pass

async def setup(bot):
    await bot.add_cog(UserPanel(bot))
