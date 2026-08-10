"""KK園區 AI Agent（官方 ADK 架構 — Anthropic/Google Agent Stack）
====================================================================
架構設計（官方 Agent Stack 規範）：

    LLMClient     → 低層 API 呼叫（NVIDIA 文字主路徑 + Gemini 工具/備援 + Groq 最終降級）
  AgentSession  → 每用戶的 Session 記憶（短期，最近 N 輪對話）
  KKBotAgent    → ADK 風格 Agent（系統提示、工具清單、Agentic Loop）
  AIResponse    → Discord Cog（事件監聽、訊息路由）

Agentic Loop（官方 Sequential Workflow）：
  用戶輸入 → Think（LLM 思考）→ Act（工具呼叫）→ Observe（結果注入）
  → 重複直到 LLM 給出最終文字回覆

API 優先級：
    1. NVIDIA API（一般文字回覆主路徑）
    2. Gemini 2.0 Flash（工具呼叫與文字備援）
    3. Groq llama-3.3-70b（最終降級，純文字，無工具）
"""

import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
import time
import json
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from shared.utils.llm_text_router import complete_text_with_fallback

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 工具箱 ────────────────────────────────────────────────────────────────
try:
    import agent_tools

    _TOOLS_AVAILABLE = True
except ImportError:
    agent_tools = None  # type: ignore
    _TOOLS_AVAILABLE = False
    logger.warning("⚠️ agent_tools 未載入，工具功能停用")

# ─── 長期記憶（修正 import 路徑）───────────────────────────────────────────
try:
    from shared.db.ai_memory import (
        build_memory_context,
        DialogueMemory,
        KnowledgeBase,
        initialize_memory_system,
    )
    from shared.db.chroma_knowledge_index import ChromaKnowledgeIndex

    _MEMORY_AVAILABLE = True
except ImportError:
    _MEMORY_AVAILABLE = False

    def build_memory_context():
        return {
            "system_instructions": "",
            "dialogue_history": "",
            "knowledge_context": "",
            "estimated_tokens": 0,
        }

    class DialogueMemory:  # type: ignore
        @staticmethod
        def add_dialogue(q, a, importance=0.5):
            pass

    class KnowledgeBase:  # type: ignore
        @staticmethod
        def search_knowledge(keyword, max_tokens=1000):
            return ""

        @staticmethod
        def get_recent_items(limit=20, category=None):
            return []

    class ChromaKnowledgeIndex:  # type: ignore
        def hybrid_search(self, query, limit=5, category=None):
            return []

    def initialize_memory_system():
        pass


# ─── 環境變數 ────────────────────────────────────────────────────────────────
GEMINI_KEY = os.getenv("AI_API_KEY")
GEMINI_KEY_BK = os.getenv("AI_API_KEY_BACKUP")
GEMINI_MODEL = os.getenv("AI_API_MODEL", "gemini-2.0-flash")
GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_MODEL = os.getenv("GROQ_API_MODEL", "llama-3.3-70b-versatile")
MAX_HISTORY = 10  # 每用戶保留的最大對話輪數
AI_INTERACTIVE_TIMEOUT_SEC = int(os.getenv("AI_INTERACTIVE_TIMEOUT", "45"))
AI_GEMINI_TIMEOUT_SEC = int(os.getenv("AI_GEMINI_TIMEOUT", "12"))
AI_GROQ_TIMEOUT_SEC = int(os.getenv("AI_GROQ_TIMEOUT", "10"))
AI_TEXT_NVIDIA_TIMEOUT_SEC = int(os.getenv("AI_TEXT_NVIDIA_TIMEOUT", "12"))
AI_TEXT_GEMINI_TIMEOUT_SEC = int(os.getenv("AI_TEXT_GEMINI_TIMEOUT", "8"))
AI_TEXT_GROQ_TIMEOUT_SEC = int(os.getenv("AI_TEXT_GROQ_TIMEOUT", "8"))
AI_LITELLM_TIMEOUT_SEC = int(os.getenv("AI_LITELLM_TIMEOUT", "12"))
AI_LITELLM_MAX_RETRIES = int(os.getenv("AI_LITELLM_MAX_RETRIES", "1"))


# ══════════════════════════════════════════════════════════════════════════════
# 1. LLMClient — 低層 API 呼叫（Gemini + Groq）
# ══════════════════════════════════════════════════════════════════════════════


