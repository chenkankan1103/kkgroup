import discord
from discord.ext import commands, tasks
import random
import asyncio
from typing import Optional
import datetime
import os
import aiohttp
import urllib.parse
import math
from db_adapter import get_user, set_user_field, get_user_field, get_all_users

class ScamParkEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        self.FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
        
        # AI 設定
        self.AI_API_KEY = os.getenv('AI_API_KEY')
        self.AI_API_URL = os.getenv('AI_API_URL')
        self.AI_API_MODEL = os.getenv('AI_API_MODEL')
        
        # 事件設定 - 調整為12小時常態分佈
        self.event_cooldown = {}  # 使用者事件冷卻 {user_id: last_event_timestamp}
        self.min_event_interval = 43200   # 最少12小時 (秒)
        self.max_event_interval = 86400   # 最多24小時 (秒)
        
        # 事件訊息追蹤
        self.event_messages = {}  # 存儲使用者的事件訊息ID {user_id: message_id}
        
        # 機器人啟動標記
        self.bot_ready = False
        
        # 初始化資料庫表格
        self.init_event_database()
        
        # 從資料庫載入上次事件時間
        self.load_last_event_times()
        
        # 啟動隨機事件任務
        if not self.random_event_trigger.is_running():
            self.random_event_trigger.start()

    def init_event_database(self):
        """初始化事件追蹤資料表（使用記憶體字典）"""
        try:
            # Initialize in-memory event history
            # Format: {user_id: {'last_event_time': float, 'last_message_id': int, 'event_count': int, 'last_event_type': str}}
            if not hasattr(self, 'event_history'):
                self.event_history = {}
            print("✅ 事件資料庫初始化完成")
        except Exception as e:
            print(f"❌ 初始化事件資料庫錯誤: {e}")

    def load_last_event_times(self):
        """從記憶體載入上次事件時間"""
        try:
            # Load event history from memory dictionary
            # Note: Since we're using in-memory storage, this mainly initializes from self.event_cooldown
            # which is already populated by init
            for user_id, last_time in self.event_cooldown.items():
                if user_id not in self.event_history:
                    self.event_history[user_id] = {
                        'last_event_time': last_time,
                        'last_message_id': self.event_messages.get(user_id),
                        'event_count': 0,
                        'last_event_type': None
                    }
            
            print(f"✅ 載入 {len(self.event_history)} 筆事件歷史記錄")
        except Exception as e:
            print(f"❌ 載入事件歷史錯誤: {e}")

    def save_event_time(self, user_id: int, message_id: int = None, event_type: str = None):
        """儲存事件觸發時間到記憶體"""
        try:
            current_time = datetime.datetime.now().timestamp()
            
            if user_id in self.event_history:
                self.event_history[user_id]['last_event_time'] = current_time
                self.event_history[user_id]['last_message_id'] = message_id
                self.event_history[user_id]['event_count'] = self.event_history[user_id].get('event_count', 0) + 1
                self.event_history[user_id]['last_event_type'] = event_type
            else:
                self.event_history[user_id] = {
                    'last_event_time': current_time,
                    'last_message_id': message_id,
                    'event_count': 1,
                    'last_event_type': event_type
                }
        except Exception as e:
            print(f"❌ 儲存事件時間錯誤: {e}")

    def cog_unload(self):
        if self.random_event_trigger.is_running():
            self.random_event_trigger.cancel()

    @tasks.loop(minutes=20)  # 每20分鐘檢查一次
    async def random_event_trigger(self):
        """隨機觸發園區事件 - 每個使用者獨立計算觸發時間"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            # Use db_adapter to get all users
            all_users = get_all_users()
            current_time = datetime.datetime.now().timestamp()
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id', 0)
                kkcoin = user_data.get('kkcoin', 0)
                level = user_data.get('level', 1)
                hp = user_data.get('hp', 100)
                stamina = user_data.get('stamina', 100)
                
                if not thread_id or thread_id == 0:
                    continue
                # 檢查冷卻時間
                last_event = self.event_cooldown.get(user_id, 0)
                time_since_last = current_time - last_event
                
                # 必須超過最小間隔時間
                if time_since_last < self.min_event_interval:
                    continue
                
                # 使用常態分佈計算觸發機率
                time_range = self.max_event_interval - self.min_event_interval
                time_progress = (time_since_last - self.min_event_interval) / time_range
                time_progress = min(1.0, time_progress)
                
                # 使用正態分佈，峰值在中間(0.5位置)
                bell_curve_factor = math.exp(-((time_progress - 0.5) ** 2) / 0.1)
                
                # 基礎觸發機率（降低到2%，配合20分鐘檢查）
                base_chance = 0.02 * bell_curve_factor
                
                # KKCoin加成（有錢的人更容易被盯上）
                wealth_bonus = min(0.03, kkcoin / 1500 * 0.02)
                
                # 超過最大間隔後，強制增加機率
                if time_since_last > self.max_event_interval:
                    overtime_bonus = 0.3  # 30%額外機率
                else:
                    overtime_bonus = 0
                
                trigger_chance = base_chance + wealth_bonus + overtime_bonus
                
                # Debug 日誌（可選）
                if random.random() < 0.05:  # 只記錄5%的檢查
                    print(f"🔍 檢查用戶 {user_id}: 距上次 {time_since_last/3600:.1f}h, "
                          f"機率 {trigger_chance*100:.1f}%, KKCoin {kkcoin}")
                
                if random.random() < trigger_chance:
                    thread = forum_channel.get_thread(thread_id)
                    member = forum_channel.guild.get_member(user_id)
                    
                    if thread and member:
                        print(f"✅ 觸發事件: 用戶 {member.name}, 距上次 {time_since_last/3600:.1f}小時")
                        await self.trigger_random_event(member, thread, kkcoin, level, hp, stamina)
                        self.event_cooldown[user_id] = current_time
                        await asyncio.sleep(2)

        except Exception as e:
            print(f"❌ 隨機事件錯誤: {e}")
            import traceback
            traceback.print_exc()

    @random_event_trigger.before_loop
    async def before_random_event_trigger(self):
        await self.bot.wait_until_ready()
        
        # 檢查並清理已刪除的訊息
        await self.cleanup_deleted_messages()
        
        self.bot_ready = True
        print("🎲 隨機事件系統已啟動")

    async def cleanup_deleted_messages(self):
        """清理已刪除的事件訊息記錄"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print("⚠️ 找不到論壇頻道，跳過清理")
                return

            # Clean up expired entries from memory
            cleaned_count = 0
            for user_id in list(self.event_history.keys()):
                try:
                    # Get user's thread from db_adapter
                    thread_id = get_user_field(user_id, 'thread_id', default=0)
                    if not thread_id or thread_id == 0:
                        continue
                    
                    message_id = self.event_history[user_id].get('last_message_id')
                    if not message_id:
                        continue
                    
                    thread = forum_channel.get_thread(thread_id)
                    
                    if thread:
                        try:
                            # Try to fetch message
                            message = await thread.fetch_message(message_id)
                            # Message exists, update memory record
                            self.event_messages[user_id] = message_id
                        except discord.NotFound:
                            # Message was deleted, clean up record
                            if user_id in self.event_messages:
                                del self.event_messages[user_id]
                            self.event_history[user_id]['last_message_id'] = None
                            cleaned_count += 1
                        except discord.Forbidden:
                            print(f"⚠️ 無權限讀取訊息: {message_id}")
                        except Exception as e:
                            print(f"⚠️ 檢查訊息錯誤: {e}")
                except Exception as e:
                    print(f"⚠️ 處理用戶 {user_id} 時發生錯誤: {e}")
                    continue
            
            if cleaned_count > 0:
                print(f"🧹 已清理 {cleaned_count} 筆無效的事件訊息記錄")
            else:
                print("✅ 所有事件訊息記錄正常")
            
        except Exception as e:
            print(f"❌ 清理訊息記錄錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def generate_pollinations_image(self, prompt: str, is_negative_event: bool = True, scene_variety: int = None) -> str:
        """使用 Pollinations.ai 生成圖片"""
        try:
            if scene_variety is None:
                scene_variety = random.randint(0, 4)
            
            scene_keywords = [
                "indoor office setting, fluorescent lighting",
                "narrow hallway, dim lighting, claustrophobic",
                "surveillance room, multiple monitors",
                "crowded dormitory, bunk beds",
                "basement level, concrete walls"
            ][scene_variety]
            
            atmosphere_options = [
                "late night, exhausted atmosphere",
                "harsh daylight, tense mood",
                "dusk, orange glow through windows",
                "midnight, only computer screens lighting",
                "dawn, tired workers"
            ]
            atmosphere = random.choice(atmosphere_options)
            
            camera_angles = [
                "security camera angle",
                "low angle shot",
                "over shoulder perspective",
                "wide establishing shot",
                "close-up dramatic shot"
            ]
            camera = random.choice(camera_angles)
            
            if is_negative_event:
                style_keywords = "dark, oppressive, dystopian, surveillance, prison atmosphere, gritty realism"
                color_tone = random.choice([
                    "desaturated colors",
                    "cold blue tones",
                    "harsh shadows",
                    "high contrast lighting"
                ])
            else:
                style_keywords = "subtle hope, cinematic, realistic"
                color_tone = random.choice([
                    "warm subtle lighting",
                    "soft natural light",
                    "golden hour glow"
                ])
            
            full_prompt = f"{prompt}, {scene_keywords}, {atmosphere}, {camera}, {style_keywords}, {color_tone}, digital art, high quality, detailed"
            encoded_prompt = urllib.parse.quote(full_prompt)
            seed = random.randint(1, 100000)
            image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=600&nologo=true&seed={seed}"
            
            return image_url
            
        except Exception as e:
            print(f"❌ 生成圖片URL錯誤: {e}")
            return None

    async def translate_to_english(self, chinese_text: str) -> str:
        """將中文提示詞翻譯成英文"""
        try:
            if not all([self.AI_API_KEY, self.AI_API_URL, self.AI_API_MODEL]):
                return chinese_text
            
            headers = {
                'Authorization': f'Bearer {self.AI_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.AI_API_MODEL,
                'messages': [
                    {'role': 'system', 'content': 'You are a translator. Translate Chinese to English for image generation prompts. Keep it concise and descriptive.'},
                    {'role': 'user', 'content': f'Translate this to English for image generation: {chinese_text}'}
                ],
                'max_tokens': 100,
                'temperature': 0.3
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.AI_API_URL, headers=headers, json=data, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
            
        except Exception as e:
            print(f"❌ 翻譯錯誤: {e}")
        
        return chinese_text

    async def generate_ai_event_description(self, event_type: str, details: dict) -> str:
        """使用AI生成事件描述"""
        try:
            if not all([self.AI_API_KEY, self.AI_API_URL, self.AI_API_MODEL]):
                return None
            
            prompt = f"""你是一個詐騙園區的旁白，請用生動的方式描述以下事件：

事件類型：{event_type}
事件詳情：{details}

請用繁體中文回應，語氣要帶有黑色幽默和諷刺，描述要生動且有畫面感，控制在80字以內。
要讓人感受到詐騙園區的壓迫感和絕望氛圍。"""
            
            headers = {
                'Authorization': f'Bearer {self.AI_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.AI_API_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 150,
                'temperature': 0.9
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.AI_API_URL, headers=headers, json=data, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
            
        except Exception as e:
            print(f"❌ AI生成錯誤: {e}")
        
        return None

    async def trigger_random_event(self, member: discord.Member, thread: discord.Thread, 
                                   kkcoin: int, level: int, hp: int, stamina: int):
        """觸發隨機事件"""
        try:
            # 檢查是否已有未處理的事件訊息
            if member.id in self.event_messages:
                old_message_id = self.event_messages[member.id]
                try:
                    old_message = await thread.fetch_message(old_message_id)
                    # 如果訊息存在且是最近的（12小時內），則跳過
                    if old_message.created_at.timestamp() > (datetime.datetime.now().timestamp() - 43200):
                        print(f"⏭️ 用戶 {member.name} 已有近期事件訊息，跳過觸發")
                        return
                except discord.NotFound:
                    # 訊息已被刪除，清除記錄
                    del self.event_messages[member.id]
                except discord.Forbidden:
                    print(f"⚠️ 無權限讀取用戶 {member.name} 的舊訊息")
                except Exception as e:
                    print(f"⚠️ 檢查舊訊息時發生錯誤: {e}")
            
            possible_events = self.get_possible_events(kkcoin, level, hp, stamina)
            
            if not possible_events:
                print(f"⚠️ 用戶 {member.name} 沒有可觸發的事件")
                return

            event = random.choice(possible_events)
            await event['handler'](member, thread, kkcoin, level, hp, stamina)

        except Exception as e:
            print(f"❌ 執行事件錯誤: {e}")
            import traceback
            traceback.print_exc()

    def get_possible_events(self, kkcoin: int, level: int, hp: int, stamina: int) -> list:
        """根據使用者狀態獲取可能的事件"""
        events = []

        # KKCoin相關事件
        if kkcoin > 250:
            events.extend([
                {'handler': self.event_major_confiscation, 'weight': 5},
                {'handler': self.event_protection_fee, 'weight': 4},
                {'handler': self.event_bribe_demand, 'weight': 3},
            ])
        
        if kkcoin > 100:
            events.extend([
                {'handler': self.event_kkcoin_confiscation, 'weight': 4},
                {'handler': self.event_cell_search, 'weight': 3},
                {'handler': self.event_blackmail, 'weight': 3},
                {'handler': self.event_gambling_trap, 'weight': 2},
            ])
        
        if kkcoin > 25:
            events.extend([
                {'handler': self.event_random_inspection, 'weight': 3},
                {'handler': self.event_fine_penalty, 'weight': 3},
                {'handler': self.event_equipment_fee, 'weight': 2},
            ])

        # 體力/HP事件
        if stamina < 50:
            events.extend([
                {'handler': self.event_forced_overtime, 'weight': 3},
                {'handler': self.event_quota_pressure, 'weight': 2},
            ])
        
        if hp < 60:
            events.extend([
                {'handler': self.event_beating, 'weight': 2},
                {'handler': self.event_medical_extortion, 'weight': 2},
            ])

        # 福利事件
        if random.random() < 0.15:
            events.extend([
                {'handler': self.event_police_bribe, 'weight': 1},
                {'handler': self.event_supervisor_favor, 'weight': 1},
            ])

        # 通用事件
        events.extend([
            {'handler': self.event_supervisor_inspection, 'weight': 2},
            {'handler': self.event_group_punishment, 'weight': 2},
            {'handler': self.event_work_accident, 'weight': 2},
            {'handler': self.event_training_hell, 'weight': 1},
            {'handler': self.event_isolation_punishment, 'weight': 1},
        ])

        weighted_events = []
        for event in events:
            weighted_events.extend([event['handler']] * event['weight'])

        return [{'handler': h} for h in weighted_events]

    # ==================== 事件處理函數 ====================

    async def event_major_confiscation(self, member, thread, kkcoin, level, hp, stamina):
        """大額沒收"""
        confiscated = min(kkcoin, random.randint(75, 150))
        
        ai_desc = await self.generate_ai_event_description(
            "大額沒收", 
            {"金額": confiscated, "原因": "發現鉅額私藏"}
        )
        
        image_prompt = await self.translate_to_english("詐騙園區主管搜查房間，發現藏匿的金錢")
        image_url = await self.generate_pollinations_image(
            image_prompt or "scam park supervisor searching room, finding hidden money",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="🚨 重大搜查行動",
            description=ai_desc or "園區主管帶隊突襲，你藏在床墊下的積蓄被翻了出來...",
            color=0xcc0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 沒收金額", value=f"**-{confiscated} KKCoin**", inline=False)
        embed.add_field(name="⚠️ 嚴重警告", value="再次發現將會被關禁閉！", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)
        
        embed.set_footer(text="園區安全管理處")

        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "大額沒收")
        
        self.update_user_kkcoin(member.id, -confiscated)

    async def event_protection_fee(self, member, thread, kkcoin, level, hp, stamina):
        """保護費"""
        fee = min(kkcoin, random.randint(50, 100))
        
        ai_desc = await self.generate_ai_event_description("保護費", {"金額": fee})
        
        image_prompt = await self.translate_to_english("詐騙園區老大收取保護費")
        image_url = await self.generate_pollinations_image(
            image_prompt or "scam park boss collecting protection money, threatening atmosphere",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="💰 保護費收取",
            description=ai_desc or "「想要好好工作？那就得付點保護費...」園區老大笑著說。",
            color=0xff6600,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💸 本月保護費", value=f"-{fee} KKCoin", inline=False)
        embed.add_field(name="🛡️ 效果", value="不交錢的話...後果自負", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "保護費")
        
        self.update_user_kkcoin(member.id, -fee)

    async def event_beating(self, member, thread, kkcoin, level, hp, stamina):
        """毆打事件"""
        hp_loss = random.randint(15, 35)
        stamina_loss = random.randint(10, 20)
        
        ai_desc = await self.generate_ai_event_description("毆打", {"傷害": hp_loss})
        
        image_prompt = await self.translate_to_english("詐騙園區主管暴力懲罰員工")
        image_url = await self.generate_pollinations_image(
            image_prompt or "scam park supervisor violently punishing worker, dark atmosphere",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="👊 暴力懲罰",
            description=ai_desc or "主管心情不好，你成了出氣筒...",
            color=0xaa0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 傷害", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 體力", value=f"-{stamina_loss}", inline=True)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "毆打")
        
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_police_bribe(self, member, thread, kkcoin, level, hp, stamina):
        """警方分贓"""
        gain = random.randint(50, 150)
        
        ai_desc = await self.generate_ai_event_description("警方分贓", {"金額": gain})
        
        image_prompt = await self.translate_to_english("警察偷偷給錢，腐敗場景")
        image_url = await self.generate_pollinations_image(
            image_prompt or "corrupt police secretly giving money, dark deal",
            is_negative_event=False
        )
        
        embed = discord.Embed(
            title="🚔 「特殊關照」",
            description=ai_desc or "外面來「視察」的警察偷偷塞了點錢給你：「這事別說出去...」",
            color=0x0066cc,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 獲得", value=f"+{gain} KKCoin", inline=False)
        embed.add_field(name="🤫 提醒", value="記住，什麼都別說", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "警方分贓")
        
        self.update_user_kkcoin(member.id, gain)

    async def event_bribe_demand(self, member, thread, kkcoin, level, hp, stamina):
        """賄賂要求"""
        bribe = min(kkcoin, random.randint(38, 88))
        embed = discord.Embed(
            title="🤝 主管「建議」", 
            description=f"主管拍了拍你的肩膀：「最近查得很嚴啊，要不要意思意思？」", 
            color=0xaa6600,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💵 「建議金額」", value=f"-{bribe} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "賄賂要求")
        self.update_user_kkcoin(member.id, -bribe)

    async def event_gambling_trap(self, member, thread, kkcoin, level, hp, stamina):
        """賭博陷阱"""
        loss = min(kkcoin, random.randint(25, 75))
        embed = discord.Embed(
            title="🎲 地下賭局", 
            description="「來玩一把吧！」結果...莊家和荷官都是自己人。", 
            color=0x990099,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💸 輸掉的錢", value=f"-{loss} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "賭博陷阱")
        self.update_user_kkcoin(member.id, -loss)

    async def event_fine_penalty(self, member, thread, kkcoin, level, hp, stamina):
        """罰款"""
        fine = min(kkcoin, random.randint(20, 50))
        reasons = ["業績不達標", "遲到5分鐘", "說話太大聲", "上廁所超時", "態度不佳"]
        reason = random.choice(reasons)
        embed = discord.Embed(
            title="📋 違規罰款", 
            description=f"違規原因：{reason}", 
            color=0xff3300,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 罰款金額", value=f"-{fine} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "罰款")
        self.update_user_kkcoin(member.id, -fine)

    async def event_equipment_fee(self, member, thread, kkcoin, level, hp, stamina):
        """設備使用費"""
        fee = min(kkcoin, random.randint(13, 38))
        items = ["電腦", "手機", "椅子", "桌子", "網路"]
        item = random.choice(items)
        embed = discord.Embed(
            title="🔧 設備使用費", 
            description=f"本月{item}使用費到期，請立即繳納。", 
            color=0x666666,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💳 費用", value=f"-{fee} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "設備費")
        self.update_user_kkcoin(member.id, -fee)

    async def event_kkcoin_confiscation(self, member, thread, kkcoin, level, hp, stamina):
        """KKCoin沒收"""
        confiscated = min(kkcoin, random.randint(25, 63))
        embed = discord.Embed(
            title="🚨 突襲搜查", 
            description="管理員突襲檢查你的房間！", 
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 沒收", value=f"-{confiscated} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "KKCoin沒收")
        self.update_user_kkcoin(member.id, -confiscated)

    async def event_forced_overtime(self, member, thread, kkcoin, level, hp, stamina):
        """強制加班"""
        stamina_loss = random.randint(20, 40)
        kkcoin_gain = random.randint(20, 50)
        embed = discord.Embed(
            title="⏰ 強制加班", 
            description="業績不達標，全員加班到天亮！", 
            color=0x990000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="⚡ 體力", value=f"-{stamina_loss}", inline=True)
        embed.add_field(name="💰 收入", value=f"+{kkcoin_gain} KKCoin", inline=True)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "強制加班")
        self.update_user_stats(member.id, kkcoin=kkcoin_gain, stamina=-stamina_loss)

    async def event_medical_extortion(self, member, thread, kkcoin, level, hp, stamina):
        """醫療勒索"""
        cost = min(kkcoin, random.randint(25, 63))
        hp_restore = random.randint(15, 30)
        embed = discord.Embed(
            title="🏥 園區醫療室", 
            description="「想治療？先付錢。」園區醫生冷冷地說。", 
            color=0x666666,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 治療", value=f"+{hp_restore} HP", inline=True)
        embed.add_field(name="💰 費用", value=f"-{cost} KKCoin", inline=True)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "醫療勒索")
        self.update_user_stats(member.id, hp=hp_restore, kkcoin=-cost)

    async def event_cell_search(self, member, thread, kkcoin, level, hp, stamina):
        """牢房搜查"""
        loss = min(kkcoin, random.randint(13, 38))
        embed = discord.Embed(
            title="🔍 牢房搜查", 
            description="安全人員突襲檢查所有牢房...", 
            color=0xff6600,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 沒收物品", value=f"-{loss} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "牢房搜查")
        self.update_user_kkcoin(member.id, -loss)

    async def event_blackmail(self, member, thread, kkcoin, level, hp, stamina):
        """勒索"""
        amount = min(kkcoin, random.randint(20, 50))
        embed = discord.Embed(
            title="😈 勒索", 
            description="「我看到你藏東西了...想要我保密嗎？」", 
            color=0x990066,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💸 封口費", value=f"-{amount} KKCoin", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "勒索")
        self.update_user_kkcoin(member.id, -amount)

    async def event_supervisor_inspection(self, member, thread, kkcoin, level, hp, stamina):
        """主管巡視"""
        stamina_loss = random.randint(10, 20)
        embed = discord.Embed(
            title="👔 主管巡視", 
            description="主管在你背後盯著你工作，壓力山大...", 
            color=0x666666,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="⚡ 精神壓力", value=f"-{stamina_loss} 體力", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "主管巡視")
        self.update_user_stats(member.id, stamina=-stamina_loss)

    async def event_quota_pressure(self, member, thread, kkcoin, level, hp, stamina):
        """業績壓力"""
        stamina_loss = random.randint(15, 30)
        embed = discord.Embed(
            title="📊 業績檢討會", 
            description="「為什麼你的業績這麼差？！」", 
            color=0xcc0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="⚡ 心理壓力", value=f"-{stamina_loss} 體力", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "業績壓力")
        self.update_user_stats(member.id, stamina=-stamina_loss)

    async def event_group_punishment(self, member, thread, kkcoin, level, hp, stamina):
        """連坐處罰"""
        hp_loss = random.randint(10, 20)
        stamina_loss = random.randint(10, 20)
        embed = discord.Embed(
            title="⚠️ 連坐處罰", 
            description="有人犯錯，所有人一起受罰！", 
            color=0x990000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 傷害", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 體力", value=f"-{stamina_loss}", inline=True)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "連坐處罰")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_work_accident(self, member, thread, kkcoin, level, hp, stamina):
        """工作意外"""
        hp_loss = random.randint(15, 30)
        accidents = ["電腦爆炸", "椅子斷裂", "被電線絆倒", "過度疲勞昏倒", "被設備夾傷"]
        accident = random.choice(accidents)
        embed = discord.Embed(
            title="💥 工作意外", 
            description=f"發生意外：{accident}", 
            color=0xff3300,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 受傷", value=f"-{hp_loss} HP", inline=False)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "工作意外")
        self.update_user_stats(member.id, hp=-hp_loss)

    async def event_training_hell(self, member, thread, kkcoin, level, hp, stamina):
        """地獄式訓練"""
        hp_loss = random.randint(10, 25)
        stamina_loss = random.randint(20, 40)
        embed = discord.Embed(
            title="🔥 地獄式訓練", 
            description="「太軟弱了！給我站軍姿三小時！」", 
            color=0xcc3300,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 體能消耗", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 精力耗盡", value=f"-{stamina_loss} 體力", inline=True)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "地獄訓練")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_isolation_punishment(self, member, thread, kkcoin, level, hp, stamina):
        """關禁閉"""
        stamina_loss = random.randint(25, 45)
        hp_loss = random.randint(10, 20)
        embed = discord.Embed(
            title="🚪 關禁閉", 
            description="被關進黑暗的小房間，不給水也不給食物...", 
            color=0x000000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 虛弱", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 精神崩潰", value=f"-{stamina_loss} 體力", inline=True)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "關禁閉")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_random_inspection(self, member, thread, kkcoin, level, hp, stamina):
        """例行檢查"""
        lost_kkcoin = min(kkcoin, random.randint(25, 75))
        embed = discord.Embed(
            title="👮 例行檢查", 
            description="主管進行突擊檢查...", 
            color=0xffa500,
            timestamp=discord.utils.utcnow()
        )
        
        if random.random() < 0.5:
            embed.add_field(name="❌ 發現違禁品", value=f"沒收 {lost_kkcoin} KKCoin", inline=False)
            message = await thread.send(embed=embed)
            self.event_messages[member.id] = message.id
            self.save_event_time(member.id, message.id, "例行檢查-沒收")
            self.update_user_kkcoin(member.id, -lost_kkcoin)
        else:
            embed.add_field(name="✅ 通過檢查", value="這次僥倖逃過...", inline=False)
            message = await thread.send(embed=embed)
            self.event_messages[member.id] = message.id
            self.save_event_time(member.id, message.id, "例行檢查-通過")

    async def event_supervisor_favor(self, member, thread, kkcoin, level, hp, stamina):
        """主管恩惠"""
        gain = random.randint(50, 200)
        hp_gain = random.randint(10, 20)
        embed = discord.Embed(
            title="😊 主管心情好", 
            description="主管今天收了大筆賄賂，心情特別好，給了你一些好處。", 
            color=0x00aa00,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 獎勵", value=f"+{gain} KKCoin", inline=True)
        embed.add_field(name="❤️ 血量恢復", value=f"+{hp_gain} HP", inline=True)
        message = await thread.send(embed=embed)
        self.event_messages[member.id] = message.id
        self.save_event_time(member.id, message.id, "主管恩惠")
        self.update_user_stats(member.id, kkcoin=gain, hp=hp_gain)

    # ==================== 資料庫更新函數 ====================

    def update_user_kkcoin(self, user_id: int, amount: int):
        """更新使用者KKCoin - 使用 db_adapter"""
        try:
            current_kkcoin = get_user_field(user_id, 'kkcoin', default=0)
            new_kkcoin = max(0, current_kkcoin + amount)
            set_user_field(user_id, 'kkcoin', new_kkcoin)
        except Exception as e:
            print(f"❌ 更新KKCoin錯誤: {e}")

    def update_user_stats(self, user_id: int, kkcoin: int = 0, hp: int = 0, stamina: int = 0):
        """更新使用者多項數據 - 使用 db_adapter"""
        try:
            if kkcoin != 0:
                current_kkcoin = get_user_field(user_id, 'kkcoin', default=0)
                new_kkcoin = max(0, current_kkcoin + kkcoin)
                set_user_field(user_id, 'kkcoin', new_kkcoin)
            
            if hp != 0:
                current_hp = get_user_field(user_id, 'hp', default=100)
                new_hp = max(0, min(100, current_hp + hp))
                set_user_field(user_id, 'hp', new_hp)
            
            if stamina != 0:
                current_stamina = get_user_field(user_id, 'stamina', default=100)
                new_stamina = max(0, min(100, current_stamina + stamina))
                set_user_field(user_id, 'stamina', new_stamina)
        
        except Exception as e:
            print(f"❌ 更新數據錯誤: {e}")

    # ==================== 管理指令 ====================

    @commands.command(name='event_stats')
    @commands.has_permissions(administrator=True)
    async def event_stats(self, ctx):
        """查看事件統計（管理員專用）"""
        try:
            if not self.event_history:
                await ctx.send("📊 目前沒有事件統計數據")
                return
            
            # Calculate stats from memory
            total_users = len(self.event_history)
            event_counts = [data.get('event_count', 0) for data in self.event_history.values()]
            avg_events = sum(event_counts) / total_users if total_users > 0 else 0
            max_events = max(event_counts) if event_counts else 0
            
            # Count event types
            event_type_counts = {}
            for data in self.event_history.values():
                event_type = data.get('last_event_type')
                if event_type:
                    event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            
            top_events = sorted(event_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            embed = discord.Embed(
                title="📊 園區事件統計",
                color=0x00aaff,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="📈 總體數據",
                value=f"追蹤用戶數：{total_users}\n平均事件數：{avg_events:.1f}\n最多事件數：{max_events}",
                inline=False
            )
            
            if top_events:
                event_list = "\n".join([f"{i+1}. {event_type}: {count}次" 
                                       for i, (event_type, count) in enumerate(top_events)])
                embed.add_field(name="🔝 最常見事件", value=event_list, inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ 查詢統計失敗: {e}")

    @commands.command(name='reset_event')
    @commands.has_permissions(administrator=True)
    async def reset_event(self, ctx, user_id: int = None):
        """重置事件冷卻時間（管理員專用）"""
        try:
            if user_id:
                if user_id in self.event_cooldown:
                    del self.event_cooldown[user_id]
                
                if user_id in self.event_history:
                    del self.event_history[user_id]
                
                if user_id in self.event_messages:
                    del self.event_messages[user_id]
                
                await ctx.send(f"✅ 已重置用戶 {user_id} 的事件冷卻")
            else:
                self.event_cooldown.clear()
                self.event_history.clear()
                self.event_messages.clear()
                
                await ctx.send("✅ 已重置所有用戶的事件冷卻")
                
        except Exception as e:
            await ctx.send(f"❌ 重置失敗: {e}")

    @commands.command(name='force_event')
    @commands.has_permissions(administrator=True)
    async def force_event(self, ctx, member: discord.Member = None):
        """強制觸發事件（管理員專用）"""
        try:
            if not member:
                member = ctx.author
            
            # Use db_adapter to get user data
            user_data = get_user(member.id)
            if not user_data:
                await ctx.send("❌ 無法找到該用戶的數據")
                return
            
            thread_id = user_data.get('thread_id', 0)
            kkcoin = user_data.get('kkcoin', 0)
            level = user_data.get('level', 1)
            hp = user_data.get('hp', 100)
            stamina = user_data.get('stamina', 100)
            
            if not thread_id or thread_id == 0:
                await ctx.send("❌ 該用戶沒有登記的討論串")
                return
            
            thread = ctx.guild.get_thread(thread_id)
            
            if not thread:
                await ctx.send("❌ 找不到該討論串")
                return
            
            await self.trigger_random_event(member, thread, kkcoin, level, hp, stamina)
            await ctx.send(f"✅ 已為 {member.mention} 強制觸發隨機事件")
            
        except Exception as e:
            await ctx.send(f"❌ 強制觸發失敗: {e}")

async def setup(bot):
    await bot.add_cog(ScamParkEvents(bot))
