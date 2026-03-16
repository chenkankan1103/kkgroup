import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from typing import Optional
import datetime
import os
import aiohttp
import urllib.parse
import math
# add_user_field is needed by update_user_kkcoin
from db_adapter import get_user, set_user_field, get_user_field, get_all_users, add_user_field

class ScamParkEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        self.FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
        
        # AI 設定
        self.AI_API_KEY = os.getenv('AI_API_KEY')
        self.AI_API_URL = os.getenv('AI_API_URL')
        self.AI_API_MODEL = os.getenv('AI_API_MODEL')
        
        # Groq 備用 API（備選方案）
        self.GROQ_API_KEY = os.getenv('GROQ_API_KEY')
        self.GROQ_API_URL = os.getenv('GROQ_API_URL')
        self.GROQ_API_MODEL = os.getenv('GROQ_API_MODEL', 'mixtral-8x7b-32768')
        
        # 判斷優先使用的 API（Google / Gemini > Groq）
        self.use_google_api = True
        if self.AI_API_KEY and 'generativelanguage.googleapis.com' in (self.AI_API_URL or ''):
            # 有 Google/Gemini API，使用它作為主要 API
            self.use_google_api = True
        else:
            # 沒有 Gemini，改用 Groq
            self.use_google_api = False
        
        # 事件設定 - 調整為1-2小時間隔增加觸發頻率
        self.event_cooldown = {}  # 使用者事件冷卻 {user_id: last_event_timestamp}
        self.min_event_interval = 3600    # 最少1小時 (秒) - 增加觸發頻率
        self.max_event_interval = 7200   # 最多2小時 (秒) - 增加觸發頻率
        
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
        """從數據庫載入上次事件時間"""
        try:
            all_users = get_all_users()
            current_time = datetime.datetime.now().timestamp()
            
            # 初始化所有用戶的冷卻時間
            for user_data in all_users:
                user_id = user_data.get('user_id')
                if user_id:
                    # 設置初始冷卻時間為當前時間減去 1 小時，讓重啟後立即有可能觸發事件
                    # 這樣新用戶或被重置的用戶能更快接到第一個事件
                    self.event_cooldown[user_id] = current_time - 3600

            # 確保前四次事件觸發不受冷卻時間限制
            for user_id in list(self.event_cooldown.keys())[:4]:
                self.event_cooldown[user_id] = 0

            print(f"✅ 初始化 {len(self.event_cooldown)} 個用戶的事件冷卻時間（允許立即觸發）")
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
                # Defensive: coerce kkcoin to int and treat None as 0 to avoid TypeError
                try:
                    kkcoin = int(user_data.get('kkcoin') or 0)
                except (TypeError, ValueError):
                    kkcoin = 0
                
                # 提取其他需要的用戶數據
                try:
                    level = int(user_data.get('level') or 0)
                except (TypeError, ValueError):
                    level = 1
                
                try:
                    hp = int(user_data.get('hp') or 100)
                except (TypeError, ValueError):
                    hp = 100
                
                try:
                    stamina = int(user_data.get('stamina') or 100)
                except (TypeError, ValueError):
                    stamina = 100

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
                
                # 基礎觸發機率（提高到25%以增加事件頻率）
                base_chance = 0.25 * bell_curve_factor
                
                # KKCoin加成（活躍用戶更容易遇到事件）
                # 高KKCoin用戶（活躍種植者）加成較多，低KKCoin用戶大幅減成
                if kkcoin >= 1000:
                    wealth_bonus = min(0.03, kkcoin / 15000 * 0.02)  # 高KKCoin: 最多3%加成
                elif kkcoin >= 100:
                    wealth_bonus = 0.0  # 中等KKCoin: 無加成
                else:
                    wealth_bonus = -0.10  # 低KKCoin: -10%減成（大幅降低觸發機率）
                
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
        """將中文提示詞翻譯成英文（優先 Google / Gemini，備用 Groq）"""
        try:
            # 優先嘗試 Google
            if self.AI_API_KEY and self.AI_API_URL:
                result = await self._translate_google(chinese_text)
                if result and result != chinese_text:
                    return result
            
            # Google 失敗，降級到 Groq
            if self.GROQ_API_KEY and self.GROQ_API_URL:
                result = await self._translate_groq(chinese_text)
                if result and result != chinese_text:
                    return result
            
        except Exception:
            pass
        
        return chinese_text
    
    async def _translate_google(self, chinese_text: str) -> str:
        """使用 Google Generative AI 翻譯（若配額超限則無聲返回 None）"""
        try:
            url = f"{self.AI_API_URL}?key={self.AI_API_KEY}"
            
            data = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"You are a translator. Translate Chinese to English for image generation prompts. Keep it concise and descriptive.\n\nTranslate this to English for image generation: {chinese_text}"
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 100
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('candidates'):
                            content = result['candidates'][0].get('content', {})
                            if content.get('parts'):
                                return content['parts'][0].get('text', '').strip()
                    elif response.status == 429:
                        # 配額超限，無聲返回 None（上層會降級到 Groq）
                        return None
        except Exception:
            # 任何錯誤都無聲返回 None
            pass
        
        return None
    
    async def _translate_groq(self, chinese_text: str) -> str:
        """使用 Groq API 翻譯（備用方案）"""
        try:
            if not all([self.GROQ_API_KEY, self.GROQ_API_URL, self.GROQ_API_MODEL]):
                return None
            
            headers = {
                'Authorization': f'Bearer {self.GROQ_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.GROQ_API_MODEL,
                'messages': [
                    {'role': 'system', 'content': 'You are a translator. Translate Chinese to English for image generation prompts. Keep it concise and descriptive.'},
                    {'role': 'user', 'content': f'Translate this to English for image generation: {chinese_text}'}
                ],
                'max_tokens': 100,
                'temperature': 0.3
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.GROQ_API_URL, headers=headers, json=data, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
        except Exception:
            # 任何錯誤都無聲返回 None
            pass
        
        return None

    async def generate_ai_event_description(self, event_type: str, details: dict) -> str:
        """使用AI生成事件描述（支援 Google API 和 Groq API）"""
        try:
            if self.use_google_api:
                return await self._generate_google_description(event_type, details)
            else:
                return await self._generate_groq_description(event_type, details)
        except Exception as e:
            print(f"❌ AI生成錯誤: {e}")
            return None
    
    async def _generate_google_description(self, event_type: str, details: dict) -> str:
        """使用 Google Generative AI 生成描述"""
        try:
            prompt = f"""你是一個詐騙園區的旁白，請用生動的方式描述以下事件：

事件類型：{event_type}
事件詳情：{details}

請用繁體中文回應，語氣要帶有黑色幽默和諷刺，描述要生動且有畫面感，控制在80字以內。
要讓人感受到詐騙園區的壓迫感和絕望氛圍。"""
            
            url = f"{self.AI_API_URL}?key={self.AI_API_KEY}"
            
            data = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 150
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('candidates'):
                            content = result['candidates'][0].get('content', {})
                            if content.get('parts'):
                                return content['parts'][0].get('text', '').strip()
        except Exception as e:
            print(f"❌ Google AI 生成失敗: {e}")
        
        return None
    
    async def _generate_groq_description(self, event_type: str, details: dict) -> str:
        """使用 Groq / OpenAI 相容 API 生成描述"""
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
            print(f"❌ Groq AI 生成失敗: {e}")
        
        return None

    async def send_or_edit_event_message(self, thread: discord.Thread, embed: discord.Embed, 
                                          user_id: int, event_type: str) -> discord.Message:
        """
        發送或編輯事件訊息，並更新事件歷史
        
        Args:
            thread: Discord 線程
            embed: 事件 embed
            user_id: 用戶 ID
            event_type: 事件類型名稱
            
        Returns:
            發送/編輯的訊息
        """
        try:
            # 獲取用戶的事件歷史
            import json
            user_data = get_user(user_id)
            event_history_str = user_data.get('event_history', '[]')
            
            try:
                event_history = json.loads(event_history_str) if isinstance(event_history_str, str) else []
            except:
                event_history = []
            
            # 添加新事件到歷史（保留前 5 條）
            current_time = datetime.datetime.now().isoformat()
            new_event = {
                'type': event_type,
                'time': current_time
            }
            event_history.insert(0, new_event)  # 新事件放在最前
            event_history = event_history[:5]  # 只保留前 5 條
            
            # 保存事件歷史到數據庫
            set_user_field(user_id, 'event_history', json.dumps(event_history, ensure_ascii=False))
            
            # 生成帶有事件歷史的完整 embed
            history_text = "📋 【前 5 次事件紀錄】\n"
            for idx, evt in enumerate(event_history[:5], 1):
                evt_time = evt.get('time', '')
                evt_type = evt.get('type', '未知')
                # 格式化時間
                try:
                    dt = datetime.datetime.fromisoformat(evt_time)
                    time_str = dt.strftime('%m/%d %H:%M')
                except:
                    time_str = evt_time[:10]
                
                history_text += f"{idx}. {evt_type} ({time_str})\n"
            
            # 添加歷史欄位到 embed
            embed.add_field(
                name="📊 你的事件歷史",
                value=history_text,
                inline=False
            )
            
            # 檢查是否有之前的事件消息
            last_message_id = get_user_field(user_id, 'last_event_message_id', default=None)
            message = None
            
            if last_message_id:
                try:
                    message = await thread.fetch_message(int(last_message_id))
                    # 編輯現有消息
                    await message.edit(embed=embed)
                    print(f"✏️ 編輯事件訊息: {event_type} for user {user_id}")
                    return message
                except discord.NotFound:
                    # 消息已被刪除，發送新消息
                    print(f"⚠️ 舊消息已被刪除，發送新訊息")
                except Exception as e:
                    print(f"⚠️ 編輯消息失敗: {e}，嘗試發送新訊息")
            
            # 發送新訊息
            message = await thread.send(embed=embed)
            # 保存消息 ID
            set_user_field(user_id, 'last_event_message_id', message.id)
            print(f"📤 發送新事件訊息: {event_type} for user {user_id}")
            return message
            
        except Exception as e:
            print(f"❌ 發送/編輯事件訊息失敗: {e}")
            import traceback
            traceback.print_exc()
            # 降級到簡單發送
            return await thread.send(embed=embed)

    async def trigger_random_event(self, member: discord.Member, thread: discord.Thread, 
                                   kkcoin: int, level: int, hp: int, stamina: int):
        """觸發隨機事件"""
        try:
            # 檢查是否已有未處理的事件訊息
            if member.id in self.event_messages:
                old_message_id = self.event_messages[member.id]
                try:
                    old_message = await thread.fetch_message(old_message_id)
                    # 如果訊息存在且是最近的（4小時內），則跳過
                    if old_message.created_at.timestamp() > (datetime.datetime.now().timestamp() - 14400):
                        print(f"⏭️ 用戶 {member.name} 已有近期事件訊息，跳過觸發")
                        return
                except discord.NotFound:
                    # 訊息已被刪除，清除記錄
                    del self.event_messages[member.id]
                except discord.Forbidden:
                    print(f"⚠️ 無權限讀取用戶 {member.name} 的舊訊息")
                except Exception as e:
                    print(f"⚠️ 檢查舊訊息時發生錯誤: {e}")

            # Defensive: ensure kkcoin is numeric before using it for event selection
            try:
                kkcoin = int(kkcoin or 0)
            except (TypeError, ValueError):
                kkcoin = 0

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

        # Defensive: coerce kkcoin to int if None/invalid to avoid comparison errors
        try:
            kkcoin = int(kkcoin or 0)
        except (TypeError, ValueError):
            kkcoin = 0

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

        # 體力/HP事件 - 新增意外傷害和疾病
        if stamina < 50:
            events.extend([
                {'handler': self.event_forced_overtime, 'weight': 3},
                {'handler': self.event_quota_pressure, 'weight': 2},
                {'handler': self.event_workplace_illness, 'weight': 2},
            ])
        
        if hp < 60:
            events.extend([
                {'handler': self.event_beating, 'weight': 2},
                {'handler': self.event_medical_extortion, 'weight': 2},
                {'handler': self.event_car_accident, 'weight': 1},
                {'handler': self.event_workplace_accident, 'weight': 1},
            ])

        # 福利事件
        if random.random() < 0.15:
            events.extend([
                {'handler': self.event_police_bribe, 'weight': 1},
                {'handler': self.event_supervisor_favor, 'weight': 1},
            ])

        # 通用事件 - 新增食物中毒
        events.extend([
            {'handler': self.event_supervisor_inspection, 'weight': 2},
            {'handler': self.event_group_punishment, 'weight': 2},
            {'handler': self.event_work_accident, 'weight': 2},
            {'handler': self.event_cannabis_confiscation, 'weight': 3},  # 大麻檢查事件
            {'handler': self.event_training_hell, 'weight': 1},
            {'handler': self.event_isolation_punishment, 'weight': 1},
            {'handler': self.event_food_poisoning, 'weight': 1},
            {'handler': self.event_car_accident, 'weight': 1},  # 普遍的交通意外
        ])

        weighted_events = []
        for event in events:
            weighted_events.extend([event['handler']] * event['weight'])

        return [{'handler': h} for h in weighted_events]

    # ==================== 事件處理函數 ====================

    async def event_major_confiscation(self, member, thread, kkcoin, level, hp, stamina):
        """大額搜查行動"""
        ai_desc = await self.generate_ai_event_description(
            "大額搜查", 
            {"警告": "發現異常"}
        )
        
        image_prompt = await self.translate_to_english("詐騙園區主管搜查房間")
        image_url = await self.generate_pollinations_image(
            image_prompt or "scam park supervisor searching room",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="🚨 重大搜查行動",
            description=ai_desc or "園區主管帶隊突襲檢查...",
            color=0xcc0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="⚠️ 嚴重警告", value="被列為重點監控對象！", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)
        
        embed.set_footer(text="園區安全管理處")

        message = await self.send_or_edit_event_message(thread, embed, member.id, "重大搜查")

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
        embed.add_field(name="� 保護範圍", value="工作安全、人身安全、不會被欺負", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await self.send_or_edit_event_message(thread, embed, member.id, "保護費警告")

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
        
        beating_scenarios = [
            "主管今天心情特別差，你剛好說了一句話觸怒他...",
            "被主管當眾扇了一巴掌，臉火辣辣地疼...",
            "因為業績沒達標，被狠狠揍了一頓...",
        ]
        
        embed = discord.Embed(
            title="👊 暴力懲罰",
            description=ai_desc or random.choice(beating_scenarios),
            color=0xaa0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 身體傷害", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 精神創傷", value=f"-{stamina_loss} 體力", inline=True)
        embed.add_field(name="💔 後遺症", value="你的尊嚴被狠狠踐踏了...", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await self.send_or_edit_event_message(thread, embed, member.id, "毆打")
        
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

        message = await self.send_or_edit_event_message(thread, embed, member.id, "警方分贓")
        
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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "主管暗示")

    async def event_gambling_trap(self, member, thread, kkcoin, level, hp, stamina):
        """拒絕賭局"""
        embed = discord.Embed(
            title="🎲 地下賭局邀約", 
            description="「來玩一把吧！」你客氣地拒絕了...", 
            color=0x990099,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="✅ 聰明選擇", value="虧得你沒參加，聽說裡面全是老千。", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "賭局拒絕")

    async def event_fine_penalty(self, member, thread, kkcoin, level, hp, stamina):
        """違規警告"""
        reasons = ["業績不達標", "遲到5分鐘", "說話太大聲", "上廁所超時", "態度不佳"]
        reason = random.choice(reasons)
        embed = discord.Embed(
            title="📋 違規警告", 
            description=f"違規原因：{reason}", 
            color=0xff3300,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="⚠️ 警告", value="再犯一次將會被記過", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "違規警告")

    async def event_equipment_fee(self, member, thread, kkcoin, level, hp, stamina):
        """設備維護通知"""
        items = ["電腦", "手機", "椅子", "桌子", "網路"]
        item = random.choice(items)
        embed = discord.Embed(
            title="🔧 設備維護通知", 
            description=f"本月{item}需要進行定期維護。", 
            color=0x666666,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📢 提醒", value="維護期間可能會有短暫不便，敬請見諒", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "設備維護")

    async def event_kkcoin_confiscation(self, member, thread, kkcoin, level, hp, stamina):
        """房間檢查"""
        embed = discord.Embed(
            title="🚨 房間檢查", 
            description="管理員進行了房間檢查...", 
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="✅ 結果", value="檢查完畢，一切正常", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "房間檢查")

    async def event_forced_overtime(self, member, thread, kkcoin, level, hp, stamina):
        """強制加班"""
        stamina_loss = random.randint(20, 40)
        kkcoin_gain = random.randint(20, 50)
        
        ai_desc = await self.generate_ai_event_description("加班", {"損失體力": stamina_loss, "賺得": kkcoin_gain})
        
        image_prompt = await self.translate_to_english("員工被迫在辦公室一直工作到天亮，疲勞不堪")
        image_url = await self.generate_pollinations_image(
            image_prompt or "employee forced overtime working exhausted at desk until dawn",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="⏰ 強制加班", 
            description=ai_desc or "業績不達標，全員加班到天亮！",
            color=0x990000,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="⚡ 體力消耗", value=f"-{stamina_loss} 體力", inline=True)
        embed.add_field(name="💰 加班費", value=f"+{kkcoin_gain} KKCoin", inline=True)
        embed.add_field(name="😫 結果", value="整個人都掏空了，明天可能會很難受...", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)
        
        message = await self.send_or_edit_event_message(thread, embed, member.id, "強制加班")
        self.update_user_stats(member.id, kkcoin=kkcoin_gain, stamina=-stamina_loss)

    async def event_medical_extortion(self, member, thread, kkcoin, level, hp, stamina):
        """免費醫療"""
        hp_restore = random.randint(15, 30)
        embed = discord.Embed(
            title="🏥 園區醫療室", 
            description="醫生表示今天有免費診療活動！", 
            color=0x666666,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 治療", value=f"+{hp_restore} HP", inline=True)
        embed.add_field(name="✅ 費用", value="免費！ 🎉", inline=True)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "免費醫療")
        self.update_user_stats(member.id, hp=hp_restore)

    async def event_cell_search(self, member, thread, kkcoin, level, hp, stamina):
        """牢房檢查"""
        embed = discord.Embed(
            title="🔍 牢房檢查", 
            description="安全人員突襲檢查所有牢房...", 
            color=0xff6600,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="✅ 檢查結果", value="你的牢房通過檢查", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "牢房檢查")

    async def event_blackmail(self, member, thread, kkcoin, level, hp, stamina):
        """間諜報告"""
        embed = discord.Embed(
            title="😈 間諜報告", 
            description="有人在背後說你壞話...", 
            color=0x990066,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="😤 心情", value="有點被冒犯，但也無所謂", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "謠言")

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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "主管巡視")
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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "業績壓力")
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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "連坐處罰")
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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "工作意外")
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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "地獄訓練")
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
        embed.add_field(name="❤️ 虚弱", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 精神崩潰", value=f"-{stamina_loss} 體力", inline=True)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "關禁閉")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_random_inspection(self, member, thread, kkcoin, level, hp, stamina):
        """例行檢查"""
        embed = discord.Embed(
            title="👮 例行檢查", 
            description="主管進行例行檢查...", 
            color=0xffa500,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="✅ 檢查完畢", value="一切正常，請繼續工作", inline=False)
        message = await self.send_or_edit_event_message(thread, embed, member.id, "例行檢查")

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
        message = await self.send_or_edit_event_message(thread, embed, member.id, "主管恩惠")
        self.update_user_stats(member.id, kkcoin=gain, hp=hp_gain)

    # ==================== 新增事件：意外傷害 ====================

    async def event_car_accident(self, member, thread, kkcoin, level, hp, stamina):
        """車禍意外"""
        hp_loss = random.randint(20, 40)
        stamina_loss = random.randint(15, 35)
        
        accident_scenarios = [
            ("你騎機車經過十字路口，被一輛轉彎的計程車撞上...", "🏍️ 機車車禍"),
            ("下班途中，公車突然來個急煞車，你被甩到擋風玻璃...", "🚌 公車車禍"),
            ("騎自行車逆向超車時，迎面撞上一台小貨車...", "🚲 自行車碰撞"),
            ("在停車場出口沒注意，被倒車的休旅車刮到...", "🚗 停車場意外"),
        ]
        scenario, title_prefix = random.choice(accident_scenarios)
        
        ai_desc = await self.generate_ai_event_description("車禍", {"傷害": hp_loss, "體力消耗": stamina_loss})
        
        image_prompt = await self.translate_to_english("交通車禍意外，救護車到達現場")
        image_url = await self.generate_pollinations_image(
            image_prompt or "car accident, ambulance arriving at scene",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title=f"🚨 {title_prefix}",
            description=ai_desc or scenario,
            color=0xff3333,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 身體傷害", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 體力消耗", value=f"-{stamina_loss} 體力", inline=True)
        embed.add_field(name="🏥 狀態", value="痛到不敢走路，得休息好幾天...", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await self.send_or_edit_event_message(thread, embed, member.id, "車禍意外")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_food_poisoning(self, member, thread, kkcoin, level, hp, stamina):
        """食物中毒"""
        hp_loss = random.randint(15, 25)
        stamina_loss = random.randint(30, 50)
        
        food_scenarios = [
            ("公司食堂的便當有點怪味，中午開始肚子就難受...", "盒餐"),
            ("外面便利商店買的飯糰過期了，才吃兩口肚臍就翻江倒海...", "便利商店飯糰"),
            ("同事帶的家常菜没放冰箱，吃了一半開始拉肚子...", "家常菜"),
            ("公司旁邊小餐廳的湯看起來就不新鮮，現在全身無力...", "餐廳湯品"),
        ]
        scenario, food_type = random.choice(food_scenarios)
        
        ai_desc = await self.generate_ai_event_description("食物中毒", {"症狀": "嚴重腹瀉", "體力": stamina_loss})
        
        image_prompt = await self.translate_to_english("食物中毒，在洗手間難受")
        image_url = await self.generate_pollinations_image(
            image_prompt or "food poisoning, person in bathroom distressed",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="🤢 食物中毒",
            description=ai_desc or scenario,
            color=0x8b4513,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 身體虛弱", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 精力耗盡", value=f"-{stamina_loss} 體力", inline=True)
        embed.add_field(name="💊 治療", value="得吃止瀉藥和電解質飲料才能恢復...", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await self.send_or_edit_event_message(thread, embed, member.id, "食物中毒")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_workplace_illness(self, member, thread, kkcoin, level, hp, stamina):
        """工作過勞致病"""
        hp_loss = random.randint(10, 20)
        stamina_loss = random.randint(40, 70)
        
        illness_scenarios = [
            ("加班過度導致免疫力下降，感冒了...", "感冒", "🤒"),
            ("長期睡眠不足，發燒到38度，整個人都燒壞了...", "發燒", "🌡️"),
            ("過度壓力和疲勞，得了頸椎症候群，脖子痛得不行...", "頸椎病", "😣"),
            ("連續出差，坐飛機被傳染了流感...", "流感", "🦠"),
        ]
        scenario, illness_type, emoji = random.choice(illness_scenarios)
        
        ai_desc = await self.generate_ai_event_description("工作病", {"病症": illness_type, "體力下降": stamina_loss})
        
        image_prompt = await self.translate_to_english("工作過度導致生病，在床上休息")
        image_url = await self.generate_pollinations_image(
            image_prompt or "overworked person sick in bed, exhausted",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title=f"{emoji} 過勞成疾",
            description=ai_desc or scenario,
            color=0xcc33cc,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 身體衰弱", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 精神崩潰", value=f"-{stamina_loss} 體力", inline=True)
        embed.add_field(name="🏥 醫囑", value="醫生說得好好休息，不然會更嚴重...", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await self.send_or_edit_event_message(thread, embed, member.id, "過勞成疾")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

    async def event_workplace_accident(self, member, thread, kkcoin, level, hp, stamina):
        """工作場所傷害"""
        hp_loss = random.randint(25, 35)
        stamina_loss = random.randint(20, 40)
        
        accident_scenarios = [
            ("搬重物時閃到腰，現在站都站不直...", "閃腰"),
            ("手指被機器夾到，腫得像烤香腸...", "夾傷"),
            ("從梯子上摔下來，整個左臂都青了...", "摔傷"),
            ("熱湯潑到身上，燙傷面積不小...", "燙傷"),
        ]
        scenario, accident_type = random.choice(accident_scenarios)
        
        ai_desc = await self.generate_ai_event_description("工作意外", {"傷害": hp_loss})
        
        image_prompt = await self.translate_to_english("工作場所傷害意外，員工受傷")
        image_url = await self.generate_pollinations_image(
            image_prompt or "workplace accident, injured worker",
            is_negative_event=True
        )
        
        embed = discord.Embed(
            title="⚠️ 工作意外",
            description=ai_desc or scenario,
            color=0xff6633,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="❤️ 重傷", value=f"-{hp_loss} HP", inline=True)
        embed.add_field(name="⚡ 虚弱", value=f"-{stamina_loss} 體力", inline=True)
        embed.add_field(name="📋 工傷", value="得去醫院掛號，可能會請病假...", inline=False)
        
        if image_url:
            embed.set_image(url=image_url)

        message = await self.send_or_edit_event_message(thread, embed, member.id, "工作意外")
        self.update_user_stats(member.id, hp=-hp_loss, stamina=-stamina_loss)

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

    @app_commands.command(name="event_stats", description="查看園區事件統計（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def event_stats_slash(self, interaction: discord.Interaction):
        """查看事件統計（管理員專用）"""
        try:
            if not self.event_history:
                await interaction.response.send_message("📊 目前沒有事件統計數據", ephemeral=True)
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
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢統計失敗: {e}", ephemeral=True)

    @app_commands.command(name="event_reset", description="重置事件冷卻時間（管理員專用）")
    @app_commands.describe(user_id="用戶ID（可選，不填則重置所有用戶）")
    @app_commands.default_permissions(administrator=True)
    async def event_reset_slash(self, interaction: discord.Interaction, user_id: int = None):
        """重置事件冷卻時間（管理員專用）"""
        try:
            if user_id:
                if user_id in self.event_cooldown:
                    del self.event_cooldown[user_id]
                
                if user_id in self.event_history:
                    del self.event_history[user_id]
                
                if user_id in self.event_messages:
                    del self.event_messages[user_id]
                
                await interaction.response.send_message(f"✅ 已重置用戶 {user_id} 的事件冷卻", ephemeral=True)
            else:
                self.event_cooldown.clear()
                self.event_history.clear()
                self.event_messages.clear()
                
                await interaction.response.send_message("✅ 已重置所有用戶的事件冷卻", ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(f"❌ 重置失敗: {e}", ephemeral=True)

    @app_commands.command(name="event_force", description="強制觸發事件（管理員專用）")
    @app_commands.describe(member="目標用戶（可選，不填則使用自己）")
    @app_commands.default_permissions(administrator=True)
    async def event_force_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        """強制觸發事件（管理員專用）"""
        try:
            if not member:
                member = interaction.user
            
            # Use db_adapter to get user data
            user_data = get_user(member.id)
            if not user_data:
                await interaction.response.send_message("❌ 無法找到該用戶的數據", ephemeral=True)
                return
            
            thread_id = user_data.get('thread_id', 0)
            kkcoin = user_data.get('kkcoin', 0)
            level = user_data.get('level', 1)
            hp = user_data.get('hp', 100)
            stamina = user_data.get('stamina', 100)
            
            if not thread_id or thread_id == 0:
                await interaction.response.send_message("❌ 該用戶沒有登記的討論串", ephemeral=True)
                return
            
            thread = interaction.guild.get_thread(thread_id)
            
            if not thread:
                await interaction.response.send_message("❌ 找不到該討論串", ephemeral=True)
                return
            
            await self.trigger_random_event(member, thread, kkcoin, level, hp, stamina)
            await interaction.response.send_message(f"✅ 已為 {member.mention} 強制觸發隨機事件", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ 強制觸發失敗: {e}", ephemeral=True)

    def update_user_kkcoin(self, user_id: int, amount: int):
        """更新用戶KK幣"""
        try:
            add_user_field(user_id, 'kkcoin', amount)
            print(f"💰 更新用戶 {user_id} KK幣: {amount:+d}")
        except Exception as e:
            print(f"❌ 更新KK幣失敗: {e}")

    async def event_cannabis_confiscation(self, member, thread, kkcoin, level, hp, stamina):
        """大麻沒收事件 - 檢查正在種植的植物"""
        try:
            # 12 小時冷卻檢查
            now_ts = datetime.datetime.now().timestamp()
            last_ts = get_user_field(member.id, 'last_cannabis_confiscation', default=0)
            if now_ts - last_ts < 12 * 3600:
                # 冷卻中，不執行任何動作
                return

            # 檢查用戶是否有正在種植的大麻植物
            from shop_commands.merchant.cannabis_farming import get_user_plants
            
            plants = await get_user_plants(member.id)
            active_plants = [plant for plant in plants if plant.get('status') != 'harvested']
            
            if not active_plants:
                # 如果沒有正在種植的植物，改為一般檢查通知
                ai_desc = await self.generate_ai_event_description(
                    "置物櫃檢查", 
                    {"發現": "無違禁品", "原因": "隨機檢查"}
                )
                
                embed = discord.Embed(
                    title="🔍 置物櫃例行檢查",
                    description=ai_desc or "園區主管進行的例行檢查已完成。",
                    color=0xffaa00,
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="✅ 檢查結果", value="無違禁品，檢查通過", inline=False)
                
                message = await self.send_or_edit_event_message(thread, embed, member.id, "置物櫃檢查")
                # 記錄執行時間
                set_user_field(member.id, 'last_cannabis_confiscation', now_ts)
                return
            
            # 有正在種植的植物，摧毀所有植物（沒有罰款）
            destroyed_plants = []
            total_destroyed = 0
            
            # 摧毀所有正在種植的植物
            from shop_commands.merchant.cannabis_unified import get_adapter
            adapter = get_adapter()
            
            for plant in active_plants:
                try:
                    plant_id = plant.get('id')
                    if plant_id:
                        # 將植物狀態設為摧毀或刪除
                        await adapter.remove_plant(member.id, plant_id)
                        seed_type = plant.get('seed_type', '未知')
                        progress = plant.get('progress', 0)
                        destroyed_plants.append(f"{seed_type} (成長度: {progress:.1f}%)")
                        total_destroyed += 1
                except Exception as e:
                    print(f"❌ 摧毀植物失敗: {e}")
            
            ai_desc = await self.generate_ai_event_description(
                "大麻種植摧毀", 
                {
                    "摧毀植物": destroyed_plants,
                    "總數": total_destroyed
                }
            )
            
            image_prompt = await self.translate_to_english("詐騙園區主管摧毀大麻種植園")
            image_url = await self.generate_pollinations_image(
                image_prompt or "scam park supervisor destroying cannabis plants",
                is_negative_event=True
            )
            
            embed = discord.Embed(
                title="🚨 大麻種植摧毀行動",
                description=ai_desc or f"園區主管發現你在偷偷種植大麻！所有植物都被摧毀。",
                color=0xcc0000,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="🌱 摧毀植物",
                value="\n".join(destroyed_plants) if destroyed_plants else "無",
                inline=False
            )
            embed.add_field(
                name="⚠️ 嚴重警告",
                value="下次再犯將會被關禁閉！",
                inline=False
            )
            
            if image_url:
                embed.set_image(url=image_url)
            
            embed.set_footer(text="園區安全管理處")
            
            message = await self.send_or_edit_event_message(thread, embed, member.id, "大麻種植摧毀")
            
            # 記錄執行時間
            set_user_field(member.id, 'last_cannabis_confiscation', now_ts)
            
        except Exception as e:
            print(f"❌ 大麻種植摧毀事件錯誤: {e}")
            import traceback
            traceback.print_exc()


async def setup(bot):
    await bot.add_cog(ScamParkEvents(bot))
