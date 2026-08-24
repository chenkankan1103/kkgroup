"""
KK園區 Claude Code CLI 移植版
====================================================================
完整移植 Claude Code CLI 核心功能到 Discord Bot，僅限：
- Discord 管理員（.env 中 ADMIN_USER_ID 設定）
- 透過 /cc 指令觸發（移除自動監聽 thread 功能）

架構：
- 使用 Anthropic Messages API (tool_use) 實現 agentic loop
- 內建 7 個核心工具：read, write, edit, list, glob, bash, task
- 路徑安全防護：防止目錄遍歷、禁止敏感路徑
- 記憶持久化：對話歷史儲存到 ai_memory.db
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from shared.db.ai_memory import (
    DialogueMemory,
    build_memory_context,
    initialize_memory_system,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 環境變數與權限設定 ─────────────────────────────────────────────────────
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# NVIDIA NIM API (OpenAI compatible)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
if not NVIDIA_API_KEY:
    logger.warning("⚠️ NVIDIA_API_KEY 未設定，Claude Code 功能將無法使用")
NVIDIA_API_URL = os.getenv(
    "NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
)

# 兩個 Nemotron 模型（用戶指定）
MODEL_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"  # 較難的任務
MODEL_SUPER = "nvidia/nemotron-3-super-120b-a12b"  # 一般回復
DEFAULT_MODEL = MODEL_SUPER

MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))
MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "20"))

# 工作目錄（專案根目錄）
WORK_DIR = Path(os.getenv("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")).resolve()

# 禁止存取的敏感路徑
BLOCKED_PATHS = {
    "/etc",
    "/root",
    "/home",
    "/var",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
    "/run",
    "/tmp",
    "/srv",
    "/opt",
    "/mnt",
    "/media",
}
BLOCKED_FILES = {".env", ".ssh", "id_rsa", "id_ed25519", "authorized_keys", "config"}
BLOCKED_PREFIXES = [
    ".git/",
    ".github/",
    "__pycache__/",
    "venv/",
    ".venv/",
    "node_modules/",
]

# ─── 系統提示詞 ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是 KK園區的 Claude Code 代理，一個專業的程式開發助手（使用 NVIDIA Nemotron 模型）。
工作目錄：{work_dir}

可用模型（自動選擇）：
- Nemotron-3-Ultra (550B): 複雜推理、代碼生成、架構設計、重構
- Nemotron-3-Super (120B): 一般對話、簡單任務、快速回覆

核心能力：
- 讀寫編輯檔案、執行命令、搜尋代碼
- 遵循專案編碼規範（參考 knowledge/_wiki/concepts/coding-rules-and-paths.md）
- 使用專案現有模組而非重造輪子（ponytail 原則：YAGNI → reuse → stdlib → native → deps）

【代碼搜尋】—— 用 bash + ripgrep (rg)，極快、零配置：
  rg "pattern" --type py -n                    # 搜尋 Python，顯示行號
  rg "class.*Agent" --type py                  # 找所有 Agent 類別
  rg "def.*search" --type py -A 3 -B 1         # 找函數含上下文 3 行
  rg "TODO|FIXME" --type py                    # 找待辦註解
  rg "import.*memory" --type py -l             # 只列檔名
  rg "async def" --type py | head -20          # 限制輸出行數

工具使用規則：
1. 每次只呼叫一個工具（read/write/edit/list/glob/bash/task）
2. 工具結果會自動注入對話，你根據結果決定下一步
3. 任務完成時直接輸出文字回覆，不再呼叫工具
4. 路徑必須在工作目錄內，禁止存取系統敏感目錄

專案特有規則：
- Discord.py 2.0：用 interaction.response.defer() 後用 followup.send()
- 字型路徑：從 cogs/common/ 出發需 ../../fonts/（三層 ../）
- 資料庫：使用 parameterized queries，啟用 WAL 模式
- 非同步：用 asyncio.gather() 平行操作，避免熱路徑 sleep
- 類別/公開方法需有 docstring（解釋 WHY，不只是 WHAT）

當前專案狀態：e2-micro (1GB RAM)，已啟用 zram 1GB swap，三服務記憶體限制已優化。"""

