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

# ✅ Gemini API 必須使用 generateContent 接口（而非 start_chat）
# 正確格式: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
# 我們手動控制對話歷史（Sliding Window），所以不需要 Chat API 的自動管理

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
    """管理對話上下文和歷史 - 直接生成 Gemini 原生 contents 格式
    
    🧠 記憶摘要機制: 防止滑動窗口遺忘重要資訊
    - 當歷史超過 10 條時，自動提取舊紀錄的關鍵字
    - 存儲在 summary_cache，並在 system_instruction 中附加
    - 確保長期對話的智商連續性
    """
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        # 改用 deque 格式存儲，直接符合 Gemini API 的 contents 結構
        # 每條對話為 {"role": "user"/"model", "parts": [{"text": "..."}]}
        self.conversation_history: Dict[int, List[Dict]] = {}
        # 🧠 記憶摘要快取 - 存儲舊對話的關鍵資訊
        self.summary_cache: Dict[int, str] = {}
    
    def add_exchange(self, user_id: int, user_msg: str, bot_msg: str):
        """添加一次對話交換，轉為 Gemini 原生格式
        
        🧠 記憶摘要: 當歷史即將超過限制時，先提取舊紀錄的關鍵字
        """
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        # 直接存儲 Gemini 格式的 content
        self.conversation_history[user_id].append({
            "role": "user",
            "parts": [{"text": user_msg}]
        })
        self.conversation_history[user_id].append({
            "role": "model",
            "parts": [{"text": bot_msg}]
        })
        
        # 🧠 記憶摘要: 超過 10 條訊息時，提取舊紀錄的關鍵字
        history = self.conversation_history[user_id]
        if len(history) > 10:
            # 提取即將被刪除的舊訊息的關鍵字
            old_messages = history[:-(self.max_history * 2)]
            if old_messages:
                # 簡單的關鍵字提取：找出對話中的重要詞彙
                summary = self._extract_summary(old_messages)
                if summary:
                    self.summary_cache[user_id] = summary
                    logger.debug(f"🧠 提取用戶 {user_id} 的舊對話摘要: {summary[:50]}...")
        
        # 維持最近 N 輪對話（每輪包括 user + model，所以總數 = max_history * 2）
        if len(history) > self.max_history * 2:
            self.conversation_history[user_id] = history[-(self.max_history * 2):]
    
    def _extract_summary(self, messages: List[Dict]) -> str:
        """從舊訊息中提取關鍵字摘要
        
        簡單策略：找出對話中的主要詞彙（名詞、關鍵字）
        """
        # 提取所有對話中的文字
        all_text = " ".join([
            msg.get("parts", [{}])[0].get("text", "")
            for msg in messages
            if msg.get("role") == "user"
        ])
        
        if not all_text:
            return ""
        
        # 簡單的關鍵字提取：分割並過濾短單詞
        words = [w for w in all_text.split() if len(w) > 2]
        # 取前 5 個不重複的詞作為摘要
        seen = set()
        keywords = []
        for w in words:
            if w not in seen and len(keywords) < 5:
                seen.add(w)
                keywords.append(w)
        
        return "、".join(keywords) if keywords else ""
    
    def get_summary(self, user_id: int) -> Optional[str]:
        """獲取用戶的對話摘要"""
        return self.summary_cache.get(user_id)
    
    def build_gemini_contents(self, user_id: int, new_message: str) -> List[Dict]:
        """構建符合 Gemini API 格式的 contents 列表，包含歷史對話和新訊息
        
        返回: [{"role": "user"/"model", "parts": [{"text": "..."}]}, ...]
        """
        history = self.conversation_history.get(user_id, [])
        
        # 開始構建 contents，包含最近的對話歷史
        contents = []
        
        # 添加歷史對話
        for item in history:
            contents.append(item)
        
        # 添加新訊息（使用者輸入）
        contents.append({
            "role": "user",
            "parts": [{"text": new_message}]
        })
        
        return contents
    
    def get_last_bot_response(self, user_id: int) -> Optional[str]:
        """獲取機器人最後的回應"""
        history = self.conversation_history.get(user_id, [])
        if history:
            # 找最後一個 role="model" 的回應
            for item in reversed(history):
                if item.get("role") == "model":
                    parts = item.get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
        return None