class LLMClient:
    """統一的 LLM API 客戶端 (使用 LiteLLM)。

    - gemini()：呼叫 Gemini generateContent，支援原生 Function Calling
    - groq()  ：呼叫 Groq（OpenAI 相容格式），純文字，無工具
    - 內建自動降級、重試、速率限制保護
    """

    def __init__(self):
        try:
            from .ai_client_liteLLM import LiteLLMClient

            self._litellm_client = LiteLLMClient()
            self._use_litellm = True
            logger.info("✅ LLMClient 使用 LiteLLM")
        except ImportError:
            self._use_litellm = False
            self._cooldowns: Dict[str, float] = {}
            logger.warning("⚠️ LiteLLM 未安裝，使用傳統 API")

    def _is_cooling(self, name: str) -> bool:
        if self._use_litellm:
            return False
        exp = self._cooldowns.get(name, 0)
        if time.time() < exp:
            logger.warning(f"❄️ {name} 冷却中（{int(exp - time.time())}s 後恢復）")
            return True
        self._cooldowns.pop(name, None)
        return False

    def _cool(self, name: str, secs: int = 60):
        if self._use_litellm:
            return
        self._cooldowns[name] = time.time() + secs
        logger.warning(f"⏸️ {name} 進入冷却 {secs}s")

    async def gemini(
        self,
        api_key: str,
        model: str,
        system: str,
        contents: List[Dict],
        tools_spec: Optional[List[Dict]] = None,
        *,
        label: str = "Gemini",
    ) -> Optional[Dict]:
        """呼叫 Gemini generateContent，回傳第一個 candidate 或 None。

        caller 透過 candidate["content"]["parts"] 解析文字或 functionCall。
        """
        use_litellm = (
            self._use_litellm
            and not tools_spec
            and all(
                all("text" in part for part in content.get("parts", []))
                for content in contents
            )
        )

        if use_litellm:
            return await self._gemini_with_litellm(
                api_key, model, system, contents, tools_spec, label
            )
        else:
            return await self._gemini_traditional(
                api_key, model, system, contents, tools_spec, label
            )

    async def _gemini_with_litellm(
        self,
        api_key: str,
        model: str,
        system: str,
        contents: List[Dict],
        tools_spec: Optional[List[Dict]] = None,
        label: str = "Gemini",
    ) -> Optional[Dict]:
        """使用 LiteLLM 呼叫 Gemini"""
        # 轉換格式
        messages = [{"role": "system", "content": system}]

        for content in contents:
            role = content["role"]
            parts = content.get("parts", [])
            if parts and "text" in parts[0]:
                messages.append(
                    {
                        "role": "assistant" if role == "model" else "user",
                        "content": parts[0]["text"],
                    }
                )
            elif parts and "functionCall" in parts[0]:
                # 處理工具調用
                fc = parts[0]["functionCall"]
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"調用工具: {fc['name']}({fc.get('args', {})})",
                    }
                )

        response = await self._litellm_client.acomplete(
            messages,
            tools_spec,
            timeout=AI_LITELLM_TIMEOUT_SEC,
            max_retries=AI_LITELLM_MAX_RETRIES,
        )

        if response:
            tool_calls = response.get("tool_calls") or []
            if tool_calls:
                first_call = tool_calls[0]
                function_data = getattr(first_call, "function", None)
                arguments = (
                    getattr(function_data, "arguments", "{}") if function_data else "{}"
                )
                try:
                    parsed_args = (
                        json.loads(arguments)
                        if isinstance(arguments, str)
                        else (arguments or {})
                    )
                except json.JSONDecodeError:
                    parsed_args = {}

                return {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": getattr(function_data, "name", ""),
                                    "args": parsed_args,
                                }
                            }
                        ]
                    }
                }

            return {"content": {"parts": [{"text": response["content"]}]}}

        return None

    async def _gemini_traditional(
        self,
        api_key: str,
        model: str,
        system: str,
        contents: List[Dict],
        tools_spec: Optional[List[Dict]] = None,
        label: str = "Gemini",
    ) -> Optional[Dict]:
        """傳統 Gemini API 呼叫"""
        if self._is_cooling(label):
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 800,
                "topP": 0.9,
            },
        }
        if tools_spec:
            payload["tools"] = tools_spec

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=AI_GEMINI_TIMEOUT_SEC)
            ) as s:
                async with s.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                ) as r:
                    if r.status == 429:
                        self._cool(label)
                        return None
                    if r.status != 200:
                        body = await r.text()
                        logger.warning(f"⚠️ {label} HTTP {r.status}: {body[:200]}")
                        return None
                    data = await r.json()
                    cands = data.get("candidates", [])
                    return cands[0] if cands else None
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ {label} 超時")
            return None
        except Exception as e:
            logger.warning(f"⚠️ {label} 錯誤: {e}")
            return None

    async def groq(
        self,
        messages: List[Dict],
        model: str = "",
        max_tokens: int = 500,
    ) -> Optional[str]:
        """呼叫 Groq，回傳文字或 None。"""
        if self._use_litellm:
            return await self._groq_with_litellm(messages, model, max_tokens)
        else:
            return await self._groq_traditional(messages, model, max_tokens)

    async def _groq_with_litellm(
        self,
        messages: List[Dict],
        model: str = "",
        max_tokens: int = 500,
    ) -> Optional[str]:
        """使用 LiteLLM 呼叫 Groq"""
        response = await self._litellm_client.acomplete(
            messages,
            timeout=AI_LITELLM_TIMEOUT_SEC,
            max_retries=AI_LITELLM_MAX_RETRIES,
        )
        return response["content"] if response else None

    async def _groq_traditional(
        self,
        messages: List[Dict],
        model: str = "",
        max_tokens: int = 500,
    ) -> Optional[str]:
        """傳統 Groq API 呼叫"""
        if not GROQ_KEY:
            return None
        if self._is_cooling("Groq"):
            return None

        payload = {
            "model": model or GROQ_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=AI_GROQ_TIMEOUT_SEC)
            ) as s:
                async with s.post(GROQ_URL, json=payload, headers=headers) as r:
                    if r.status == 429:
                        self._cool("Groq")
                        return None
                    if r.status != 200:
                        logger.warning(f"⚠️ Groq HTTP {r.status}")
                        return None
                    data = await r.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0]["message"]["content"].strip()
        except asyncio.TimeoutError:
            logger.warning("⚠️ Groq 超時")
        except Exception as e:
            logger.warning(f"⚠️ Groq 錯誤: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 2. AgentSession — 每用戶 Session 記憶（短期）
# ══════════════════════════════════════════════════════════════════════════════


class AgentSession:
    """管理每個用戶的短期 Session 記憶（最近 N 輪，滑動窗口）。"""

    def __init__(self, max_turns: int = MAX_HISTORY):
        self.max_turns = max_turns
        self._history: Dict[int, List[Dict]] = {}

    def add(self, user_id: int, user_msg: str, bot_msg: str):
        h = self._history.setdefault(user_id, [])
        h.append({"role": "user", "parts": [{"text": user_msg}]})
        h.append({"role": "model", "parts": [{"text": bot_msg}]})
        if len(h) > self.max_turns * 2:
            self._history[user_id] = h[-(self.max_turns * 2) :]

    def build_contents(self, user_id: int, new_msg: str) -> List[Dict]:
        """組合歷史對話 + 新訊息，返回 Gemini contents 格式。"""
        h = self._history.get(user_id, [])
        return h + [{"role": "user", "parts": [{"text": new_msg}]}]

    def clear(self, user_id: int):
        self._history.pop(user_id, None)


# ══════════════════════════════════════════════════════════════════════════════
# 3. KKBotAgent — ADK 風格 Agent（官方 Agentic Loop）
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
你是 KK園區的 AI 助理，代號「干部」。
職責：
- 回答用戶問題，簡潔（150 字以內）
- 必要時呼叫工具查詢數據
- 你同時是中控室 NPC，要善用長期記憶、知識庫與 VM 掃描報告回答問題
- 使用繁體中文，語氣親切但專業

工具使用規則：
- 只在有明確數據需求時呼叫工具（餘額、排行榜、裝備等）
- 一般聊天不使用工具
- 呼叫工具後等待結果，再回覆用戶
"""

_MAX_TOOL_ROUNDS = int(os.getenv("AI_MAX_TOOL_ROUNDS", "2"))

_TOOL_KEYWORDS = [
    "餘額",
    "KK幣",
    "kkcoin",
    "排行",
    "狀態",
    "裝備",
    "配裝",
    "查詢",
    "查一下",
    "查",
    "找",
    "搜尋",
    "爬取",
    "抓取",
    "搜索",
    "search",
    "crawl",
    "fetch",
    "查找",
    "git",
    "推送",
    "日誌",
    "錯誤",
    "error",
    "代碼",
    "程式",
    "bot",
    "Bot",
    "服務",
    "service",
]


class KKBotAgent:
    """ADK 風格 Agent。

    Agentic Loop（官方 Sequential Workflow）：
      Think → Act（工具）→ Observe（結果）→ Think → ... → Final Reply

    API 降級：Gemini（主 Key → 備用 Key）→ Groq（純文字，無工具）
    """

    def __init__(self, llm: LLMClient, session: AgentSession):
        self.llm = llm
        self.session = session
        self._tools_spec: Optional[List[Dict]] = (
            agent_tools.get_gemini_tools_spec() if _TOOLS_AVAILABLE else None
        )

    @staticmethod
    def _build_system_prompt(user_msg: str) -> str:
        if not _MEMORY_AVAILABLE:
            return _SYSTEM_PROMPT

        memory_context = build_memory_context()
        vector_index = ChromaKnowledgeIndex()
        semantic_items = vector_index.hybrid_search(user_msg, limit=4)
        related_knowledge = KnowledgeBase.search_knowledge(user_msg, max_tokens=500)
        recent_vm_items = KnowledgeBase.get_recent_items(limit=3, category="vm_scan")

        vm_lines = []
        for item in recent_vm_items:
            vm_lines.append(f"- {item['topic']}: {item['content'][:180]}")

        semantic_lines = []
        for item in semantic_items:
            semantic_lines.append(
                f"- ({item.get('match_mode', 'semantic')}/{item.get('score', 0)}) {item['topic']}: {item['content'][:180]}"
            )

        prompt_parts = [_SYSTEM_PROMPT]

        system_instructions = memory_context.get("system_instructions", "").strip()
        if system_instructions:
            prompt_parts.append(f"=== 長期角色設定 ===\n{system_instructions}")

        knowledge_context = memory_context.get("knowledge_context", "").strip()
        if knowledge_context:
            prompt_parts.append(f"=== 全域知識摘要 ===\n{knowledge_context}")

        if related_knowledge:
            prompt_parts.append(f"=== 與目前問題最相關的知識 ===\n{related_knowledge}")

        if semantic_lines:
            prompt_parts.append(
                "=== 語意檢索命中的知識 ===\n" + "\n".join(semantic_lines)
            )

        if vm_lines:
            prompt_parts.append("=== 最近 VM 掃描摘要 ===\n" + "\n".join(vm_lines))

        prompt_parts.append(
            "=== 回答規則 ===\n"
            "- 若知識庫或 VM 掃描已有答案，優先引用這些內容。\n"
            "- 若你根據 repo 結構推測可擴充功能，請明確說出依據。\n"
            "- 若資料不足，直接說你需要再掃描或查工具。"
        )
        return "\n\n".join(part for part in prompt_parts if part)

    @staticmethod
    def _contents_to_messages(
        system_prompt: str, contents: List[Dict]
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for content in contents:
            role = content.get("role", "user")
            text = ""
            for part in content.get("parts", []):
                if "text" in part:
                    text = part["text"]
                    break
            if not text:
                continue
            messages.append(
                {
                    "role": "assistant" if role == "model" else "user",
                    "content": text,
                }
            )
        return messages

    async def run(self, user_id: int, user_msg: str) -> str:
        """主入口：給定用戶 ID 和訊息，回傳 AI 回應文字。"""
        contents = self.session.build_contents(user_id, user_msg)
        needs_tools = self._needs_tools(user_msg)
        tools_spec = self._tools_spec if (needs_tools and _TOOLS_AVAILABLE) else None
        system_prompt = self._build_system_prompt(user_msg)

        if not needs_tools:
            text_messages = self._contents_to_messages(system_prompt, contents)
            text_result, provider = await complete_text_with_fallback(
                text_messages,
                max_tokens=800,
                nvidia_timeout=AI_TEXT_NVIDIA_TIMEOUT_SEC,
                gemini_timeout=AI_TEXT_GEMINI_TIMEOUT_SEC,
                groq_timeout=AI_TEXT_GROQ_TIMEOUT_SEC,
            )
            if text_result:
                logger.info("✅ 文字回覆使用 %s", provider)
                self._save(user_id, user_msg, text_result)
                return text_result

        # ── 嘗試 Gemini（主要 Key → 備用 Key）────────────────────────────
        for key, label in [
            (GEMINI_KEY, "Gemini (主)"),
            (GEMINI_KEY_BK, "Gemini (備)"),
        ]:
            if not key:
                continue
            result = await self._gemini_loop(
                key, label, system_prompt, contents, tools_spec, user_id
            )
            if result:
                self._save(user_id, user_msg, result)
                return result

        # ── Gemini 全部失敗 → 降級至 Groq（無工具）─────────────────────
        logger.warning("⚠️ Gemini 全部不可用，降級至 Groq")
        groq_result = await self.llm.groq(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]
        )
        if groq_result:
            self._save(user_id, user_msg, groq_result)
            return groq_result

        return "中控室訊號中斷，請稍後再試。"

    async def _gemini_loop(
        self,
        api_key: str,
        label: str,
        system_prompt: str,
        initial_contents: List[Dict],
        tools_spec: Optional[List[Dict]],
        user_id: int,
    ) -> Optional[str]:
        """官方 Agentic Loop：Think → Act → Observe → Think... → Reply"""
        contents = list(initial_contents)

        for _round in range(_MAX_TOOL_ROUNDS + 1):
            # 最後一輪不帶工具，強制 LLM 輸出文字
            candidate = await self.llm.gemini(
                api_key,
                GEMINI_MODEL,
                system_prompt,
                contents,
                tools_spec=(tools_spec if _round < _MAX_TOOL_ROUNDS else None),
                label=label,
            )
            if candidate is None:
                return None

            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                return None

            # 純文字 → 完成
            if "text" in parts[0]:
                return parts[0]["text"].strip() or None

            # Function Call → 執行工具，注入結果，繼續迴圈
            if "functionCall" not in parts[0]:
                logger.warning(f"⚠️ {label} 未知 parts 類型: {list(parts[0].keys())}")
                return None

            fc = parts[0]["functionCall"]
            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            logger.info(f"🔧 [{label}] 工具呼叫: {tool_name}({tool_args})")
            tool_result = self._call_tool(tool_name, tool_args, caller_id=user_id)
            logger.info(f"✅ 工具結果: {str(tool_result)[:200]}")

            # 官方 Function Calling 格式：注入 model 的工具呼叫 + user 的工具結果
            contents.append({"role": "model", "parts": [{"functionCall": fc}]})
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tool_name,
                                "response": {"result": str(tool_result)},
                            }
                        }
                    ],
                }
            )

        logger.warning(f"⚠️ {label} 達到工具呼叫上限（{_MAX_TOOL_ROUNDS} 輪）")
        return None

    def _call_tool(self, name: str, args: Dict, caller_id: int) -> str:
        if not _TOOLS_AVAILABLE:
            return "工具系統未載入"
        try:
            return agent_tools.dispatch_tool(name, args, caller_id=caller_id)
        except Exception as e:
            logger.warning(f"⚠️ 工具執行失敗 {name}: {e}")
            return f"工具執行錯誤: {e}"

    def _save(self, user_id: int, user_msg: str, reply: str):
        self.session.add(user_id, user_msg, reply)
        try:
            importance = 0.8 if len(user_msg) > 50 else 0.5
            DialogueMemory.add_dialogue(user_msg, reply, importance=importance)
        except Exception:
            pass

    @staticmethod
    def _needs_tools(msg: str) -> bool:
        """判斷是否需要工具（避免普通聊天帶上工具規格浪費 token）。"""
        if len(msg) < 5:
            return False
        return any(k in msg for k in _TOOL_KEYWORDS) or len(msg) > 200


# ══════════════════════════════════════════════════════════════════════════════
# 4. AIResponse — Discord Cog
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)


class AIResponse(commands.Cog):
    """處理 @tag 訊息，路由至 KKBotAgent。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _llm = LLMClient()
        _session = AgentSession()
        self._agent = KKBotAgent(_llm, _session)
        try:
            initialize_memory_system()
        except Exception:
            pass
        logger.info("✅ AIResponse（ADK 架構）初始化完成")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not self.bot.user.mentioned_in(message):
            return

        user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not user_input:
            return

        async with message.channel.typing():
            try:
                reply = await asyncio.wait_for(
                    self._agent.run(message.author.id, user_input),
                    timeout=AI_INTERACTIVE_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                reply = "處理超時，請再試一次。"
            except Exception as e:
                logger.error(f"Agent 執行錯誤: {e}", exc_info=True)
                reply = "中控室發生內部錯誤。"

        await message.reply(reply)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIResponse(bot))
