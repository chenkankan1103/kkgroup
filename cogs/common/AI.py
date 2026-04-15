import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
from typing import Optional, List, Dict
# from utils.persona import build_persona_prompt, analyze_tone, get_emotion_emoji  # 不再使用動態人設
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

# ─── 工具箱導入（agent_tools.py 在專案根目錄）───────────────────────────────
try:
    import agent_tools
    _TOOLS_AVAILABLE = True
except ImportError:
    agent_tools = None  # type: ignore
    _TOOLS_AVAILABLE = False
    print("⚠️  agent_tools 模組不可用，AI 工具功能已停用")

# ─── 基於提示的函數呼叫系統（支援 Groq 和 GitHub Models）─────────────────────
try:
    from prompt_function_calling import (
        build_system_prompt_with_tools,
        extract_function_calls,
        extract_response_without_calls,
        execute_extracted_calls,
        format_call_results_for_context
    )
    _PROMPT_FC_AVAILABLE = True
except ImportError:
    _PROMPT_FC_AVAILABLE = False
    print("⚠️  prompt_function_calling 模組不可用，Groq/GitHub Models 工具呼叫功能已停用")

AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_KEY_BACKUP = os.getenv("AI_API_KEY_BACKUP")  # 備用 API 金鑰
AI_API_URL = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gemini-2.0-flash")  # Gemini 預設模型

# Groq 備用 API（優先級更高）
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = os.getenv("GROQ_API_URL")
GROQ_API_MODEL = os.getenv("GROQ_API_MODEL", "mixtral-8x7b-32768")

