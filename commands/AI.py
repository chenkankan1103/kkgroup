import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
from typing import Optional, List, Dict
from utils.persona import build_persona_prompt, analyze_tone
from utils.memory import add_to_history, get_history
from dotenv import load_dotenv
import logging

load_dotenv()

AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gpt-3.5-turbo")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        """構建包含上下文的完整提示"""
        history = self.conversation_history.get(user_id, [])
        
        context = "最近的對話記錄：\n"
        for i, exchange in enumerate(history[-3:], 1):
            context += f"\n--- 對話 {i} ---\n"
            context += f"使用者: {exchange['user']}\n"
            context += f"機器人: {exchange['bot']}\n"
        
        context += f"\n--- 新訊息 ---\n使用者: {new_message}\n"
        return context
    
    def get_last_bot_response(self, user_id: int) -> Optional[str]:
        """獲取機器人最後的回應"""
        history = self.conversation_history.get(user_id, [])
        if history:
            return history[-1]['bot']
        return None


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
    
async def call_ai_api(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """通用 API 調用函數 - 改進版"""
        if not AI_API_KEY or not AI_API_URL:
            logger.error("AI API 配置不完整")
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": AI_API_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(AI_API_URL, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        # 先獲取原始文本，便於調試
                        response_text = await resp.text()
                        logger.info(f"API 原始響應 ({len(response_text)} chars): {response_text[:500]}")
                        
                        try:
                            data = await resp.json()
                        except Exception as json_error:
                            logger.error(f"JSON 解析失敗: {json_error}")
                            logger.error(f"響應文本: {response_text[:1000]}")
                            return None
                        
                        # 根據 API 類型調整解析方式
                        if "choices" in data and len(data["choices"]) > 0:
                            return data["choices"][0]["message"]["content"].strip()
                        elif "result" in data:  # 某些 API 的響應格式
                            return data["result"].strip()
                        elif "content" in data:
                            return data["content"].strip()
                        else:
                            logger.error(f"未知的 API 響應格式: {data}")
                            return None
                    else:
                        response_text = await resp.text()
                        logger.error(f"API 請求失敗: {resp.status}, 響應: {response_text[:500]}")
        except asyncio.TimeoutError:
            logger.error("AI API 請求超時")
        except Exception as e:
            logger.error(f"AI API 錯誤: {e}")
        
        return None
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """處理提及機器人的訊息 - 使用上下文感知"""
        try:
            if message.author.bot:
                return
            if not self.bot.user.mentioned_in(message):
                return

            tone = analyze_tone(message.content)
            persona_prompt = build_persona_prompt(bot_name="KK園區中控室", tone=tone)
            user_id = message.author.id
            user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()

            # 記錄到簡單歷史
            add_to_history(user_id, user_input)

            # 構建帶有上下文的提示
            if IntentAnalyzer.should_use_context(user_input):
                full_prompt = self.context_manager.build_context_prompt(user_id, user_input)
            else:
                full_prompt = user_input

            async with message.channel.typing():
                reply = await self.call_ai_api(persona_prompt, full_prompt)
                
                if not reply:
                    reply = "中控室接收不到有意義的訊號，請再問一次。"

            # 保存此次對話交換
            self.context_manager.add_exchange(user_id, user_input, reply)
            
            await message.reply(reply)

        except Exception as e:
            logger.error(f"訊息處理錯誤: {e}")
            try:
                await message.reply("中控室發生未知錯誤。")
            except:
                pass


async def setup(bot):
    await bot.add_cog(AIResponse(bot))
