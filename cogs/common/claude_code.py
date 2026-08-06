"""
KK園區 Claude Code CLI 移植版
====================================================================
完整移植 Claude Code CLI 核心功能到 Discord Bot，僅限：
- Discord 管理員（.env 中 ADMIN_USER_ID 設定）
- 指定頻道：1509078418312921128

架構：
- 使用 Anthropic Messages API (tool_use) 實現 agentic loop
- 內建 7 個核心工具：read, write, edit, list, glob, bash, task
- 路徑安全防護：防止目錄遍歷、禁止敏感路徑
- 記憶持久化：對話歷史儲存到 ai_memory.db
"""

import os
import json
import asyncio
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import aiohttp

from shared.db.ai_memory import (
    DialogueMemory,
    PersonalityMemory,
    KnowledgeBase,
    build_memory_context,
    initialize_memory_system,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 環境變數與權限設定 ─────────────────────────────────────────────────────
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
ALLOWED_CHANNEL_ID = 1509078418312921128

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.warning("⚠️ ANTHROPIC_API_KEY 未設定，Claude Code 功能將無法使用")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))
MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "20"))

# 工作目錄（專案根目錄）
WORK_DIR = Path(os.getenv("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")).resolve()

# 禁止存取的敏感路徑
BLOCKED_PATHS = {
    "/etc", "/root", "/home", "/var", "/usr", "/bin", "/sbin",
    "/lib", "/lib64", "/boot", "/sys", "/proc", "/dev",
    "/run", "/tmp", "/srv", "/opt", "/mnt", "/media",
}
BLOCKED_FILES = {".env", ".ssh", "id_rsa", "id_ed25519", "authorized_keys", "config"}
BLOCKED_PREFIXES = [".git/", ".github/", "__pycache__/", "venv/", ".venv/", "node_modules/"]

# ─── 系統提示詞 ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是 KK園區的 Claude Code 代理，一個專業的程式開發助手。
工作目錄：{work_dir}

核心能力：
- 讀寫編輯檔案、執行命令、搜尋代碼
- 遵循專案編碼規範（參考 knowledge/_wiki/concepts/coding-rules-and-paths.md）
- 使用專案現有模組而非重造輪子（ponytail 原則：YAGNI → reuse → stdlib → native → deps）

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
                "old_string": {"type": "string", "description": "要替換的原始字串（需唯一匹配）"},
                "new_string": {"type": "string", "description": "新字串"},
                "replace_all": {"type": "boolean", "description": "是否替換所有匹配", "default": False},
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
                "timeout": {"type": "integer", "description": "超時秒數", "default": 30},
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
            lines = lines[offset:offset + limit]
        result = "\n".join(lines)
        return f"=== {p} ===\n{result}"

    async def write(self, path: str, content: str) -> str:
        p = validate_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ 已寫入: {p} ({len(content)} 字元)"

    async def edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        p = validate_path(path, must_exist=True)
        content = p.read_text(encoding="utf-8")

        if old_string not in content:
            raise ValueError("old_string 未在檔案中找到")

        if not replace_all and content.count(old_string) > 1:
            raise ValueError("old_string 匹配多處，請設定 replace_all=true 或提供更精確的字串")

        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
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
        dangerous = ["rm -rf /", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/",
                     "chmod 777", "chown root", "passwd", "userdel", "groupdel"]
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
        except asyncio.TimeoutError:
            raise TimeoutError(f"指令超時 ({timeout}s)")

    async def task(self, description: str, prompt: str) -> str:
        # 子任務：建立新的 agent 實例執行（簡化版：直接返回說明）
        return f"[子任務] {description}\n提示: {prompt}\n\n(子任務功能簡化版：請在主對話中繼續操作)"