# GitHub Models 備用 API（優先級在 Groq 之前）
GITHUB_MODELS_API_KEY = os.getenv("GITHUB_MODELS_API_KEY")
GITHUB_MODELS_API_URL = os.getenv("GITHUB_MODELS_API_URL")
GITHUB_MODELS_API_MODEL = os.getenv("GITHUB_MODELS_API_MODEL", "gpt-5-turbo")

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
        self.context_manager = ContextManager(max_history=5)
        # 初始化全局記憶系統
        try:
            initialize_memory_system()
        except Exception as e:
            logger.warning(f"記憶系統初始化失敗: {e}")
    
    async def call_ai_api(self, system_prompt: str, user_prompt: str, include_memory: bool = False, caller_id: Optional[int] = None) -> Optional[str]:
        """通用 API 調用函數 - 優先 Gemini（含 Function Calling），備用 Groq
        
        ⚠️ 注意：include_memory 預設關閉以節省 token 額度（Gemini 免費額度有限）
        如果需要記憶功能，可設置 include_memory=True，但會大幅增加 token 消耗
        """
        # 記憶系統已禁用以節省 token 額度
        # 原因：工具列表(~1200 tokens) + 記憶上下文(~800 tokens) 會導致快速超額
        # 如確實需要記憶，可改回以下邏輯：
        if include_memory:
            logger.warning("⚠️ 記憶系統在 Gemini 免費版上會導致快速超額，已跳過記憶注入")
            # 實際的記憶注入已禁用，以下代碼保留作參考
            # try:
            #     memory_context = build_memory_context()
            #     estimated_tokens = memory_context.get("estimated_tokens", 0)
            #     if estimated_tokens > 2500:
            #         logger.warning(f"⚠️ 記憶 token 過多，跳過記憶上下文")
            #     else:
            #         enhanced_prompt = system_prompt + "\n\n" + memory_context["system_instructions"]
            #         if memory_context["dialogue_history"]:
            #             enhanced_prompt += f"\n=== 對話歷史參考 ===\n{memory_context['dialogue_history']}\n"
            #         if memory_context["knowledge_context"]:
            #             enhanced_prompt += f"\n=== 相關知識背景 ===\n{memory_context['knowledge_context']}\n"
            #         system_prompt = enhanced_prompt
            # except Exception as e:
            #     logger.warning(f"無法整合記憶上下文: {e}")
        
        # 優先嘗試：Gemini（主 → 備用） → GitHub Models → Groq
        api_attempts = []
        gemini_failed_reason = None
        
        logger.info("═" * 60)
        logger.info("📡 AI API 配置檢查")
        logger.info(f"  ✓ Gemini 主API: {'已配置' if (AI_API_KEY and AI_API_URL) else '未配置'}")
        logger.info(f"  ✓ Gemini 備用API: {'已配置' if (AI_API_KEY_BACKUP and AI_API_URL) else '未配置'}")
        logger.info(f"  ✓ GitHub Models: {'已配置' if (GITHUB_MODELS_API_KEY and GITHUB_MODELS_API_URL) else '未配置'}")
        logger.info(f"  ✓ Groq API: {'已配置' if (GROQ_API_KEY and GROQ_API_URL) else '未配置'}")
        logger.info("═" * 60)
        
        if AI_API_KEY and AI_API_URL:
            api_attempts.append(("Gemini (主)", AI_API_URL, AI_API_KEY, AI_API_MODEL, "gemini"))
        if AI_API_KEY_BACKUP and AI_API_URL:
            api_attempts.append(("Gemini (備用)", AI_API_URL, AI_API_KEY_BACKUP, AI_API_MODEL, "gemini"))
        if GITHUB_MODELS_API_KEY and GITHUB_MODELS_API_URL:
            api_attempts.append(("GitHub Models", GITHUB_MODELS_API_URL, GITHUB_MODELS_API_KEY, GITHUB_MODELS_API_MODEL, "openai"))
        if GROQ_API_KEY and GROQ_API_URL:
            api_attempts.append(("Groq", GROQ_API_URL, GROQ_API_KEY, GROQ_API_MODEL, "openai"))
        
        if not api_attempts:
            logger.error("❌ 沒有可用的 AI API 配置")
            logger.error(f"  - AI_API_KEY: {'有' if AI_API_KEY else '無'}")
            logger.error(f"  - AI_API_URL: {'有' if AI_API_URL else '無'}")
            logger.error(f"  - GITHUB_MODELS_API_KEY: {'有' if GITHUB_MODELS_API_KEY else '無'}")
            logger.error(f"  - GITHUB_MODELS_API_URL: {'有' if GITHUB_MODELS_API_URL else '無'}")
            logger.error(f"  - GROQ_API_KEY: {'有' if GROQ_API_KEY else '無'}")
            logger.error(f"  - GROQ_API_URL: {'有' if GROQ_API_URL else '無'}")
            return None
        
        logger.info(f"🔄 開始嘗試 API（共 {len(api_attempts)} 個）: {' → '.join([name for name, *_ in api_attempts])}")
        
        for api_name, url, api_key, model, api_type in api_attempts:
            try:
                logger.info(f"⏳ 嘗試使用 {api_name} (模型: {model})...")
                
                if api_type == "gemini":
                    # ── Google Gemini API（支援 Function Calling）──────────────────
                    import json as _json
                    full_url = f"{url}?key={api_key}"
                    headers = {"Content-Type": "application/json"}

                    # 建立初始對話內容
                    contents = [{
                        "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                    }]

                    payload = {
                        "contents": contents,
                        "generationConfig": {
                            "temperature": 0.85,
                            "maxOutputTokens": 300
                        }
                    }

                    # ⚠️ 代理人工具已禁用，優化 token 消耗和 AI 回應簡潔性
                    # 專注於通用 AI 回應，無需工具呼叫功能
                    # 節省 ~1200 tokens 可用額度
                    USE_TOOLS_FOR_GEMINI = False
                    
                    if USE_TOOLS_FOR_GEMINI and _TOOLS_AVAILABLE:
                        payload["tools"] = agent_tools.get_gemini_tools_spec()
                        logger.info("🔧 工具列表已加入 Gemini payload (消耗 ~1000+ tokens)")
                    else:
                        logger.info("ℹ️ 代理人工具已禁用，專注於通用 AI 回應")

                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                        # ── 第一次請求 ──────────────────────────────────────────────
                        async with session.post(full_url, headers=headers, json=payload) as resp:
                            response_text = await resp.text()

                            if resp.status == 429:
                                gemini_failed_reason = "配額超限 (429)"
                                logger.warning(f"⚠️ {api_name} 配額超限 (429)，嘗試下一個 API...")
                                continue

                            if resp.status != 200:
                                logger.warning(f"⚠️ {api_name} 返回 {resp.status}，回應: {response_text[:200]}")
                                continue

                            try:
                                data = _json.loads(response_text)
                            except _json.JSONDecodeError as e:
                                logger.warning(f"⚠️ {api_name} JSON 解析失敗: {e}\n原始回應: {response_text[:300]}")
                                continue

                            if not data or "candidates" not in data or not data["candidates"]:
                                logger.warning(f"⚠️ {api_name} 回應非空但缺 candidates: {list(data.keys()) if data else 'data=None'}")
                                continue

                            candidate = data["candidates"][0]
                            parts = candidate.get("content", {}).get("parts", [])

                            if not parts:
                                logger.warning(f"⚠️ {api_name} 回應無 parts 內容")
                                continue

                            # ── 處理 Function Call（工具呼叫）──────────────────────
                            if "functionCall" in parts[0] and _TOOLS_AVAILABLE:
                                fc = parts[0]["functionCall"]
                                tool_name = fc.get("name", "")
                                tool_args = fc.get("args", {})
                                logger.info(f"🔧 Gemini 呼叫工具: {tool_name}({tool_args})")

                                tool_result = agent_tools.dispatch_tool(
                                    tool_name, tool_args, caller_id=caller_id
                                )
                                logger.info(f"   工具結果: {str(tool_result)[:100]}")

                                # 多輪對話：附上工具結果，取得最終回應
                                contents.append({
                                    "role": "model",
                                    "parts": [{"functionCall": fc}]
                                })
                                contents.append({
                                    "role": "user",
                                    "parts": [{"functionResponse": {
                                        "name": tool_name,
                                        "response": {"result": str(tool_result)}
                                    }}]
                                })
                                payload["contents"] = contents

                                # ── 第二次請求（取得工具結果後的最終回覆）─────────
                                async with session.post(full_url, headers=headers, json=payload) as resp2:
                                    r2_text = await resp2.text()
                                    if resp2.status != 200:
                                        continue
                                    try:
                                        data = _json.loads(r2_text)
                                    except _json.JSONDecodeError:
                                        continue
                                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])

                            # ── 提取最終文字內容 ───────────────────────────────────
                            if not parts:
                                logger.warning(f"⚠️ {api_name} 提取後 parts 仍為空")
                                continue
                            
                            if "text" not in parts[0]:
                                logger.warning(f"⚠️ {api_name} 回應無 text 欄位: {parts[0].keys() if isinstance(parts[0], dict) else '非dict'}")
                                continue
                            
                            content = parts[0]["text"].strip()
                            if content:
                                logger.info(f"✅ 使用以下 API 成功回應:")
                                logger.info(f"   - API 名稱: {api_name}")
                                logger.info(f"   - 模型: {model}")
                                logger.info(f"   - 回應長度: {len(content)} 字符")
                                logger.info("═" * 60)
                                return content
                            else:
                                logger.warning(f"⚠️ {api_name} 文字內容為空")

                else:
                    # ── OpenAI 相容格式（GitHub Models, Groq 等）───────────────────────
                    import json as _json
                    full_url = url
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    # 準備系統提示 - 無工具功能，專注於通用 AI 回應
                    enhanced_system = system_prompt
                    
                    # 如果之前 Gemini 失敗，添加降級提示
                    if gemini_failed_reason and ("GitHub" in api_name or "Groq" in api_name):
                        enhanced_system += f"\n\n⚠️ [系統注]: Gemini API {gemini_failed_reason}，已切換至 {api_name}。"
                        logger.warning(f"⚠️ 已切換至 {api_name}（Gemini {gemini_failed_reason}）")
                    
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": enhanced_system},
                            {"role": "user", "content": user_prompt}
                        ]
                    }

                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                        # ── 第一次請求 ──────────────────────────────────────────────
                        async with session.post(full_url, headers=headers, json=payload) as resp:
                            response_text = await resp.text()

                            if resp.status == 429:
                                continue

                            if resp.status != 200:
                                logger.warning(f"⚠️ {api_name} 返回 {resp.status}，嘗試備用 API...")
                                continue

                            try:
                                data = _json.loads(response_text)
                            except _json.JSONDecodeError as e:
                                logger.warning(f"{api_name} JSON 解析失敗: {e}")
                                continue

                            if "choices" in data and data["choices"]:
                                first_response = data["choices"][0]["message"]["content"].strip()
                                
                                # 代理人工具已禁用，直接返回 AI 回應
                                if first_response:
                                    logger.info(f"✅ 使用以下 API 成功回應:")
                                    logger.info(f"   - API 名稱: {api_name}")
                                    logger.info(f"   - 模型: {model}")
                                    logger.info(f"   - 回應長度: {len(first_response)} 字符")
                                    logger.info("═" * 60)
                                    return first_response


            except asyncio.TimeoutError:
                logger.warning(f"⚠️ {api_name} 請求超時，嘗試備用 API...")
                continue
            except Exception as e:
                logger.warning(f"⚠️ {api_name} 錯誤: {e}，嘗試備用 API...")
                continue
        
        # 所有 API 都失敗
        logger.error("❌ 所有 AI API 都不可用 - 已嘗試的引擎:")
        for api_name, _, _, _, _ in api_attempts:
            logger.error(f"   ✗ {api_name} - 失敗")
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """處理提及機器人的訊息 - 使用上下文感知"""
        try:
            if message.author.bot:
                return
            if not self.bot.user.mentioned_in(message):
                return

            user_id = message.author.id
            user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()
            
            # 使用簡單預設的系統提示詞 - 中控室干部風格
            system_prompt = f"""你是 KK 園區中控室的監控干部，負責監管整個園區的運營。
你的語氣應該是專業、有點威嚴但不冷漠的。
直接回答問題，必要時給出指示或建議。避免過度解釋。
有需要時使用可用工具查詢園區資訊。

當前聯絡人：{message.author.name} (ID: {user_id})
當提及『我』、『我的』等時，應使用此 ID。"""

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
                        self.call_ai_api(system_prompt, full_prompt, caller_id=user_id),
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
