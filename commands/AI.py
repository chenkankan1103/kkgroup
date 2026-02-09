import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
from typing import Optional, List, Dict
from utils.persona import build_persona_prompt, analyze_tone
from utils.memory import add_to_history
from dotenv import load_dotenv
import logging

load_dotenv()

# Google Gemini API 設定（優先）
GOOGLE_API_KEY = os.getenv("AI_API_KEY")

# Groq API 設定（備用）
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_API_MODEL = os.getenv("GROQ_API_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 嘗試導入 Google Generative AI SDK
GOOGLE_GENAI_AVAILABLE = False
try:
    import google.generativeai as genai
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
        GOOGLE_GENAI_AVAILABLE = True
        logger.info("🚀 AI模塊初始化: 使用 Google Gemini API (google.generativeai SDK)")
except ImportError:
    logger.warning("⚠️ google.generativeai 未安裝，將使用 Groq API")
except Exception as e:
    logger.warning(f"⚠️ Google Gemini API 初始化失敗: {e}，將使用 Groq API 作為備用")

# 如果 Google API 不可用，使用 Groq
if not GOOGLE_GENAI_AVAILABLE:
    if GROQ_API_KEY:
        logger.info("🚀 AI模塊初始化: 使用 Groq API 作為備用方案")
    else:
        logger.error("❌ 既沒有 Google Gemini API 也沒有 Groq API Key")


class ContextManager:
    """管理對話上下文和歷史"""
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.conversation_history: Dict[int, List[Dict]] = {}
    
    def add_exchange(self, user_id: int, user_msg: str, bot_msg: str):
        """添加一次對話交換（使用者訊息 + 機器人回應）"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        self.conversation_history[user_id].append({
            'user': user_msg,
            'bot': bot_msg
        })
        
        if len(self.conversation_history[user_id]) > self.max_history:
            self.conversation_history[user_id].pop(0)
    
    def build_context_prompt(self, user_id: int, new_message: str) -> str:
        """構建包含上下文的簡化提示（控制長度以避免 API 限制）"""
        history = self.conversation_history.get(user_id, [])
        
        # 從最近3條開始，如果太長就逐步減少
        for num_exchanges in [3, 2, 1, 0]:
            context = ""
            if num_exchanges > 0:
                context = "最近的對話記錄：\n"
                for i, exchange in enumerate(history[-num_exchanges:], 1):
                    # 截斷過長的訊息
                    user_msg = exchange['user'][:200]
                    bot_msg = exchange['bot'][:200]
                    context += f"\n--- 對話 {i} ---\n"
                    context += f"使用者: {user_msg}\n"
                    context += f"機器人: {bot_msg}\n"
                context += f"\n--- 新訊息 ---\n"
            
            context += f"使用者: {new_message}\n"
            
            # 如果總長度在合理範圍內（Groq 限制），就使用這個版本
            if len(context) < 2000:
                return context
        
        # 如果實在太長，只返回當前訊息
        logger.warning(f"對話上下文過長，只使用當前訊息")
        return f"使用者: {new_message}\n"
    
    def get_last_bot_response(self, user_id: int) -> Optional[str]:
        """獲取機器人最後的回應"""
        history = self.conversation_history.get(user_id, [])
        if history:
            return history[-1]['bot']
        return None


class ComplexityDetector:
    """檢測問題複雜度，以決定使用哪個模型"""
    
    # 簡單問題關鍵詞
    SIMPLE_KEYWORDS = [
        "1+1", "幾歲", "你是誰", "叫什麼", "幾點", "今天天氣",
        "是什麼", "的英文", "縮寫", "歌詞", "名字", "怎麼唸",
        "好不好", "行不行", "要不要", "可不可以"
    ]
    
    # 複雜問題關鍵詞
    COMPLEX_KEYWORDS = [
        "為什麼", "怎麼樣", "應該", "可能", "分析", "比較", "建議",
        "計劃", "策略", "問題", "困擾", "煩惱", "如何", "怎麼辦",
        "設計", "改進", "優化", "邏輯", "推理", "思考", "深入"
    ]
    
    @staticmethod
    def is_complex(message: str) -> bool:
        """判斷問題是否複雜（需要使用gemini-2.5-pro）"""
        message_lower = message.lower()
        
        # 短訊息通常是簡單問題
        if len(message) < 20:
            return False
        
        # 多句子或包含複雜詞彙
        if "。" in message or "，" in message:
            complex_count = sum(1 for kw in ComplexityDetector.COMPLEX_KEYWORDS if kw in message_lower)
            simple_count = sum(1 for kw in ComplexityDetector.SIMPLE_KEYWORDS if kw in message_lower)
            
            # 複雜詞彙多於簡單詞彙，或者有問號和多個標點
            if complex_count > simple_count or message.count("?") > 1 or len(message) > 50:
                return True
        
        return False


class IntentAnalyzer:
    """分析使用者意圖"""
    
    CONTEXT_KEYWORDS = ["然後", "所以", "呢", "咧", "?", "那", "這"]
    
    @staticmethod
    def should_use_context(message: str) -> bool:
        """判斷是否應該使用上下文"""
        if len(message) <= 6:
            return True
        return any(kw in message.lower() for kw in IntentAnalyzer.CONTEXT_KEYWORDS)


class AIResponse(commands.Cog):
    """處理所有 AI 回應的 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.context_manager = ContextManager(max_history=10)
    
    async def create_control_room_prompt(self, tone: str = "neutral") -> str:
        """建立人設系統提示詞 - 簡潔版"""
        
        base_prompt = """你是KK園區中控室的幹部。簡短直接，不要廢話。
根據對方的問題類型調整語氣。無論如何都要簡潔有力。

你的特點：疲憊但負責、冷但有溫、相信數據、監控一切。
用詞要口語化，說人話，別套公務員腔。"""
        
        if tone == "tired":
            return base_prompt + "\n【疲憊模式】眼神死掉地回答簡單問題。會吐槽，但還是解決。「嘖，又來... [答案]」"
        elif tone == "professional":
            return base_prompt + "\n【專業模式】技術問題時冷靜精準。直奔主題，用數據說話。「監測到...系統顯示...」"
        elif tone == "sarcastic":
            return base_prompt + "\n【毒舌模式】風趣回嘴，互動感強。黑色幽默可以用，但不傷人。「哈，算了... 我跟你說...」"
        elif tone == "warm":
            return base_prompt + "\n【溫暖模式】認真回應，有溫度但保持距離。肯定對方的努力。「別擔心，我在看著...」"
        elif tone == "analytical":
            return base_prompt + "\n【分析模式】數據問題用數字說話。精準透徹。「根據統計...數據顯示...」"
        else:
            return base_prompt + "\n【自動切換】根據問題類型自動選擇最合適的語氣。簡潔、有力、口語化。"
    
    async def call_ai_api(self, system_prompt: str, user_message: str, user_prompt: str) -> Optional[str]:
        """智能 API 調用函數 - 根據複雜度選擇模型，優先使用 Google Gemini API"""
        
        # 判斷複雜度並選擇模型
        is_complex = ComplexityDetector.is_complex(user_message)
        selected_model = 'gemini-2.5-pro' if is_complex else 'gemini-2.5-flash'
        model_type = "Pro (深度思考)" if is_complex else "Flash (快速回應)"
        
        # 1️⃣ 優先嘗試 Google Generative AI SDK
        if GOOGLE_GENAI_AVAILABLE:
            try:
                logger.info(f"🔄 嘗試使用 Google Gemini API - 模型: {selected_model} ({model_type})...")
                model = genai.GenerativeModel(selected_model)
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                
                # Pro 模型使用稍長的超時時間
                response = model.generate_content(full_prompt)
                
                if response.text:
                    logger.info(f"✅ Google Gemini {model_type} 成功: {len(response.text)} 字符")
                    return response.text
                else:
                    logger.warning("⚠️ Google Gemini API 未返回文本")
            except Exception as e:
                logger.warning(f"⚠️ Google Gemini API 失敗 ({model_type}): {e}，將降級到 Groq API")
        
        # 2️⃣ 降級到 Groq API
        if GROQ_API_KEY:
            try:
                logger.info("🔄 嘗試使用 Groq API (備用)...")
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": GROQ_API_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.7
                }
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    async with session.post(GROQ_API_URL, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "choices" in data and len(data["choices"]) > 0:
                                content = data["choices"][0]["message"]["content"].strip()
                                logger.info(f"✅ Groq API 成功: {len(content)} 字符")
                                return content
                            else:
                                logger.error(f"Groq API 響應格式錯誤: {str(data)[:200]}")
                        else:
                            response_text = await resp.text()
                            logger.error(f"Groq API 請求失敗: {resp.status}")
                            logger.error(f"響應: {response_text[:300]}")
            except asyncio.TimeoutError:
                logger.error("Groq API 請求超時")
            except Exception as e:
                logger.error(f"Groq API 錯誤: {e}", exc_info=True)
        
        # 3️⃣ 兩個 API 都失敗
        logger.error("❌ 無法連接到任何 AI API (Google Gemini 和 Groq 都失敗)")
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """處理提及機器人的訊息 - 監控室幹部回應系統"""
        try:
            if message.author.bot:
                return
            if not self.bot.user.mentioned_in(message):
                return

            tone = analyze_tone(message.content)
            # 獲取根據語氣調整的提示詞
            control_room_prompt = await self.create_control_room_prompt(tone)
            user_id = message.author.id
            user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()

            # 檢查訊息是否為空
            if not user_input:
                await message.reply("🎛️ 收到信號，但內容空白。給我點有用的資訊。")
                return

            # 記錄到簡單歷史
            add_to_history(user_id, user_input)

            # 構建帶有上下文的提示
            if IntentAnalyzer.should_use_context(user_input):
                full_prompt = self.context_manager.build_context_prompt(user_id, user_input)
            else:
                full_prompt = user_input

            async with message.channel.typing():
                # 傳遞user_input以供複雜度檢測
                reply = await self.call_ai_api(control_room_prompt, user_input, full_prompt)
                
                if not reply:
                    reply = "📡 監測中... 等等，信號不穩定。稍後再問。"

            # 保存此次對話交換
            self.context_manager.add_exchange(user_id, user_input, reply)
            
            await message.reply(reply)

        except Exception as e:
            logger.error(f"訊息處理錯誤: {e}")
            try:
                await message.reply("⚠️ 監控系統異常。我正在診斷問題，稍安勿躁。")
            except:
                pass


async def setup(bot):
    await bot.add_cog(AIResponse(bot))