# ─── Anthropic API 客戶端 ───────────────────────────────────────────────────
class AnthropicClient:
    """Anthropic Messages API 客戶端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            )
        return self.session

    async def create_message(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int = MAX_TOKENS,
    ) -> Dict:
        session = await self._get_session()
        payload = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "tools": tools,
            "tool_choice": {"type": "auto"},
        }

        async with session.post(ANTHROPIC_API_URL, json=payload) as resp:
            if resp.status == 429:
                raise Exception("Rate limited")
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"API Error {resp.status}: {text[:500]}")
            return await resp.json()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# ─── Agent 核心邏輯 ─────────────────────────────────────────────────────────
class ClaudeCodeAgent:
    """Claude Code Agent - Agentic Loop 實作"""

    def __init__(self, user_id: int, channel_id: int):
        self.user_id = user_id
        self.channel_id = channel_id
        self.client = AnthropicClient(ANTHROPIC_API_KEY)
        self.tools = ToolExecutor(WORK_DIR)
        self.history: List[Dict] = []
        self.turn_count = 0

    def _build_system_prompt(self) -> str:
        # 獲取長期記憶上下文
        memory = build_memory_context()
        context = SYSTEM_PROMPT.format(work_dir=WORK_DIR)
        if memory["system_instructions"]:
            context += "\n\n" + memory["system_instructions"]
        if memory["knowledge_context"]:
            context += "\n\n=== 知識庫 ===\n" + memory["knowledge_context"]
        return context

    async def run(self, user_input: str) -> str:
        """主入口：執行 agentic loop"""
        if not ANTHROPIC_API_KEY:
            return "❌ ANTHROPIC_API_KEY 未設定，無法使用 Claude Code 功能。請在 .env 中設定。"

        # 載入該用戶的對話歷史
        self._load_history()

        # 加入用戶輸入
        self.history.append({"role": "user", "content": user_input})

        system_prompt = self._build_system_prompt()

        for turn in range(MAX_TURNS):
            self.turn_count = turn + 1

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

            # 如果有工具呼叫，執行工具
            if tool_uses:
                # 將 assistant 訊息加入歷史
                self.history.append({"role": "assistant", "content": content})

                # 執行每個工具（通常一次只有一個）
                for tool_use in tool_uses:
                    result = await self._execute_tool(tool_use)
                    # 將工具結果加入歷史
                    self.history.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use["id"],
                                "content": result,
                            }
                        ],
                    })
                continue  # 繼續下一輪

            # 純文字回覆：任務完成
            reply = "\n".join(texts).strip()
            if reply:
                self._save_history(user_input, reply)
                return reply

            # 沒有工具也沒有文字（不應發生）
            self.history.append({"role": "assistant", "content": content})

        return f"⚠️ 已達最大輪數（{MAX_TURNS}），任務未完成。請繼續指示。"

    async def _execute_tool(self, tool_use: Dict) -> str:
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
                if len(lines) >= 2 and lines[0].startswith("用戶:") and lines[1].startswith("AI:"):
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


# ─── Discord Cog ────────────────────────────────────────────────────────────
class ClaudeCodeCog(commands.Cog):
    """Claude Code CLI Discord 整合"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_agents: Dict[int, ClaudeCodeAgent] = {}
        logger.info("✅ ClaudeCodeCog 初始化完成")

    def _check_permission(self, interaction: discord.Interaction) -> bool:
        """檢查權限：管理員且在指定頻道"""
        # 頻道檢查
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            return False
        # 管理員檢查
        if interaction.user.id == ADMIN_USER_ID:
            return True
        # 也可檢查角色（可選）
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
    async def cc(self, interaction: discord.Interaction, prompt: str, continue_conv: bool = False):
        if not self._check_permission(interaction):
            await interaction.response.send_message(
                "❌ 此指令僅限 Discord 管理員在指定頻道使用。", ephemeral=True
            )
            return

        if not ANTHROPIC_API_KEY:
            await interaction.response.send_message(
                "❌ ANTHROPIC_API_KEY 未在 .env 中設定，無法使用此功能。", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            # 獲取或建立 agent
            user_id = interaction.user.id
            if continue_conv and user_id in self.active_agents:
                agent = self.active_agents[user_id]
            else:
                agent = ClaudeCodeAgent(user_id, interaction.channel_id)
                self.active_agents[user_id] = agent

            # 執行
            reply = await agent.run(prompt)

            # 分段發送（Discord 限制 2000 字元）
            for chunk in self._chunk_text(reply, 1900):
                await interaction.followup.send(chunk)

        except Exception as e:
            logger.exception("Claude Code 執行錯誤")
            await interaction.followup.send(f"❌ 執行錯誤: {e}")

    @app_commands.command(
        name="cc_status",
        description="查看 Claude Code Agent 狀態",
    )
    async def cc_status(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
            return

        active = len(self.active_agents)
        embed = discord.Embed(
            title="🤖 Claude Code 狀態",
            color=discord.Color.blue(),
        )
        embed.add_field(name="活躍 Agent", value=str(active), inline=True)
        embed.add_field(name="模型", value=MODEL, inline=True)
        embed.add_field(name="工作目錄", value=str(WORK_DIR), inline=False)
        embed.add_field(name="最大輪數", value=str(MAX_TURNS), inline=True)
        embed.add_field(name="最大輸出", value=f"{MAX_TOKENS} tokens", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="cc_clear",
        description="清除當前對話歷史",
    )
    async def cc_clear(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
            return

        if interaction.user.id in self.active_agents:
            await self.active_agents[interaction.user.id].close()
            del self.active_agents[interaction.user.id]
            await interaction.response.send_message("✅ 已清除對話歷史", ephemeral=True)
        else:
            await interaction.response.send_message("無活躍對話", ephemeral=True)

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> List[str]:
        """將長文字分割"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        for i in range(0, len(text), max_len):
            chunks.append(text[i:i + max_len])
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
    except Exception:
        pass