# ─── 工具規格定義（Anthropic tool_use 格式）────────────────────────────────
TOOLS = [
    {
        "name": "read",
        "description": "讀取檔案內容",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "檔案路徑（相對或絕對）"},
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
        "description": "精確編輯檔案（字串替換）",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "檔案路徑"},
                "old_string": {
                    "type": "string",
                    "description": "要替換的原始字串（需唯一匹配）",
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
                "path": {"type": "string", "description": "目錄路徑"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "glob",
        "description": " Glob 模式搜尋檔案",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob 模式（如 **/*.py）"},
                "path": {"type": "string", "description": "搜尋根目錄"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "bash",
        "description": "執行 Shell 指令",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要執行的指令"},
                "timeout": {
                    "type": "integer",
                    "description": "超時秒數",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "task",
        "description": "啟動子任務（複雜操作委派）",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "子任務描述"},
                "prompt": {"type": "string", "description": "詳細指令"},
            },
            "required": ["description", "prompt"],
        },
    },
]


# ─── 路徑安全驗證 ───────────────────────────────────────────────────────────
def validate_path(path: str, must_exist: bool = False) -> Path:
    """驗證並解析路徑，確保在工作目錄內且不存取敏感路徑"""
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = (WORK_DIR / p).resolve()
        else:
            p = p.resolve()

        # 必須在工作目錄內
        try:
            p.relative_to(WORK_DIR)
        except ValueError:
            raise PermissionError(f"路徑超出工作目錄範圍: {path}")

        # 檢查敏感路徑
        parts = set(p.parts)
        if parts & BLOCKED_PATHS:
            raise PermissionError(f"禁止存取系統目錄: {path}")

        # 檢查敏感檔案
        if p.name in BLOCKED_FILES:
            raise PermissionError(f"禁止存取敏感檔案: {p.name}")

        # 檢查敏感前綴
        for prefix in BLOCKED_PREFIXES:
            if prefix in str(p.relative_to(WORK_DIR)):
                raise PermissionError(f"禁止存取 {prefix} 目錄")

        if must_exist and not p.exists():
            raise FileNotFoundError(f"檔案不存在: {path}")

        return p
    except (PermissionError, FileNotFoundError):
        raise
    except Exception as e:
        raise ValueError(f"路徑無效: {path} - {e}")


# ─── 工具實作 ────────────────────────────────────────────────────────────────
class ToolExecutor:
    """工具執行器"""

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir

    async def read(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        p = validate_path(path, must_exist=True)
        if p.stat().st_size > 10 * 1024 * 1024:  # 10MB 限制
            raise ValueError("檔案過大（>10MB），請用 offset/limit 分段讀取")

        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        if offset or limit != 2000:
            lines = lines[offset : offset + limit]
        result = "\n".join(lines)
        return f"=== {p} ===\n{result}"

    async def write(self, path: str, content: str) -> str:
        p = validate_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ 已寫入: {p} ({len(content)} 字元)"

    async def edit(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        p = validate_path(path, must_exist=True)
        content = p.read_text(encoding="utf-8")

        if old_string not in content:
            raise ValueError("old_string 未在檔案中找到")

        if not replace_all and content.count(old_string) > 1:
            raise ValueError(
                "old_string 匹配多處，請設定 replace_all=true 或提供更精確的字串"
            )

        new_content = (
            content.replace(old_string, new_string)
            if replace_all
            else content.replace(old_string, new_string, 1)
        )
        p.write_text(new_content, encoding="utf-8")
        return f"✅ 已編輯: {p}"

    async def list(self, path: str) -> str:
        p = validate_path(path, must_exist=True)
        if not p.is_dir():
            raise ValueError("路徑不是目錄")

        items = []
        for item in sorted(p.iterdir()):
            prefix = "📁" if item.is_dir() else "📄"
            size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
            items.append(f"{prefix} {item.name}{size}")
        return f"=== {p} ===\n" + "\n".join(items) if items else "(空目錄)"

    async def glob(self, pattern: str, path: str = ".") -> str:
        p = validate_path(path, must_exist=True)
        matches = list(p.rglob(pattern))
        if not matches:
            return f"無匹配檔案: {pattern}"

        # 限制輸出
        results = []
        for m in matches[:100]:
            rel = m.relative_to(self.work_dir)
            prefix = "📁" if m.is_dir() else "📄"
            results.append(f"{prefix} {rel}")

        if len(matches) > 100:
            results.append(f"... 還有 {len(matches) - 100} 個結果")
        return "\n".join(results)

    async def bash(self, command: str, timeout: int = 30) -> str:
        # 安全檢查：禁止危險指令
        dangerous = [
            "rm -rf /",
            "shutdown",
            "reboot",
            "mkfs",
            "dd if=",
            "> /dev/",
            "chmod 777",
            "chown root",
            "passwd",
            "userdel",
            "groupdel",
        ]
        for d in dangerous:
            if d in command:
                raise PermissionError(f"禁止執行危險指令: {d}")

        # 在工作目錄執行
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONPATH": str(self.work_dir)},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            result = f"[exit {proc.returncode}]\n{out}"
            if err:
                result += f"\n[stderr]\n{err}"
            return result[:10000]  # 限制輸出大小
        except TimeoutError:
            raise TimeoutError(f"指令超時 ({timeout}s)")

    async def task(self, description: str, prompt: str) -> str:
        # 子任務：建立新的 agent 實例執行（簡化版：直接返回說明）
        return f"[子任務] {description}\n提示: {prompt}\n\n(子任務功能簡化版：請在主對話中繼續操作)"


# ─── NVIDIA NIM API 客戶端 (OpenAI 兼容格式) ──────────────────────────────────
class NvidiaNimClient:
    """NVIDIA NIM API 客戶端 - OpenAI 兼容格式

    支持工具調用 (function calling)，模型自動選擇：
    - nemotron-3-ultra-550b: 複雜任務、代碼生成、推理
    - nemotron-3-super-120b: 一般對話、簡單任務
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=180),  # NVIDIA 較慢，增加超時
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self.session

    def _convert_tools_to_openai(self, tools: list[dict]) -> list[dict]:
        """將 Anthropic tool 格式轉換為 OpenAI function calling 格式"""
        openai_tools = []
        for tool in tools:
            # NVIDIA NIM 使用 functions 格式
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
            )
        return openai_tools

    def _convert_messages_to_openai(
        self, messages: list[dict], system: str
    ) -> list[dict]:
        """將 Anthropic messages 格式轉換為 OpenAI 格式"""
        openai_messages = []

        # 系統提示詞
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "user":
                if isinstance(content, str):
                    openai_messages.append({"role": "user", "content": content})
                elif isinstance(content, list):
                    # 處理 tool_result 格式
                    for block in content:
                        if block.get("type") == "tool_result":
                            openai_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": block.get("tool_use_id", "unknown"),
                                    "content": str(block.get("content", "")),
                                }
                            )

            elif role == "assistant":
                if isinstance(content, str):
                    openai_messages.append({"role": "assistant", "content": content})
                elif isinstance(content, list):
                    # 構建 assistant 訊息，可能包含 tool_calls
                    tool_calls = []
                    text_parts = []
                    for block in content:
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block.get("id"),
                                    "type": "function",
                                    "function": {
                                        "name": block.get("name"),
                                        "arguments": json.dumps(block.get("input", {})),
                                    },
                                }
                            )

                    msg_dict = {"role": "assistant"}
                    if text_parts:
                        msg_dict["content"] = "\n".join(text_parts)
                    if tool_calls:
                        msg_dict["tool_calls"] = tool_calls
                    openai_messages.append(msg_dict)

        return openai_messages

    def _select_model(self, messages: list[dict], tools: list[dict]) -> str:
        """根據任務複雜度選擇模型

        較難的任務特徵：
        - 需要多輪工具調用
        - 代碼生成/編輯
        - 複雜推理
        - 長上下文
        """
        # 簡單啟發式：如果有工具且歷史較長，用 ultra
        has_tools = len(tools) > 0
        history_len = len(messages)

        # 檢查最近用戶輸入關鍵詞
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    last_user_msg = content.lower()
                elif isinstance(content, list):
                    for block in content:
                        if block.get("type") == "text":
                            last_user_msg = block.get("text", "").lower()
                break

        complex_keywords = [
            "重構",
            "架構",
            "優化",
            "debug",
            "除錯",
            "重寫",
            "實現",
            "設計",
            "refactor",
            "architecture",
            "optimize",
            "implement",
            "design",
            "複雜",
            "complex",
            "完整",
            "complete",
            "系統",
        ]

        is_complex = any(kw in last_user_msg for kw in complex_keywords)

        if has_tools and (history_len > 10 or is_complex):
            return MODEL_ULTRA
        return MODEL_SUPER

    async def create_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = MAX_TOKENS,
    ) -> dict:
        """創建聊天完成請求，返回 Anthropic 兼容格式（含限流重試）"""
        session = await self._get_session()

        # 選擇模型
        model = self._select_model(messages, tools)
        logger.info(
            f"🤖 選擇模型: {model} (輪數: {len(messages)//2}, 工具: {len(tools)})"
        )

        # 轉換格式
        openai_messages = self._convert_messages_to_openai(messages, system)
        openai_tools = self._convert_tools_to_openai(tools)

        payload = {
            "model": model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "tools": openai_tools if openai_tools else None,
            "tool_choice": "auto" if openai_tools else None,
            "stream": False,
        }

        payload = {k: v for k, v in payload.items() if v is not None}

        # 重試邏輯：限流/暫時性錯誤/網路異常時指數退避
        max_retries = 3
        base_delay = 2.0  # 秒
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(max_retries):
            try:
                async with session.post(NVIDIA_API_URL, json=payload) as resp:
                    if resp.status in retryable_statuses:
                        # 讀取 Retry-After header（若有）
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = base_delay * (2**attempt)
                        else:
                            delay = base_delay * (2**attempt)

                        if attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️ NVIDIA NIM 錯誤 ({resp.status})，第 {attempt + 1}/{max_retries} 次重試，等待 {delay:.1f}s..."
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            raise Exception(
                                f"NVIDIA NIM 暫時性錯誤 ({resp.status})，重試 {max_retries} 次後仍失敗"
                            )

                    if resp.status != 200:
                        text = await resp.text()
                        raise Exception(f"NVIDIA API Error {resp.status}: {text[:500]}")

                    result = await resp.json()
                    return self._convert_response_to_anthropic(result)

            except (TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"⚠️ NVIDIA NIM 網路錯誤: {type(e).__name__}: {e}，第 {attempt + 1}/{max_retries} 次重試，等待 {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception(
                        f"NVIDIA NIM 網路錯誤，重試 {max_retries} 次後仍失敗: {e}"
                    )

    def _convert_response_to_anthropic(self, openai_response: dict) -> dict:
        """將 OpenAI 回應格式轉換為 Anthropic 兼容格式"""
        choice = openai_response.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = []

        # 文字內容
        if message.get("content"):
            content.append({"type": "text", "text": message["content"]})

        # 工具調用
        for tool_call in message.get("tool_calls", []):
            func = tool_call.get("function", {})
            content.append(
                {
                    "type": "tool_use",
                    "id": tool_call.get("id", "call_" + str(hash(str(func)))),
                    "name": func.get("name"),
                    "input": json.loads(func.get("arguments", "{}")),
                }
            )

        # 如果沒有任何內容
        if not content:
            content.append({"type": "text", "text": ""})

        return {
            "content": content,
            "stop_reason": "tool_use" if message.get("tool_calls") else "end_turn",
            "usage": openai_response.get("usage", {}),
        }

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# ─── Agent 核心邏輯 ─────────────────────────────────────────────────────────
class ClaudeCodeAgent:
    """Claude Code Agent - Agentic Loop 實作 (NVIDIA NIM 版本)"""

    def __init__(self, user_id: int, channel_id: int, progress_callback=None):
        self.user_id = user_id
        self.channel_id = channel_id
        self.client = NvidiaNimClient(NVIDIA_API_KEY)
        self.tools = ToolExecutor(WORK_DIR)
        self.history: list[dict] = []
        self.turn_count = 0
        self.progress_callback = progress_callback  # 進度回調函數
        self._last_progress_update = 0  # 上次更新時間戳
        self._progress_interval = 10  # 更新間隔（秒）
        self._progress_buffer: list[str] = []  # 進度緩衝區
        self._buffer_lock = asyncio.Lock()
        self._cancelled = asyncio.Event()  # 取消信號
        self._paused = False  # 暫停狀態
        self._pause_event = asyncio.Event()  # 暫停/恢復事件
        self._pause_event.set()  # 預設為非暫停狀態
        self._progress_content: list[
            str
        ] = []  # 累積的完整進度內容（用於編輯同一條 message 顯示所有步驟）

    async def _flush_progress_buffer(self):
        """將緩衝區內容合併發送"""
        async with self._buffer_lock:
            if not self._progress_buffer:
                return
            content = "\n".join(self._progress_buffer)
            self._progress_buffer.clear()
        try:
            if self.progress_callback:
                await self.progress_callback(content)
        except Exception as e:
            logger.warning(f"進度回調失敗: {e}")

    async def _add_progress(self, message: str):
        """發送進度更新（累積到完整內容，並觸發 callback）"""
        # 累積完整進度內容
        self._progress_content.append(message)

        if self.progress_callback:
            try:
                # 傳遞完整累積內容給 callback（由 callback 決定如何顯示/分割）
                await self.progress_callback("\n".join(self._progress_content))
            except Exception as e:
                logger.warning(f"進度回調失敗: {e}")
        else:
            # 兼容舊模式：緩衝區
            async with self._buffer_lock:
                self._progress_buffer.append(message)

            import time

            now = time.time()
            if now - self._last_progress_update >= self._progress_interval:
                self._last_progress_update = now
                await self._flush_progress_buffer()

    async def _finalize_progress(self):
        """強制發送剩餘緩衝區內容（舊模式）"""
        await self._flush_progress_buffer()

    def cancel(self):
        """取消執行中的任務（完全終止）"""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def pause(self):
        """暫停任務（可恢復）"""
        self._paused = True
        self._pause_event.clear()

    def resume(self):
        """恢復任務"""
        self._paused = False
        self._pause_event.set()

    def is_paused(self) -> bool:
        return getattr(self, "_paused", False)

    async def _wait_if_paused(self):
        """如果任務被暫停，等待恢復"""
        while getattr(self, "_paused", False):
            await self._pause_event.wait()
            # 等待恢復信號
            await asyncio.sleep(0.5)

    def _build_system_prompt(self) -> str:
        # 獲取長期記憶上下文
        memory = build_memory_context()
        context = SYSTEM_PROMPT.format(work_dir=WORK_DIR)
        if memory["system_instructions"]:
            context += "\n\n" + memory["system_instructions"]
        if memory["knowledge_context"]:
            context += "\n\n=== 知識庫 ===\n" + memory["knowledge_context"]
        return context

    async def run(self, user_input: str, progress_callback=None) -> str:
        """主入口：執行 agentic loop（無輪數上限，直到完成任務）"""
        if not NVIDIA_API_KEY:
            return "❌ NVIDIA_API_KEY 未設定，無法使用 Claude Code 功能。請在 .env 中設定。"

        # 允許外部傳入 progress_callback（用於編輯同一條 message 的模式）
        if progress_callback:
            self.progress_callback = progress_callback

        # 載入該用戶的對話歷史
        self._load_history()

        # 加入用戶輸入
        self.history.append({"role": "user", "content": user_input})

        system_prompt = self._build_system_prompt()

        # 安全上限：避免無限循環（100 輪足夠大）
        MAX_SAFE_TURNS = 100
        while self.turn_count < MAX_SAFE_TURNS:
            # 檢查是否被取消
            if self._cancelled.is_set():
                await self._finalize_progress()
                return "🛑 任務已由使用者取消"

            # 檢查是否被暫停（等待恢復）
            await self._wait_if_paused()

            self.turn_count += 1

            # 進度更新：記錄到緩衝區
            await self._add_progress(f"🔄 第 {self.turn_count} 輪：思考中...")

            # 呼叫 API
            response = await self.client.create_message(
                messages=self.history,
                system=system_prompt,
                tools=TOOLS,
            )

            # 處理回應
            content = response.get("content", [])
            tool_uses = [c for c in content if c.get("type") == "tool_use"]
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]

            # 顯示 AI 的思考/規劃（若有文字且無工具，或工具前的說明）
            if texts:
                thinking = "\n".join(texts).strip()
                if thinking:
                    # 截斷過長文字
                    if len(thinking) > 200:
                        thinking = thinking[:197] + "..."
                    await self._add_progress(f"💭 第 {self.turn_count} 輪：{thinking}")

            # 如果有工具呼叫，執行工具
            if tool_uses:
                # 將 assistant 訊息加入歷史
                self.history.append({"role": "assistant", "content": content})

                # 執行每個工具
                for tool_use in tool_uses:
                    tool_name = tool_use["name"]
                    args = tool_use["input"]
                    # 顯示工具細節
                    detail = self._format_tool_detail(tool_name, args)
                    await self._add_progress(
                        f"🔧 第 {self.turn_count} 輪：執行 {tool_name} {detail}"
                    )
                    result = await self._execute_tool(tool_use)
                    # 將工具結果加入歷史
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
                continue  # 繼續下一輪

            # 純文字回覆：任務完成
            reply = "\n".join(texts).strip()
            if reply:
                # 強制發送剩餘進度
                await self._finalize_progress()
                self._save_history(user_input, reply)
                return reply

            # 沒有工具也沒有文字（不應發生）
            self.history.append({"role": "assistant", "content": content})

        # 超過安全上限
        await self._finalize_progress()
        # 返回特殊標記，讓上層處理繼續按鈕
        return {
            "type": "limit_reached",
            "message": f"⚠️ 已達安全輪數上限（{MAX_SAFE_TURNS}），任務未完成。點擊下方按鈕繼續。",
            "history": self.history,
            "system_prompt": system_prompt,
        }

    async def _execute_tool(self, tool_use: dict) -> str:
        name = tool_use["name"]
        args = tool_use["input"]

        try:
            if name == "read":
                result = await self.tools.read(**args)
            elif name == "write":
                result = await self.tools.write(**args)
            elif name == "edit":
                result = await self.tools.edit(**args)
            elif name == "list":
                result = await self.tools.list(**args)
            elif name == "glob":
                result = await self.tools.glob(**args)
            elif name == "bash":
                result = await self.tools.bash(**args)
            elif name == "task":
                result = await self.tools.task(**args)
            else:
                result = f"❌ 未知工具: {name}"
        except PermissionError as e:
            result = f"❌ 權限拒絕: {e}"
        except FileNotFoundError as e:
            result = f"❌ 檔案不存在: {e}"
        except TimeoutError as e:
            result = f"❌ {e}"
        except Exception as e:
            logger.exception("Tool error")
            result = f"❌ 執行錯誤: {e}"

        return result

    def _format_tool_detail(self, tool_name: str, args: dict) -> str:
        """格式化工具參數用於進度顯示"""
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
            # 截斷過長命令
            if len(cmd) > 80:
                cmd = cmd[:77] + "..."
            return f"💻 {cmd}"

        elif tool_name == "task":
            desc = args.get("description", "")
            if len(desc) > 60:
                desc = desc[:57] + "..."
            return f"🤖 子任務: {desc}"

        return ""

    def _load_history(self):
        """從資料庫載入該用戶的最近對話並轉換為 API messages 格式"""
        try:
            # 獲取最近對話（限制 token 預算）
            history_text = DialogueMemory.get_recent_dialogue(max_tokens=2000)
            if not history_text:
                return

            # 解析對話歷史（格式："用戶: query\nAI: response" 以 "\n\n---\n\n" 分隔）
            sections = history_text.split("\n\n---\n\n")
            for section in sections[-10:]:  # 只取最近 10 輪
                lines = section.strip().split("\n")
                if (
                    len(lines) >= 2
                    and lines[0].startswith("用戶:")
                    and lines[1].startswith("AI:")
                ):
                    user_query = lines[0][3:].strip()  # 移除 "用戶: "
                    ai_response = "\n".join(lines[1:])[3:].strip()  # 移除 "AI: "
                    self.history.append({"role": "user", "content": user_query})
                    self.history.append({"role": "assistant", "content": ai_response})
        except Exception as e:
            logger.warning(f"載入歷史失敗: {e}")

    def _save_history(self, user_input: str, reply: str):
        """儲存對話到記憶系統"""
        try:
            DialogueMemory.add_dialogue(user_input, reply, importance=0.6)
        except Exception as e:
            logger.warning(f"儲存記憶失敗: {e}")

    async def close(self):
        await self.client.close()


# ─── 停止/暫停按鈕 View ──────────────────────────────────────────────────────────────
class StopView(discord.ui.View):
    """帶有停止/暫停按鈕的進度訊息 View"""

    def __init__(self, agent: "ClaudeCodeAgent", timeout: float = 300):
        super().__init__(timeout=timeout)
        self.agent = agent

    @discord.ui.button(
        label="⏸️ 暫停", style=discord.ButtonStyle.danger, custom_id="claude_stop"
    )
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # 只有觸發者能暫停
        if interaction.user.id != self.agent.user_id:
            await interaction.response.send_message(
                "❌ 只有發起者能暫停任務", ephemeral=True
            )
            return

        # 暫停 agent（設置暫停標記，不取消任務）
        self.agent.pause()
        button.disabled = True
        button.label = "⏸️ 已暫停"
        self.clear_items()
        # 添加恢復按鈕
        resume_button = discord.ui.Button(
            label="▶️ 恢復", style=discord.ButtonStyle.success, custom_id="claude_resume"
        )
        resume_button.callback = self._create_resume_callback(interaction)
        self.add_item(resume_button)

        await interaction.response.edit_message(view=self)

    def _create_resume_callback(self, original_interaction: discord.Interaction):
        async def resume_callback(interaction: discord.Interaction):
            if interaction.user.id != self.agent.user_id:
                await interaction.response.send_message(
                    "❌ 只有發起者能恢復任務", ephemeral=True
                )
                return

            # 恢復 agent
            self.agent.resume()
            # 重新添加暫停按鈕
            self.clear_items()
            new_stop_button = discord.ui.Button(
                label="⏸️ 暫停",
                style=discord.ButtonStyle.danger,
                custom_id="claude_stop",
            )
            new_stop_button.callback = self.stop_button
            self.add_item(new_stop_button)

            await interaction.response.edit_message(view=self)

        return resume_callback

    async def on_timeout(self):
        """超時時禁用按鈕"""
        for item in self.children:
            item.disabled = True


# ─── 恢復按鈕 View（獨立使用，用於任務被暫發時）──────────────────────────────────────
class ResumeView(discord.ui.View):
    """任務暫停後的恢復按鈕"""

    def __init__(self, agent: "ClaudeCodeAgent", timeout: float = 300):
        super().__init__(timeout=timeout)
        self.agent = agent

    @discord.ui.button(
        label="▶️ 恢復執行",
        style=discord.ButtonStyle.success,
        custom_id="claude_resume_main",
    )
    async def resume_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # 只有觸發者能恢復
        if interaction.user.id != self.agent.user_id:
            await interaction.response.send_message(
                "❌ 只有發起者能恢復任務", ephemeral=True
            )
            return

        self.agent.resume()
        button.disabled = True
        button.label = "▶️ 恢復中..."
        await interaction.response.edit_message(view=self)

        # 發送新進度訊息並繼續執行
        stop_view = StopView(self.agent)
        progress_msg = await interaction.followup.send("🔄 恢復執行...", view=stop_view)

        async def update_progress(text: str):
            """更新進度訊息（編輯同一條 message，超長時分割發送）"""
            try:
                chunks = self._chunk_text(text, 1900)
                if len(chunks) == 1:
                    await progress_msg.edit(content=chunks[0], view=stop_view)
                else:
                    await progress_msg.edit(content=chunks[0], view=stop_view)
                    for chunk in chunks[1:]:
                        await interaction.followup.send(chunk)
            except (discord.NotFound, discord.HTTPException):
                pass

        # 繼續執行
        reply = await self.agent.run("", progress_callback=update_progress)

        # 處理結果
        if isinstance(reply, dict) and reply.get("type") == "limit_reached":
            continue_view = ContinueView(self.agent, "")
            await progress_msg.edit(content=reply["message"], view=continue_view)
        else:
            stop_view.stop()
            await progress_msg.edit(view=stop_view)
            chunks = self._chunk_text(reply, 1900)
            for chunk in chunks:
                await interaction.followup.send(chunk)

    def _chunk_text(self, text: str, max_len: int) -> list[str]:
        """將長文字分割"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        for i in range(0, len(text), max_len):
            chunks.append(text[i : i + max_len])
        return chunks

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# ─── 繼續按鈕 View ──────────────────────────────────────────────────────────────
class ContinueView(discord.ui.View):
    """輪數上限時的繼續按鈕"""

    def __init__(
        self, agent: "ClaudeCodeAgent", original_prompt: str, timeout: float = 300
    ):
        super().__init__(timeout=timeout)
        self.agent = agent
        self.original_prompt = original_prompt
        self.continued = False

    @discord.ui.button(
        label="▶️ 繼續執行",
        style=discord.ButtonStyle.success,
        custom_id="claude_continue",
    )
    async def continue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # 只有觸發者能繼續
        if interaction.user.id != self.agent.user_id:
            await interaction.response.send_message(
                "❌ 只有發起者能繼續任務", ephemeral=True
            )
            return

        self.continued = True
        button.disabled = True
        button.label = "⏳ 繼續中..."
        await interaction.response.edit_message(view=self)

        # 重置 agent 的輪數計數器，繼續執行
        self.agent.turn_count = 0

        # 發送新進度訊息
        progress_msg = await interaction.followup.send(
            "🔄 繼續執行...", view=StopView(self.agent)
        )

        async def update_progress(text: str):
            """更新進度訊息（編輯同一條 message，超長時分割發送）"""
            try:
                chunks = self._chunk_text(text, 1900)
                if len(chunks) == 1:
                    await progress_msg.edit(
                        content=chunks[0], view=StopView(self.agent)
                    )
                else:
                    # 第一塊編輯原訊息，其餘發送新訊息
                    await progress_msg.edit(
                        content=chunks[0], view=StopView(self.agent)
                    )
                    for chunk in chunks[1:]:
                        await interaction.followup.send(chunk)
            except (discord.NotFound, discord.HTTPException):
                pass

        # 繼續執行（傳入空輸入，讓 agent 從歷史繼續）
        reply = await self.agent.run("", progress_callback=update_progress)

        # 處理結果
        if isinstance(reply, dict) and reply.get("type") == "limit_reached":
            # 再次達到上限，遞迴顯示繼續按鈕
            continue_view = ContinueView(self.agent, self.original_prompt)
            await progress_msg.edit(content=reply["message"], view=continue_view)
        else:
            # 正常完成
            await progress_msg.edit(view=StopView(self.agent))  # 禁用按鈕
            chunks = self._chunk_text(reply, 1900)
            for chunk in chunks:
                await interaction.followup.send(chunk)

    def _chunk_text(self, text: str, max_len: int) -> list[str]:
        """將長文字分割"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        for i in range(0, len(text), max_len):
            chunks.append(text[i : i + max_len])
        return chunks

    async def on_timeout(self):
        """超時時禁用按鈕"""
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# ─── Discord Cog ────────────────────────────────────────────────────────────
class ClaudeCodeCog(commands.Cog):
    """Claude Code CLI Discord 整合"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # key: (user_id, channel_id) -> agent
        self.active_agents: dict[tuple, ClaudeCodeAgent] = {}
        logger.info("✅ ClaudeCodeCog 初始化完成")

    def _check_permission_interaction(self, interaction: discord.Interaction) -> bool:
        """檢查互動權限：僅限 Discord 管理員"""
        if interaction.user.id == ADMIN_USER_ID:
            return True
        admin_role = os.getenv("ADMIN_ROLE_NAME", "管理員")
        return any(r.name == admin_role for r in getattr(interaction.user, "roles", []))

    @app_commands.command(
        name="cc",
        description="Claude Code CLI - AI 程式開發助手（管理員限定）",
    )
    @app_commands.describe(
        prompt="任務描述，例如：幫我新增一個 /ping 指令到 bot.py",
        continue_conv="是否繼續上一輪對話（預設新對話）",
    )
    async def cc(
        self, interaction: discord.Interaction, prompt: str, continue_conv: bool = False
    ):
        if not self._check_permission_interaction(interaction):
            await interaction.response.send_message(
                "❌ 此指令僅限 Discord 管理員使用。", ephemeral=True
            )
            return

        if not NVIDIA_API_KEY:
            await interaction.response.send_message(
                "❌ NVIDIA_API_KEY 未在 .env 中設定，無法使用此功能。", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            # 使用 channel_id 作為 context key
            agent_key = (interaction.user.id, interaction.channel_id)

            # 獲取或建立 agent
            if continue_conv and agent_key in self.active_agents:
                agent = self.active_agents[agent_key]
            else:
                agent = ClaudeCodeAgent(interaction.user.id, interaction.channel_id)
                self.active_agents[agent_key] = agent

            # 建立停止按鈕 View
            stop_view = StopView(agent)

            # 發送初始進度訊息（帶停止按鈕）
            initial_msg = await interaction.followup.send(
                "🔄 開始執行...", view=stop_view
            )

            async def update_progress(text: str):
                """更新進度訊息（編輯同一條 message，超長時分割發送）"""
                try:
                    chunks = self._chunk_text(text, 1900)
                    if len(chunks) == 1:
                        await initial_msg.edit(content=chunks[0], view=stop_view)
                    else:
                        # 第一塊編輯原訊息，其餘發送新訊息
                        await initial_msg.edit(content=chunks[0], view=stop_view)
                        for chunk in chunks[1:]:
                            await interaction.followup.send(chunk)
                except (discord.NotFound, discord.HTTPException):
                    pass

            # 執行
            reply = await agent.run(prompt, progress_callback=update_progress)

            # 檢查是否達到輪數上限
            if isinstance(reply, dict) and reply.get("type") == "limit_reached":
                # 顯示繼續按鈕
                continue_view = ContinueView(agent, prompt)
                await initial_msg.edit(content=reply["message"], view=continue_view)
            else:
                # 正常完成
                stop_view.stop()  # 禁用按鈕
                await initial_msg.edit(view=stop_view)

                chunks = self._chunk_text(reply, 1900)
                for chunk in chunks:
                    await interaction.followup.send(chunk)

        except Exception as e:
            logger.exception("Claude Code 執行錯誤")
            await interaction.followup.send(f"❌ 執行錯誤: {e}")

    @app_commands.command(
        name="cc_status",
        description="查看 Claude Code Agent 狀態",
    )
    async def cc_status(self, interaction: discord.Interaction):
        if not self._check_permission_interaction(interaction):
            await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
            return

        active = len(self.active_agents)
        agent_key = (interaction.user.id, interaction.channel_id)
        has_active = agent_key in self.active_agents

        embed = discord.Embed(
            title="🤖 Claude Code 狀態 (NVIDIA NIM)",
            color=discord.Color.blue(),
        )
        embed.add_field(name="活躍 Agent 總數", value=str(active), inline=True)
        embed.add_field(
            name="當前對話", value="✅ 活躍" if has_active else "💤 無", inline=True
        )
        embed.add_field(name="Channel ID", value=str(interaction.channel_id), inline=False)
        embed.add_field(
            name="模型 (自動選擇)",
            value=f"Ultra: {MODEL_ULTRA}\nSuper: {MODEL_SUPER}",
            inline=False,
        )
        embed.add_field(name="工作目錄", value=str(WORK_DIR), inline=False)
        embed.add_field(name="最大輪數", value=str(MAX_TURNS), inline=True)
        embed.add_field(name="最大輸出", value=f"{MAX_TOKENS} tokens", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="cc_clear",
        description="清除當前對話歷史",
    )
    async def cc_clear(self, interaction: discord.Interaction):
        if not self._check_permission_interaction(interaction):
            await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
            return

        agent_key = (interaction.user.id, interaction.channel_id)

        if agent_key in self.active_agents:
            await self.active_agents[agent_key].close()
            del self.active_agents[agent_key]
            await interaction.response.send_message("✅ 已清除對話歷史", ephemeral=True)
        else:
            await interaction.response.send_message("無活躍對話", ephemeral=True)

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> list[str]:
        """將長文字分割"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        for i in range(0, len(text), max_len):
            chunks.append(text[i : i + max_len])
        return chunks

    
    async def cog_unload(self):
        """卸載時關閉所有 agent"""
        for agent in self.active_agents.values():
            await agent.close()
        self.active_agents.clear()


async def setup(bot: commands.Bot):
    await bot.add_cog(ClaudeCodeCog(bot))
    # 初始化記憶系統
    try:
        initialize_memory_system()
    except Exception as e:
        logger.warning(f"記憶系統初始化失敗: {e}")
