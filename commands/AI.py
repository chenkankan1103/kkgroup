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

# 導入全局記憶系統
try:
    from ai_memory import (
        build_memory_context, 
        DialogueMemory, 
        PersonalityMemory,
        KnowledgeBase,
        initialize_memory_system
    )
except ImportError:
    # 如果記憶系統不可用，使用 stub
    def build_memory_context():
        return {"system_instructions": "", "dialogue_history": "", "knowledge_context": "", "estimated_tokens": 0}
    class DialogueMemory:
        @staticmethod
        def add_dialogue(q, a, importance=0.5): pass
    class PersonalityMemory: pass
    class KnowledgeBase: pass
    def initialize_memory_system(): pass

load_dotenv()

AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gpt-3.5-turbo")

# Groq 備用 API（優先級更高）
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = os.getenv("GROQ_API_URL")
GROQ_API_MODEL = os.getenv("GROQ_API_MODEL", "mixtral-8x7b-32768")

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
        # 初始化全局記憶系統
        try:
            initialize_memory_system()
        except Exception as e:
            logger.warning(f"記憶系統初始化失敗: {e}")
    
    async def call_ai_api(self, system_prompt: str, user_prompt: str, include_memory: bool = True) -> Optional[str]:
        """通用 API 調用函數 - 優先 Groq，備用 Gemini"""
        # 如果需要，添加全局記憶上下文
        if include_memory:
            try:
                memory_context = build_memory_context()
                # 組合系統提示詞：基礎設定 + 角色記憶 + 對話歷史
                enhanced_prompt = system_prompt + "\n\n" + memory_context["system_instructions"]
                
                # 添加對話歷史（如果有）
                if memory_context["dialogue_history"]:
                    enhanced_prompt += f"\n=== 對話歷史參考 ===\n{memory_context['dialogue_history']}\n"
                
                # 添加知識庫背景（如果有）
                if memory_context["knowledge_context"]:
                    enhanced_prompt += f"\n=== 相關知識背景 ===\n{memory_context['knowledge_context']}\n"
                
                system_prompt = enhanced_prompt
            except Exception as e:
                logger.warning(f"無法整合記憶上下文: {e}")
        
        # 優先嘗試 Groq，然後備用 Gemini
        api_attempts = []
        if GROQ_API_KEY and GROQ_API_URL:
            api_attempts.append(("Groq", GROQ_API_URL, GROQ_API_KEY, GROQ_API_MODEL, "openai"))
        if AI_API_KEY and AI_API_URL:
            api_attempts.append(("Gemini", AI_API_URL, AI_API_KEY, AI_API_MODEL, "gemini"))
        
        if not api_attempts:
            logger.error("沒有可用的 AI API 配置")
            return None
        
        for api_name, url, api_key, model, api_type in api_attempts:
            try:
                logger.info(f"⏳ 嘗試使用 {api_name} API...")
                
                if api_type == "gemini":
                    # Google Gemini API
                    full_url = f"{url}?key={api_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{
                            "parts": [
                                {
                                    "text": f"{system_prompt}\n\n{user_prompt}"
                                }
                            ]
                        }],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 500
                        }
                    }
                else:
                    # OpenAI 相容格式（Groq 等）
                    full_url = url
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    }
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    async with session.post(full_url, headers=headers, json=payload) as resp:
                        response_text = await resp.text()
                        
                        if resp.status == 200:
                            # 成功，解析回應
                            import json
                            data = None
                            
                            # 提取 JSON 對象
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
                                    except json.JSONDecodeError as e:
                                        logger.warning(f"{api_name} JSON 解析失敗: {e}")
                                        continue
                            
                            if data:
                                # 根據 API 類型解析
                                content = None
                                
                                # Gemini 格式
                                if "candidates" in data and len(data["candidates"]) > 0:
                                    candidate = data["candidates"][0]
                                    if "content" in candidate and "parts" in candidate["content"]:
                                        parts = candidate["content"]["parts"]
                                        if len(parts) > 0 and "text" in parts[0]:
                                            content = parts[0]["text"].strip()
                                
                                # OpenAI 格式（Groq）
                                elif "choices" in data and len(data["choices"]) > 0:
                                    content = data["choices"][0]["message"]["content"].strip()
                                
                                # 其他格式
                                elif "result" in data:
                                    content = data["result"].strip() if isinstance(data["result"], str) else str(data["result"])
                                elif "content" in data:
                                    content = data["content"].strip() if isinstance(data["content"], str) else str(data["content"])
                                
                                if content:
                                    logger.info(f"✅ {api_name} 成功: {len(content)} 字符")
                                    return content
                        
                        elif resp.status == 429:
                            # 配額超限，嘗試下一個 API
                            logger.warning(f"⚠️ {api_name} 配額已超限 (429)，嘗試備用 API...")
                            continue
                        
                        else:
                            logger.warning(f"⚠️ {api_name} 返回 {resp.status}，嘗試備用 API...")
                            continue
                            
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ {api_name} 請求超時，嘗試備用 API...")
                continue
            except Exception as e:
                logger.warning(f"⚠️ {api_name} 錯誤: {e}，嘗試備用 API...")
                continue
        
        # 所有 API 都失敗
        logger.error("❌ 所有 AI API 都不可用")
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
                try:
                    # 添加 45 秒超時保護，確保不會卡住
                    reply = await asyncio.wait_for(
                        self.call_ai_api(persona_prompt, full_prompt),
                        timeout=45
                    )
                except asyncio.TimeoutError:
                    logger.error("AI API 總體超時（45秒）")
                    reply = None
                
                if not reply:
                    reply = "中控室接收不到有意義的訊號，請再問一次。"

            # 保存此次對話交換
            self.context_manager.add_exchange(user_id, user_input, reply)
            
            # 將對話存儲到全局記憶庫（判斷重要性）
            try:
                importance = 0.5  # 預設中等重要性
                if len(user_input) > 50:  # 較長的提問通常更重要
                    importance = 0.8
                elif any(keyword in user_input for keyword in ["幫我", "怎麼", "如何", "什麼"]):
                    importance = 0.7
                
                DialogueMemory.add_dialogue(user_input, reply, importance=importance)
            except Exception as e:
                logger.warning(f"記憶存儲失敗: {e}")
            
            await message.reply(reply)

        except Exception as e:
            logger.error(f"訊息處理錯誤: {e}")
            try:
                await message.reply("中控室發生未知錯誤。")
            except:
                pass


async def setup(bot):
    await bot.add_cog(AIResponse(bot))
