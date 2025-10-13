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
        """通用 API 調用函數 - 改進版，處理多個 JSON 對象"""
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
                        response_text = await resp.text()
                        logger.info(f"API 原始響應長度: {len(response_text)} chars")
                        logger.info(f"響應前 300 字符: {response_text[:300]}")
                        logger.info(f"響應後 300 字符: {response_text[-300:]}")
                        
                        import json
                        data = None
                        
                        # 方法 1: 直接提取第一個完整的 JSON 對象（處理多個 JSON 連接的情況）
                        cleaned_text = response_text.strip()
                        start_idx = cleaned_text.find('{')
                        
                        if start_idx != -1:
                            brace_count = 0
                            end_idx = -1
                            for i in range(start_idx, len(cleaned_text)):
                                if cleaned_text[i] == '{':
                                    brace_count += 1
                                elif cleaned_text[i] == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end_idx = i
                                        break
                            
                            if end_idx != -1:
                                json_str = cleaned_text[start_idx:end_idx+1]
                                try:
                                    data = json.loads(json_str)
                                    logger.info(f"成功提取 JSON 對象 (長度: {len(json_str)})")
                                except json.JSONDecodeError as e:
                                    logger.error(f"JSON 解析失敗: {e}")
                                    logger.error(f"嘗試解析的字符串: {json_str[:500]}")
                        
                        if data is None:
                            logger.error(f"無法解析任何 JSON 對象，完整響應: {response_text[:1000]}")
                            return None
                        
                        # 根據 API 類型調整解析方式
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0]["message"]["content"].strip()
                            logger.info(f"成功獲取回應 (choices): {len(content)} 字符")
                            return content
                        elif "result" in data:
                            content = data["result"].strip() if isinstance(data["result"], str) else str(data["result"])
                            logger.info(f"成功獲取回應 (result): {len(content)} 字符")
                            return content
                        elif "content" in data:
                            content = data["content"].strip() if isinstance(data["content"], str) else str(data["content"])
                            logger.info(f"成功獲取回應 (content): {len(content)} 字符")
                            return content
                        else:
                            logger.error(f"未知的 API 響應格式。數據鍵: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                            logger.error(f"完整數據: {str(data)[:500]}")
                            return None
                    else:
                        response_text = await resp.text()
                        logger.error(f"API 請求失敗: {resp.status}")
                        logger.error(f"響應: {response_text[:500]}")
        except asyncio.TimeoutError:
            logger.error("AI API 請求超時")
        except Exception as e:
            logger.error(f"AI API 錯誤: {e}", exc_info=True)
        
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