class AIResponse(commands.Cog):
    """處理所有 AI 回應的 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.context_manager = ContextManager(max_history=5)
        
        # 優化：在初始化時一次性構建 API 配置，避免每次調用都重複檢查
        self._api_attempts = self._build_api_config()
        
        # ❄️ API 冷却機制 - 避免頻繁撞已超限的 API
        # 格式: {api_name: cooldown_until_timestamp}
        self.api_cooldowns: Dict[str, float] = {}
        
        # 初始化全局記憶系統
        try:
            initialize_memory_system()
        except Exception as e:
            logger.warning(f"記憶系統初始化失敗: {e}")
    
    def _build_api_config(self) -> List[tuple]:
        """一次性構建可用的 API 配置清單，避免每次調用都重複檢查
        
        優先級: Gemini (主) → Gemini (備用) → Groq
        返回: [(api_name, url, api_key, model, api_type)]
        
        🔍 驗證: Gemini URL 必須指向 :generateContent 端點，而非 :streamGenerateContent 或 :batchGenerateContent
        """
        api_attempts = []
        
        # ✅ 驗證 Gemini API URL 格式
        def validate_gemini_url(url: str, api_name: str) -> bool:
            """驗證 Gemini URL 是否指向 generateContent 端點"""
            if not url:
                return False
            # 正確格式必須包含 :generateContent（而非 :streamGenerateContent）
            if ":generateContent" not in url:
                logger.warning(f"⚠️ {api_name} URL 格式可能錯誤，未包含 ':generateContent'")
                logger.warning(f"   ⚠️ 預期格式: https://generativelanguage.googleapis.com/v1beta/models/{{model}}:generateContent")
                logger.warning(f"   ❌ 當前 URL: {url[:80]}...")
                return False
            if ":streamGenerateContent" in url or ":batchGenerateContent" in url:
                logger.error(f"❌ {api_name} URL 指向錯誤的端點（stream 或 batch）")
                return False
            return True
        
        if AI_API_KEY and AI_API_URL:
            if validate_gemini_url(AI_API_URL, "Gemini (主)"):
                api_attempts.append(("Gemini (主)", AI_API_URL, AI_API_KEY, AI_API_MODEL, "gemini"))
                logger.info(f"✅ Gemini (主) API: 使用 generateContent 端點")
        
        if AI_API_KEY_BACKUP and AI_API_URL:
            if validate_gemini_url(AI_API_URL, "Gemini (備用)"):
                api_attempts.append(("Gemini (備用)", AI_API_URL, AI_API_KEY_BACKUP, AI_API_MODEL, "gemini"))
                logger.info(f"✅ Gemini (備用) API: 使用 generateContent 端點")
        
        if GROQ_API_KEY and GROQ_API_URL:
            api_attempts.append(("Groq", GROQ_API_URL, GROQ_API_KEY, GROQ_API_MODEL, "openai"))
        
        # 記錄初始化時的配置狀態
        if api_attempts:
            logger.info(f"✅ 初始化 {len(api_attempts)} 個 API 配置: {' → '.join([name for name, *_ in api_attempts])}")
        else:
            logger.error("❌ 沒有可用的 AI API 配置")
            logger.error("⚠️ 請檢查 .env 文件中的 API 配置")
        
        return api_attempts
    
    def _detect_task_type(self, user_prompt: str) -> str:
        """檢測訊息類型，決定回應長度
        
        返回: 'code' (代碼相關) 或 'chat' (普通對話)
        """
        keywords_code = ['代碼', '程式', '寫', '解釋', '實現', '如何', '方法', '函數', '函式', '算法']
        prompt_lower = user_prompt.lower()
        
        if any(kw in prompt_lower for kw in keywords_code):
            return 'code'
        return 'chat'
    
    def _build_gemini_payload(self, system_prompt: str, contents: List[Dict], user_prompt: str, use_tools: bool = False) -> Dict:
        """構建 Gemini API 的 payload - 單一責任原則
        
        🎯 Gemini 1.5 Flash generateContent API 規範:
        
        1. system_instruction - 分離的系統提示詞
           • Gemini API 對此進行內部快取優化
           • 比將其混入 contents 節省 5-10% token
           
        2. contents - 對話歷史列表（role/parts 格式）
           • 手動管理滑動窗口（最近 5 輪對話）
           • 每項格式: {"role": "user"/"model", "parts": [{"text": "..."}]}
           • 直接符合 API 規格，無需轉換邏輯
           
        3. generationConfig - 生成配置
           • temperature: 0.7（降低以獲得更穩定、更簡潔的回應）
           • maxOutputTokens: 動態調整（300 普通對話, 800 代碼相關）
           • topP: 0.8（平衡創意度）
           
        4. 注意：NOT start_chat API
           • 我們使用 generateContent（POST 請求）
           • 不使用 start_chat（自動管理多輪對話）
           • 原因：需要手動控制歷史長度以節省 token
        
        參數:
            system_prompt: 系統提示詞
            contents: 原生 Gemini contents 列表 [{"role": "user"/"model", "parts": [...]}]
            user_prompt: 使用者訊息（用於檢測任務類型）
            use_tools: 是否加入工具列表（默認關閉以節省 token）
        
        返回: 符合 Gemini generateContent API 規格的 payload
        """
        # 📊 動態調整 Token 限制
        task_type = self._detect_task_type(user_prompt)
        if task_type == 'code':
            max_tokens = 800  # 代碼相關：允許更長的回應
            instruction_hint = ""
        else:
            max_tokens = 300  # 普通對話：簡潔回應
            instruction_hint = "\n請在一句話內回覆，語言簡潔。"
        
        # 構建 system_instruction（可能包含簡潔要求）
        final_system_prompt = system_prompt + instruction_hint
        
        payload = {
            "system_instruction": {
                "parts": [{"text": final_system_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,  # ✅ 優化：降低至 0.7 以獲得更穩定的回應
                "maxOutputTokens": max_tokens,  # 📊 動態調整
                "topP": 0.8  # 平衡創意度
            }
        }
        
        if task_type == 'code':
            logger.debug(f"🔧 檢測到代碼相關任務，maxOutputTokens 調整為 {max_tokens}")
        else:
            logger.debug(f"💬 檢測到普通對話，maxOutputTokens 設為 {max_tokens}（簡潔回應）")
        
        # 可選：加入工具列表（如果啟用且可用）
        if use_tools and _TOOLS_AVAILABLE:
            payload["tools"] = agent_tools.get_gemini_tools_spec()
            logger.info("🔧 工具列表已加入 Gemini payload (消耗 ~1000+ tokens)")
        else:
            logger.debug("ℹ️ 代理人工具已禁用，專注於通用 AI 回應")
        
        return payload
    
    async def call_ai_api(self, system_prompt: str, user_prompt: str, user_id: Optional[int] = None, include_memory: bool = False) -> Optional[str]:
        """通用 API 調用函數 - 優先 Gemini，備用 Groq
        
        優化改進：
        1. 使用結構化 contents 列表而非文字拼接
        2. 利用 system_instruction 欄位進行內部快取優化
        3. 從對話歷史中構建原生 Gemini 格式的 contents
        4. 降低 temperature 至 0.7 以獲得更穩定的回應
        
        參數:
            system_prompt: 系統提示詞
            user_prompt: 使用者訊息
            user_id: 使用者 ID（用於構建對話歷史）
            include_memory: 是否加入記憶上下文（預設關閉）
        """
        if include_memory:
            logger.warning("⚠️ 記憶系統在 Gemini 免費版上會導致快速超額，已跳過記憶注入")
        
        # 使用已初始化的 API 配置，避免每次調用都重複檢查
        if not self._api_attempts:
            logger.error("❌ 沒有可用的 AI API 配置")
            return None
        
        # 優化：使用 ContextManager 的原生 Gemini 格式 contents
        if user_id is not None:
            contents = self.context_manager.build_gemini_contents(user_id, user_prompt)
        else:
            # 如果沒有 user_id，只使用當前訊息
            contents = [{"role": "user", "parts": [{"text": user_prompt}]}]
        
        # 🧠 注入對話摘要到 system_prompt，確保長期對話的連貫性
        effective_system_prompt = system_prompt
        if user_id is not None:
            summary = self.context_manager.get_summary(user_id)
            if summary:
                effective_system_prompt = f"{system_prompt}\n\n🧠 前文摘要 (記住這些重要信息): {summary}"
                logger.debug(f"🧠 已為用戶 {user_id} 注入對話摘要: {summary[:50]}...")
        
        logger.info(f"🔄 開始嘗試 API（共 {len(self._api_attempts)} 個）: {' → '.join([name for name, *_ in self._api_attempts])}")
        
        gemini_failed_reason = None
        import time  # 用於冷却機制
        
        for api_name, url, api_key, model, api_type in self._api_attempts:
            try:
                # ❄️ API 冷却機制 - 避免頻繁撞超限 API
                if api_name in self.api_cooldowns:
                    cooldown_until = self.api_cooldowns[api_name]
                    if time.time() < cooldown_until:
                        remaining = int(cooldown_until - time.time())
                        logger.warning(f"❄️ {api_name} 仍在冷却中 ({remaining}s 後恢復)，跳過...")
                        continue
                    else:
                        # 冷却時間已過，移除冷却記錄
                        del self.api_cooldowns[api_name]
                        logger.info(f"✅ {api_name} 冷却時間已過，重新嘗試...")
                
                logger.info(f"⏳ 嘗試使用 {api_name} (模型: {model})...")
                
                if api_type == "gemini":
                    # ── Google Gemini 1.5 Flash API - 使用 generateContent 接口 ──────────
                    # 📌 重要: 我們使用 generateContent POST 接口（而非 start_chat）
                    #    原因: 需要手動精準控制對話歷史長度（Sliding Window Memory）
                    #    好處: 節省 token、避免不必要的對話上下文
                    #
                    # 預期 URL 格式: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
                    # 完整請求 URL: {AI_API_URL}?key={api_key}
                    # 
                    # Payload 結構:
                    #   - system_instruction: 系統提示詞（Gemini API 內部快取優化）
                    #   - contents: 對話歷史（role/parts 格式，手動管理長度）
                    #   - generationConfig: 生成配置（temperature, maxOutputTokens 等）
                    import json as _json
                    full_url = f"{url}?key={api_key}"  # URL 應包含 :generateContent
                    headers = {"Content-Type": "application/json"}

                    # 優化：使用 _build_gemini_payload 方法構建 payload（包含 system_instruction）
                    payload = self._build_gemini_payload(effective_system_prompt, contents, user_prompt, use_tools=False)
                    
                    logger.debug(f"📨 Gemini generateContent 請求詳情:")
                    logger.debug(f"   - 端點: {url}")
                    logger.debug(f"   - 方式: POST generateContent（手動滑動窗口記憶）")
                    logger.debug(f"   - System Instruction 字數: {len(effective_system_prompt)}")
                    logger.debug(f"   - Contents 項數: {len(contents)}")
                    logger.debug(f"   - Temperature: {payload['generationConfig']['temperature']}")
                    logger.debug(f"   - maxOutputTokens: {payload['generationConfig']['maxOutputTokens']}")

                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                        # ── generateContent POST 請求 ──────────────────────────────────
                        async with session.post(full_url, headers=headers, json=payload) as resp:
                            response_text = await resp.text()

                            if resp.status == 429:
                                gemini_failed_reason = "配額超限 (429)"
                                # ❄️ 設置 60 秒冷却，避免頻繁撞 API 限制
                                self.api_cooldowns[api_name] = time.time() + 60
                                logger.warning(f"⚠️ {api_name} 配額超限 (429)，設置 60 秒冷却，嘗試下一個 API...")
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

                            # ── 提取最終文字內容 ───────────────────────────────────
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
                    # ── OpenAI 相容格式（Groq 等）───────────────────────
                    import json as _json
                    full_url = url
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    # 準備系統提示 - 無工具功能，專注於通用 AI 回應
                    enhanced_system = effective_system_prompt + "\n請在 150 字內簡潔回覆，禁止廢話。"
                    
                    # 如果之前 Gemini 失敗，添加降級提示
                    if gemini_failed_reason and "Groq" in api_name:
                        enhanced_system += f"\n⚠️ [系統注]: Gemini API {gemini_failed_reason}，已切換至 {api_name}。"
                        logger.warning(f"⚠️ 已切換至 {api_name}（Gemini {gemini_failed_reason}）")
                    
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": enhanced_system},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.7,  # 優化：降低至 0.7 以獲得更穩定的回應
                        "max_tokens": 300
                    }

                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                        # ── 第一次請求 ──────────────────────────────────────────────
                        async with session.post(full_url, headers=headers, json=payload) as resp:
                            response_text = await resp.text()

                            if resp.status == 429:
                                # ❄️ 設置 60 秒冷却，避免頻繁撞 API 限制
                                self.api_cooldowns[api_name] = time.time() + 60
                                logger.warning(f"⚠️ {api_name} 配額超限 (429)，設置 60 秒冷却...")
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
        for api_name, _, _, _, _ in self._api_attempts:
            logger.error(f"   ✗ {api_name} - 失敗")
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """處理提及機器人的訊息 - 使用優化的 Gemini 格式"""
        try:
            if message.author.bot:
                return
            if not self.bot.user.mentioned_in(message):
                return

            user_id = message.author.id
            user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()
            
            # 優化後的簡潔系統提示詞 + 簡潔要求
            system_prompt = f"""KK園區監控干部。簡潔回應，150字內。用戶：{message.author.name}"""

            # 記錄到簡單歷史
            add_to_history(user_id, user_input)

            async with message.channel.typing():
                try:
                    # 優化：直接傳遞 user_input（新訊息），call_ai_api 會自動透過 ContextManager 加入歷史
                    # 添加 45 秒超時保護，確保不會卡住
                    reply = await asyncio.wait_for(
                        self.call_ai_api(system_prompt, user_input, user_id=user_id),
                        timeout=45
                    )
                except asyncio.TimeoutError:
                    logger.error("AI API 總體超時（45秒）")
                    reply = None
                
                if not reply:
                    reply = "中控室接收不到有意義的訊號，請再問一次。"

            # 保存此次對話交換（轉換為 Gemini 格式）
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
