"""
KK群組 - 核心 Agent 邏輯 (獨立模組，無 Discord 依賴)
===========================================================
從 claude_code.py 抽離，設計為可在獨立進程/服務中運行。

特性：
- 無 Discord 依賴（純 Python + Anthropic/OpenAI 相容 API）
- 工具延遲載入（Lazy Import），降低啟動記憶體
- 任務 ID 追蹤、狀態持久化介面
- 進度回調介面（支援 WebSocket / HTTP 長輪詢 / 簡單 callback）
- 取消/暫停/恢復控制
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 環境變數與設定 ─────────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_API_URL = os.getenv(
    "NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
)
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))
MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "20"))
WORK_DIR = Path(os.getenv("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")).resolve()


# ─── 狀態定義 ─────────────────────────────────────────────────────
class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ─── 進度回調介面 ─────────────────────────────────────────────────────
ProgressCallback = Callable[[str], Any]  # 接收進度文字，可為 async


# ─── 任務存儲介面 ─────────────────────────────────────────────────────
class TaskStore(ABC):
    """任務狀態持久化抽象介面（可換 SQLite/Redis/PostgreSQL）"""

    @abstractmethod
    async def create(self, task_id: str, task_type: str, payload: dict) -> None:
        pass

    @abstractmethod
    async def update(self, task_id: str, **fields) -> None:
        pass

    @abstractmethod
    async def get(self, task_id: str) -> dict | None:
        pass

    @abstractmethod
    async def list(self, status: str | None = None, limit: int = 50) -> list[dict]:
        pass


# ─── 基礎設施：NVIDIA NIM Client ─────────────────────────────────────
class NvidiaNimClient:
    """NVIDIA NIM API 客戶端 (OpenAI 相容格式)"""

    def __init__(self, api_key: str, api_url: str = NVIDIA_API_URL):
        self.api_key = api_key
        self.api_url = api_url
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> "aiohttp.ClientSession":
        """延遲建立 session"""
        if self._session is None or self._session.closed:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=300)
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"}, timeout=timeout
            )
        return self._session

    async def create_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
    ) -> dict:
        # 模型自動選擇邏輯
        if model == "auto":
            model = "nvidia/nemotron-3-super-120b-a12b"  # 默認較快模型

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }
        if system:
            payload["system"] = system

        async with self.session.post(self.api_url, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"NVIDIA API Error {resp.status}: {error_text}")
            data = await resp.json()
            return data["choices"][0]["message"]

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ─── 基礎設施：工具執行器 (延遲載入) ─────────────────────────────────
class ToolExecutor:
    """工具執行器 - 延遲載入具體實作以降低啟動記憶體"""

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self._tools_module = None

    @property
    def tools(self):
        """延遲導入 tools 實作"""
        if self._tools_module is None:
            from . import tools  # 延遲導入

            self._tools_module = tools.ToolImpl(self.work_dir)
        return self._tools_module

    async def execute(self, name: str, args: dict) -> str:
        method = getattr(self.tools, name, None)
        if not method:
            return f"❌ 未知工具: {name}"
        try:
            return await method(**args)
        except PermissionError as e:
            return f"❌ 權限拒絕: {e}"
        except FileNotFoundError as e:
            return f"❌ 檔案不存在: {e}"
        except TimeoutError as e:
            return f"❌ {e}"
        except Exception as e:
            logger.exception(f"Tool {name} error")
            return f"❌ 執行錯誤: {e}"


# ─── 核心 Agent 類別 ─────────────────────────────────────────────────
class ClaudeCodeAgent:
    """
    Claude Code Agent - Agentic Loop 實作

    設計原則：
    - 無 Discord 依賴
    - 狀態可序列化（支援斷點續傳）
    - 進度回調解耦（適配 HTTP/WebSocket/CLI）
    """

    def __init__(
        self,
        task_id: str,
        user_id: int = 0,
        channel_id: int = 0,
        progress_callback: ProgressCallback | None = None,
        task_store: TaskStore | None = None,
    ):
        self.task_id = task_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.client = NvidiaNimClient(NVIDIA_API_KEY) if NVIDIA_API_KEY else None
        self.tools = ToolExecutor(WORK_DIR)
        self.history: list[dict] = []
        self.turn_count = 0
        self.progress_callback = progress_callback
        self._progress_content: list[str] = []
        self._cancelled = asyncio.Event()
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._started_at = datetime.utcnow()
        self._task_store = task_store
        self._status = TaskStatus.PENDING

    # ─── 狀態管理 ────────────────────────────────────────────────
    @property
    def status(self) -> str:
        return self._status

    def _set_status(self, status: str):
        self._status = status
        if self._task_store:
            asyncio.create_task(self._task_store.update(self.task_id, status=status))

    # ─── 進度回調 ────────────────────────────────────────────────
    async def _add_progress(self, message: str):
        """記錄進度並觸發回調"""
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        self._progress_content.append(formatted)

        if self.progress_callback:
            try:
                # 傳遞完整累積進度
                await self.progress_callback("\n".join(self._progress_content))
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def get_progress(self) -> str:
        return "\n".join(self._progress_content)

    def cancel(self):
        self._cancelled.set()
        self._set_status(TaskStatus.CANCELLED)

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def pause(self):
        self._paused = True
        self._pause_event.clear()
        self._set_status(TaskStatus.PAUSED)

    def resume(self):
        self._paused = False
        self._pause_event.set()
        self._set_status(TaskStatus.RUNNING)

    def is_paused(self) -> bool:
        return self._paused

    async def _wait_if_paused(self):
        while self._paused:
            await self._pause_event.wait()
            await asyncio.sleep(0.5)

    # ─── 系統提示詞 ──────────────────────────────────────────────
    def _build_system_prompt(self) -> str:
        # 延遲導入記憶系統
        try:
            from shared.db.ai_memory import build_memory_context

            memory = build_memory_context()
            context = SYSTEM_PROMPT.format(work_dir=WORK_DIR)
            if memory.get("system_instructions"):
                context += "\n\n" + memory["system_instructions"]
            if memory.get("knowledge_context"):
                context += "\n\n=== 知識庫 ===\n" + memory["knowledge_context"]
            return context
        except Exception as e:
            logger.warning(f"Failed to build memory context: {e}")
            return SYSTEM_PROMPT.format(work_dir=WORK_DIR)

    # ─── 主執行循環 ──────────────────────────────────────────────
    async def run(self, user_input: str) -> str:
        """主入口：執行 agentic loop"""
        if not self.client:
            return "❌ NVIDIA_API_KEY 未設定，無法使用 Agent 功能。"

        self._set_status(TaskStatus.RUNNING)
        await self._add_progress(f"🚀 任務開始: {user_input[:100]}")

        # 載入歷史（如有）
        await self._load_history()

        # 加入用戶輸入
        self.history.append({"role": "user", "content": user_input})

        system_prompt = self._build_system_prompt()

        try:
            while self.turn_count < MAX_TURNS:
                if self.is_cancelled():
                    await self._add_progress("🛑 任務已取消")
                    return "🛑 任務已由使用者取消"

                await self._wait_if_paused()
                self.turn_count += 1
                await self._add_progress(f"🔄 第 {self.turn_count} 輪：思考中...")

                # 呼叫 API
                response = await self.client.create_message(
                    messages=self.history,
                    system=system_prompt,
                    tools=TOOLS,
                )

                content = response.get("content", [])
                tool_uses = [c for c in content if c.get("type") == "tool_use"]
                texts = [c.get("text", "") for c in content if c.get("type") == "text"]

                # 顯示思考過程
                if texts:
                    thinking = "\n".join(texts).strip()
                    if thinking:
                        if len(thinking) > 200:
                            thinking = thinking[:197] + "..."
                        await self._add_progress(
                            f"💭 第 {self.turn_count} 輪：{thinking}"
                        )

                # 執行工具
                if tool_uses:
                    self.history.append({"role": "assistant", "content": content})

                    for tool_use in tool_uses:
                        tool_name = tool_use["name"]
                        args = tool_use["input"]
                        detail = self._format_tool_detail(tool_name, args)
                        await self._add_progress(
                            f"🔧 第 {self.turn_count} 輪：執行 {tool_name} {detail}"
                        )

                        result = await self.tools.execute(tool_name, args)
                        self.history.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_use["id"],
                                        "content": result,
                                    }
                                ],
                            }
                        )
                    continue

                # 純文字回覆：任務完成
                reply = "\n".join(texts).strip()
                if reply:
                    await self._add_progress("✅ 任務完成")
                    await self._save_history(user_input, reply)
                    self._set_status(TaskStatus.COMPLETED)
                    return reply

                self.history.append({"role": "assistant", "content": content})

            # 超過輪數上限
            await self._add_progress(f"⚠️ 達到最大輪數 ({MAX_TURNS})")
            self._set_status(TaskStatus.COMPLETED)
            return f"⚠️ 已達最大輪數上限（{MAX_TURNS}），任務可能未完全結束。"

        except Exception as e:
            logger.exception("Agent run error")
            self._set_status(TaskStatus.FAILED)
            await self._add_progress(f"❌ 錯誤: {e}")
            raise

    # ─── 工具細節格式化 ──────────────────────────────────────────
    def _format_tool_detail(self, tool_name: str, args: dict) -> str:
        if tool_name == "read":
            path = args.get("path", "")
            offset = args.get("offset")
            limit = args.get("limit")
            detail = f"📄 {path}"
            if offset is not None or limit is not None:
                parts = []
                if offset is not None:
                    parts.append(f"第 {offset + 1} 行")
                if limit is not None:
                    parts.append(f"{limit} 行")
                detail += f" ({', '.join(parts)})"
            return detail
        elif tool_name == "write":
            path = args.get("path", "")
            content_len = len(args.get("content", ""))
            return f"📝 {path} ({content_len} 字元)"
        elif tool_name == "edit":
            path = args.get("path", "")
            old_len = len(args.get("old_string", ""))
            new_len = len(args.get("new_string", ""))
            return f"✏️ {path} ({old_len}→{new_len} 字元)"
        elif tool_name == "list":
            path = args.get("path", ".")
            return f"📁 {path}"
        elif tool_name == "glob":
            pattern = args.get("pattern", "")
            path = args.get("path", ".")
            return f"🔍 {path}/{pattern}"
        elif tool_name == "bash":
            cmd = args.get("command", "")
            if len(cmd) > 80:
                cmd = cmd[:77] + "..."
            return f"💻 {cmd}"
        elif tool_name == "scan_journalctl":
            svc = args.get("service", "all")
            since = args.get("since_minutes", 15)
            return f"📋 journalctl {svc} 最近 {since} 分鐘"
        elif tool_name == "search_code":
            pattern = args.get("pattern", "")
            path = args.get("path", ".")
            return f"🔍 grep {pattern} in {path}"
        return ""

    # ─── 歷史持久化 ──────────────────────────────────────────────
    async def _load_history(self):
        """從資料庫載入該用戶的最近對話"""
        try:
            from shared.db.ai_memory import DialogueMemory

            history_text = DialogueMemory.get_recent_dialogue(max_tokens=2000)
            if not history_text:
                return
            sections = history_text.split("\n\n---\n\n")
            for section in sections[-10:]:
                lines = section.strip().split("\n")
                if (
                    len(lines) >= 2
                    and lines[0].startswith("用戶:")
                    and lines[1].startswith("AI:")
                ):
                    user_query = lines[0][3:].strip()
                    ai_response = "\n".join(lines[1:])[3:].strip()
                    self.history.append({"role": "user", "content": user_query})
                    self.history.append({"role": "assistant", "content": ai_response})
        except Exception as e:
            logger.warning(f"載入歷史失敗: {e}")

    async def _save_history(self, user_input: str, reply: str):
        """儲存對話到記憶系統"""
        try:
            from shared.db.ai_memory import DialogueMemory

            DialogueMemory.add_dialogue(user_input, reply, importance=0.6)
        except Exception as e:
            logger.warning(f"儲存記憶失敗: {e}")

    # ─── 序列化（用於斷點續傳/狀態查詢） ─────────────────────────
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "status": self._status,
            "turn_count": self.turn_count,
            "started_at": self._started_at.isoformat(),
            "progress": self.get_progress(),
            "history_length": len(self.history),
        }

    async def close(self):
        await self.client.close()


# ─── 工具定義 (Anthropic/OpenAI 格式) ──────────────────────────────
TOOLS = [
    {
        "name": "read",
        "description": "讀取檔案內容（支援行號範圍）",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "檔案路徑（相對於工作目錄）"},
                "offset": {"type": "integer", "description": "起始行號（0-based）"},
                "limit": {"type": "integer", "description": "讀取行數"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write",
        "description": "寫入檔案（覆蓋或新建）",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "檔案路徑"},
                "content": {"type": "string", "description": "檔案內容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit",
        "description": "編輯檔案（精確字串替換）",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "檔案路徑"},
                "old_string": {
                    "type": "string",
                    "description": "要替換的原字串（需唯一匹配）",
                },
                "new_string": {"type": "string", "description": "新字串"},
                "replace_all": {
                    "type": "boolean",
                    "description": "是否替換所有匹配",
                    "default": False,
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list",
        "description": "列出目錄內容",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目錄路徑", "default": "."},
            },
        },
    },
    {
        "name": "glob",
        "description": "Glob 模式搜尋檔案",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob 模式"},
                "path": {"type": "string", "description": "搜尋根目錄", "default": "."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "bash",
        "description": "執行 shell 命令",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "命令字串"},
                "timeout": {
                    "type": "integer",
                    "description": "超時秒數",
                    "default": 60,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_code",
        "description": "在代碼庫中搜尋（ripgrep）",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正則模式"},
                "path": {"type": "string", "description": "搜尋路徑", "default": "."},
                "glob": {"type": "string", "description": "檔案過濾", "default": ""},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "scan_journalctl",
        "description": "掃描 systemd journal 錯誤日誌",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "enum": ["bot", "shopbot", "uibot", "kkgroup-api", "all"],
                    "default": "all",
                },
                "since_minutes": {"type": "integer", "default": 15},
                "level": {
                    "type": "string",
                    "enum": ["error", "warning", "all"],
                    "default": "error",
                },
                "pattern": {"type": "string", "description": "grep 模式"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
]

# ─── 系統提示詞 ────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是 KK園區的 Code Agent，專業的程式開發助手。
工作目錄：{work_dir}

核心能力：
- 讀寫編輯檔案、執行命令、搜尋代碼、掃描系統日誌
- 遵循專案編碼規範（參考 knowledge/_wiki/concepts/coding-rules-and-paths.md）
- 使用結構化日誌分析系統異常
- 產出最小、可驗證的修復

工具使用原則：
1. 先搜尋/讀取理解上下文，再動手修改
2. 優先用 search_code/glob 定位，避免盲目讀取
3. 修改後務必用 bash 執行測試/驗證
4. 遇到系統錯誤優先用 scan_journalctl 定位

輸出風格：簡潔、結構化、可執行。
"""
