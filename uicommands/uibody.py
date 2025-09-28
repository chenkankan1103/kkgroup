@tasks.loop(minutes=1)  # 每分鐘執行一次
    async def auto_update_top_users(self):
        """每分鐘自動更新排行榜前10名使用者的面板"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel orimport discord
from discord.ext import commands, tasks
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
import time
from datetime import datetime, timedelta

load_dotenv()

class UpdatePanelView(discord.ui.View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        # 使用類級別的字典來儲存冷卻時間
        if not hasattr(UpdatePanelView, 'last_update'):
            UpdatePanelView.last_update = {}
        
    @discord.ui.button(label="更新面板", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="update_panel_button")
    async def update_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 檢查冷卻時間（5秒）
        current_time = time.time()
        last_update_time = UpdatePanelView.last_update.get(interaction.user.id, 0)
        
        if current_time - last_update_time < 5:
            remaining_time = 5 - (current_time - last_update_time)
            await interaction.response.send_message(
                f"⏰ 請等待 {remaining_time:.1f} 秒後再更新面板！", 
                ephemeral=True
            )
            return
            
        # 只允許房間擁有者更新自己的面板
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 你只能更新自己的面板！", ephemeral=True)
            return
            
        try:
            await interaction.response.defer()
            
            # 更新最後更新時間
            UpdatePanelView.last_update[interaction.user.id] = current_time
            
            user_data = self.cog.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.followup.send("❌ 沒有找到你的資料！", ephemeral=True)
                return
            
            embed = await self.cog.create_user_embed(user_data, interaction.user)
            character_image = await self.cog.fetch_character_image(user_data)
            
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.gif")
            
            # 找到文章的第一則訊息並更新它
            async for message in interaction.channel.history(limit=50, oldest_first=True):
                if message.embeds and message.author == self.cog.bot.user:
                    # 檢查是否是面板訊息（第一則包含面板的訊息）
                    if f"{interaction.user.display_name or interaction.user.name} 的面板資訊" in message.embeds[0].title:
                        try:
                            await message.edit(embed=embed, attachments=files)
                            await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
                            return
                        except discord.NotFound:
                            break
                        except Exception as e:
                            print(f"更新面板訊息時發生錯誤: {e}")
                            break
            
            # 如果沒找到原始訊息，發送錯誤訊息
            await interaction.followup.send("❌ 找不到面板訊息，請聯繫管理員！", ephemeral=True)
            
        except Exception as e:
            print(f"更新面板時發生錯誤: {e}")
            await interaction.followup.send("❌ 更新面板時發生錯誤！", ephemeral=True)

class UserPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        self.FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
        
        # AI 設定
        self.AI_API_KEY = os.getenv('AI_API_KEY')
        self.AI_API_URL = os.getenv('AI_API_URL')
        self.AI_API_MODEL = os.getenv('AI_API_MODEL')
        
        self.assets_path = './assets'
        self.equipment_path = os.path.join(self.assets_path, 'equipment')
        
        os.makedirs(self.equipment_path, exist_ok=True)
        
        self.init_database()

    def init_database(self):
        """初始化資料庫，添加新欄位"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 檢查是否存在 users 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                # 如果表不存在，創建它
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
                print("✅ 創建 users 表")
            else:
                # 表存在，檢查並添加缺少的欄位
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                new_columns = [
                    ("face", "INTEGER DEFAULT 20000"),
                    ("hair", "INTEGER DEFAULT 30000"), 
                    ("skin", "INTEGER DEFAULT 12000"),
                    ("top", "INTEGER DEFAULT 1040010"),
                    ("bottom", "INTEGER DEFAULT 1060096"),
                    ("shoes", "INTEGER DEFAULT 1072288"),
                    ("is_stunned", "INTEGER DEFAULT 0"),
                    ("gender", "TEXT DEFAULT 'male'"),
                    ("thread_id", "INTEGER DEFAULT 0"),
                    ("last_kkcoin_snapshot", "INTEGER DEFAULT 0"),
                    ("last_xp_snapshot", "INTEGER DEFAULT 0"),
                    ("last_level_snapshot", "INTEGER DEFAULT 1")
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

    async def cog_load(self):
        """當 Cog 加載時啟動任務"""
        await self.bot.wait_until_ready()
        await self.create_threads_for_existing_members()
        self.weekly_summary.start()
        print("✅ 已為現有會員創建文章並開始每週統計任務")

    def cog_unload(self):
        """當 Cog 卸載時停止任務"""
        self.weekly_summary.cancel()

    async def create_threads_for_existing_members(self):
        """為所有現有會員創建個人文章"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print(f"論壇頻道 {self.FORUM_CHANNEL_ID} 不存在或不是論壇頻道")
                return

            guild = forum_channel.guild
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 獲取所有已註冊的使用者
            cursor.execute('SELECT user_id, thread_id FROM users')
            all_users = cursor.fetchall()
            
            created_count = 0
            validated_count = 0
            
            for user_id, thread_id in all_users:
                member = guild.get_member(user_id)
                if not member:  # 成員不在伺服器中，跳過
                    continue
                
                # 如果沒有 thread_id，創建新文章
                if not thread_id or thread_id == 0:
                    thread = await self.get_or_create_user_thread(member)
                    if thread:
                        created_count += 1
                        # 避免 API 限制，每創建一個文章後稍微等待
                        await asyncio.sleep(1)
                else:
                    # 如果有 thread_id，驗證文章是否還存在
                    try:
                        thread = forum_channel.get_thread(thread_id)
                        if thread:
                            validated_count += 1
                        else:
                            # 文章不存在，清除記錄並重新創建
                            cursor.execute('UPDATE users SET thread_id = 0 WHERE user_id = ?', (user_id,))
                            conn.commit()
                            
                            thread = await self.get_or_create_user_thread(member)
                            if thread:
                                created_count += 1
                                await asyncio.sleep(1)
                    except Exception as e:
                        print(f"驗證使用者 {user_id} 的文章時發生錯誤: {e}")
            
            conn.close()
            print(f"✅ 驗證了 {validated_count} 個現有文章，為 {created_count} 位會員創建了新文章")
            
        except Exception as e:
            print(f"為現有會員創建文章時發生錯誤: {e}")

    @tasks.loop(hours=168)  # 每週執行一次 (168小時 = 7天)
    async def weekly_summary(self):
        """每週發布統計總結"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 獲取所有有文章的使用者
            cursor.execute('SELECT user_id, thread_id, kkcoin, xp, level, last_kkcoin_snapshot, last_xp_snapshot, last_level_snapshot FROM users WHERE thread_id != 0')
            users_data = cursor.fetchall()
            
            for user_id, thread_id, current_kkcoin, current_xp, current_level, last_kkcoin, last_xp, last_level in users_data:
                try:
                    thread = forum_channel.get_thread(thread_id)
                    member = forum_channel.guild.get_member(user_id)
                    
                    if not thread or not member:
                        continue
                    
                    # 計算本週變化
                    kkcoin_change = (current_kkcoin or 0) - (last_kkcoin or 0)
                    xp_change = (current_xp or 0) - (last_xp or 0)
                    level_change = (current_level or 1) - (last_level or 1)
                    
                    # 只為有變化的使用者發布統計（活躍篩選）
                    if kkcoin_change > 0 or xp_change > 0 or level_change > 0:
                        # 生成 AI 評論
                        ai_comment = await self.generate_ai_comment(member, kkcoin_change, xp_change, level_change)
                        
                        # 創建週報 embed
                        embed = discord.Embed(
                            title=f"📊 {member.display_name or member.name} 的本週統計",
                            color=0x00ff88,
                            timestamp=discord.utils.utcnow()
                        )
                        embed.set_thumbnail(url=member.display_avatar.url)
                        
                        # 添加統計欄位
                        if kkcoin_change > 0:
                            embed.add_field(name="💰 KKCoin 增長", value=f"+{kkcoin_change}", inline=True)
                        if xp_change > 0:
                            embed.add_field(name="✨ 經驗值 增長", value=f"+{xp_change}", inline=True)
                        if level_change > 0:
                            embed.add_field(name="⭐ 等級 提升", value=f"+{level_change}", inline=True)
                        
                        # 添加 AI 評論
                        if ai_comment:
                            embed.add_field(name="🤖 AI 評論", value=ai_comment, inline=False)
                        
                        embed.set_footer(text="🔄 每週自動更新統計")
                        
                        # 發送到使用者的個人文章，並附上更新按鈕
                        view = UpdatePanelView(self, user_id)
                        await thread.send(embed=embed, view=view)
                        print(f"✅ 已為 {member.name} 發布週報並提供更新按鈕")
                        
                        # 稍微等待避免 API 限制
                        await asyncio.sleep(0.5)
                    
                    # 更新快照數據
                    cursor.execute('''
                        UPDATE users 
                        SET last_kkcoin_snapshot = ?, last_xp_snapshot = ?, last_level_snapshot = ?
                        WHERE user_id = ?
                    ''', (current_kkcoin, current_xp, current_level, user_id))
                    
                except Exception as e:
                    print(f"處理使用者 {user_id} 週報時發生錯誤: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"生成週報時發生錯誤: {e}")

    async def generate_ai_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """使用 AI 生成個性化評論"""
        try:
            if not all([self.AI_API_KEY, self.AI_API_URL, self.AI_API_MODEL]):
                return None
            
            # 構建提示詞
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
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 100,
                'temperature': 0.8
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.AI_API_URL, headers=headers, json=data, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
            
        except Exception as e:
            print(f"生成 AI 評論時發生錯誤: {e}")
        
        # 如果 AI 失敗，返回預設評論
        return f"本週表現不錯！繼續保持這個節奏 💪"

    def get_user_data(self, user_id: int) -> Optional[dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = """
                SELECT user_id, level, xp, kkcoin, title, hp, stamina, 
                inventory, character_config, face, hair, skin, 
                top, bottom, shoes, is_stunned, gender, thread_id
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
                    'is_stunned': row[15] or 0,
                    'gender': row[16] or 'male',
                    'thread_id': row[17] or 0
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

    async def create_user_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 {user.display_name or user.name} 的面板資訊",
            color=0x00ff88,
            timestamp=discord.utils.utcnow()
        )
        
        # 嘗試使用使用者頭像作為縮圖，如果失敗則使用角色圖片
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
                if len(inventory_str) > 50:
                    inventory = inventory_str[:50] + '...'
                else:
                    inventory = inventory_str
        embed.add_field(name="🎒 物品欄", value=inventory, inline=False)
        
        embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
        
        return embed

    async def get_or_create_user_thread(self, user: discord.User) -> Optional[discord.Thread]:
        """獲取或創建使用者的個人文章"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print(f"論壇頻道 {self.FORUM_CHANNEL_ID} 不存在或不是論壇頻道")
                return None

            user_data = self.get_user_data(user.id)
            if not user_data:
                print(f"沒有找到使用者 {user.id} 的資料")
                return None

            # 檢查是否已有文章
            thread_id = user_data.get('thread_id', 0)
            if thread_id:
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    return thread
                else:
                    # 文章不存在，清除資料庫中的記錄
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute('UPDATE users SET thread_id = 0 WHERE user_id = ?', (user.id,))
                    conn.commit()
                    conn.close()

            # 創建新文章
            embed = await self.create_user_embed(user_data, user)
            character_image = await self.fetch_character_image(user_data)
            
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.gif")

            # 創建文章標題
            thread_name = f"📊 {user.display_name or user.name} 的個人面板"
            
            # 創建文章並直接在第一則訊息中包含面板資訊
            thread, message = await forum_channel.create_thread(
                name=thread_name,
                embed=embed,
                files=files
            )

            # 更新資料庫中的 thread_id
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET thread_id = ? 
                WHERE user_id = ?
            ''', (thread.id, user.id))
            conn.commit()
            conn.close()

            print(f"✅ 為使用者 {user.name} 創建了新的個人文章")
            return thread

        except Exception as e:
            print(f"創建或獲取使用者文章時發生錯誤: {e}")
            return None

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """當成員離開伺服器時刪除其文章"""
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
                    print(f"🗑️ 已刪除離開成員 {member.name} 的個人文章")
            except discord.NotFound:
                pass  # 文章已經不存在
            except Exception as e:
                print(f"刪除離開成員文章時發生錯誤: {e}")

            # 清除資料庫中的 thread_id
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET thread_id = 0 WHERE user_id = ?', (member.id,))
            conn.commit()
            conn.close()

        except Exception as e:
            print(f"處理成員離開事件時發生錯誤: {e}")

    @app_commands.command(name="面板", description="在論壇頻道中查看或創建你的個人面板")
    async def show_panel(self, interaction: discord.Interaction):
        user_data = self.get_user_data(interaction.user.id)
        if not user_data:
            await interaction.response.send_message("❌ 沒有找到你的資料！請先註冊。", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        thread = await self.get_or_create_user_thread(interaction.user)
        if thread:
            await interaction.followup.send(f"✅ 你的個人面板：{thread.mention}", ephemeral=True)
        else:
            await interaction.followup.send("❌ 創建或獲取個人面板時發生錯誤！", ephemeral=True)

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

    @app_commands.command(name="手動週報", description="管理員指令：手動觸發週報生成")
    @app_commands.default_permissions(administrator=True)
    async def manual_weekly_summary(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            await self.weekly_summary()
            await interaction.followup.send("✅ 已完成週報生成！")
        except Exception as e:
            await interaction.followup.send(f"❌ 生成週報時發生錯誤：{str(e)}")

    @app_commands.command(name="初始化文章", description="管理員指令：為所有現有會員創建個人文章")
    @app_commands.default_permissions(administrator=True)
    async def initialize_threads(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            await self.create_threads_for_existing_members()
            await interaction.followup.send("✅ 已為所有現有會員創建個人文章！")
        except Exception as e:
            await interaction.followup.send(f"❌ 創建文章時發生錯誤：{str(e)}")

    @app_commands.command(name="重置文章", description="管理員指令：清除所有文章記錄（不刪除實際文章）")
    @app_commands.default_permissions(administrator=True)
    async def reset_threads(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET thread_id = 0')
            conn.commit()
            conn.close()
            
            await interaction.followup.send("✅ 已清除所有文章記錄！下次重啟機器人時會重新檢查並創建缺少的文章。")
        except Exception as e:
            await interaction.followup.send(f"❌ 重置時發生錯誤：{str(e)}")

    @app_commands.command(name="檢查文章", description="管理員指令：檢查並修復文章狀態")
    @app_commands.default_permissions(administrator=True)
    async def check_threads(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            await self.create_threads_for_existing_members()
            await interaction.followup.send("✅ 已完成文章狀態檢查和修復！")
        except Exception as e:
            await interaction.followup.send(f"❌ 檢查時發生錯誤：{str(e)}")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 統計資料
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE thread_id != 0')
            users_with_threads = cursor.fetchone()[0]
            
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if forum_channel and isinstance(forum_channel, discord.ForumChannel):
                total_threads = len(forum_channel.threads)
            else:
                total_threads = 0
            
            conn.close()
            
            embed = discord.Embed(
                title="📊 論壇統計資訊",
                color=0x00ff88,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="👥 總註冊使用者", value=f"{total_users} 人", inline=True)
            embed.add_field(name="📝 擁有個人文章", value=f"{users_with_threads} 人", inline=True)
            embed.add_field(name="🏷️ 論壇總文章數", value=f"{total_threads} 個", inline=True)
            
            if forum_channel:
                embed.add_field(name="📍 論壇頻道", value=forum_channel.mention, inline=False)
            
            await interaction.response.send_message(embed=embed)
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 統計資料
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE thread_id != 0')
            users_with_threads = cursor.fetchone()[0]
            
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if forum_channel and isinstance(forum_channel, discord.ForumChannel):
                total_threads = len(forum_channel.threads)
            else:
                total_threads = 0
            
            conn.close()
            
            embed = discord.Embed(
                title="📊 論壇統計資訊",
                color=0x00ff88,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="👥 總註冊使用者", value=f"{total_users} 人", inline=True)
            embed.add_field(name="📝 擁有個人文章", value=f"{users_with_threads} 人", inline=True)
            embed.add_field(name="🏷️ 論壇總文章數", value=f"{total_threads} 個", inline=True)
            
            if forum_channel:
                embed.add_field(name="📍 論壇頻道", value=forum_channel.mention, inline=False)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ 獲取統計時發生錯誤：{str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserPanel(bot))
