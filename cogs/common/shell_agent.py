"""KK園區 Shell Agent（ADK 架構 — Gemini Function Calling + Groq 備用）
=======================================================================

Agentic Loop（官方 Sequential Workflow）：
    Think（LLM 決定下一條 Shell 指令）
    → Act（Discord Button 確認 → run_terminal 執行）
    → Observe（結果注入對話）
    → loop until 「任務完成」or 超出 MAX_STEPS

🔒 安全設計：
    - /shellagent 僅限 ADMIN_ROLE_NAME 或 LEADER_DISCORD_ID
    - 每條 Shell 指令都必須先在 Discord ✅ 確認後才執行
    - 管理員可隨時 ❌ 中止
    - 最多 MAX_STEPS 步，防止無限迴圈
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
import logging
from typing import Optional, List, Dict

from dotenv import load_dotenv
from shared.utils.view_registry import PersistentViewBase

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 設定 ────────────────────────────────────────────────────────────────────
LEADER_DISCORD_ID: int = int(os.getenv("LEADER_DISCORD_ID", "0"))
ADMIN_ROLE_NAME:   str = os.getenv("ADMIN_ROLE_NAME", "管理員")
MAX_STEPS:          int = 10
CONFIRM_TIMEOUT:    int = 60  # Discord Button 等待秒數

_GEMINI_KEY    = os.getenv("AI_API_KEY")
_GEMINI_KEY_BK = os.getenv("AI_API_KEY_BACKUP")
_GEMINI_MODEL  = os.getenv("AI_API_MODEL", "gemini-2.0-flash")
_GROQ_KEY      = os.getenv("GROQ_API_KEY")
_GROQ_URL      = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
_GROQ_MODEL    = os.getenv("GROQ_API_MODEL", "llama-3.3-70b-versatile")

_SHELL_SYSTEM = """\
你是 KK園區的 Shell Agent，一位專業的 Linux 伺服器工程師助手。
目標：逐步執行 Shell 指令達成管理員交辦的任務。

規則：
1. 每次只提議「一條」Shell 指令（透過 run_terminal 工具呼叫）
2. 禁止使用 rm -rf /、shutdown、reboot 等破壞性指令
3. 根據前一步的執行結果決定下一步
4. 目標完成後，以純文字「任務完成：<摘要>」回覆，不再呼叫工具
5. 無法完成時說明原因並停止
"""


# ══════════════════════════════════════════════════════════════════════════════
# 1. ConfirmCommandView — Discord 確認按鈕
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmCommandView(PersistentViewBase):
    """顯示「✅ 執行」與「❌ 取消任務」的確認介面。"""

    def __init__(self, command: str):
        super().__init__()
        self.command:   str           = command
        self.confirmed: Optional[bool] = None  # True / False / None（超時）

        self.add_button(label="✅ 執行",       callback=self._confirm, style="success")
        self.add_button(label="❌ 取消任務",   callback=self._cancel,  style="danger")

    @staticmethod
    def _check_perm(interaction: discord.Interaction) -> bool:
        if interaction.user.id == LEADER_DISCORD_ID:
            return True
        return any(r.name == ADMIN_ROLE_NAME for r in getattr(interaction.user, "roles", []))

    async def _confirm(self, interaction: discord.Interaction):
        if not self._check_perm(interaction):
            await interaction.response.send_message("❌ 你沒有權限確認指令。", ephemeral=True)
            return
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🟢 已核准執行:\n```bash\n{self.command}\n```",
            view=self,
        )
        self.stop()

    async def _cancel(self, interaction: discord.Interaction):
        if not self._check_perm(interaction):
            await interaction.response.send_message("❌ 你沒有權限中止任務。", ephemeral=True)
            return
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🔴 任務已由 {interaction.user.mention} 中止。",
            view=self,
        )
        self.stop()


# ══════════════════════════════════════════════════════════════════════════════
# 2. ShellAgentRunner — ADK Sequential Workflow
# ══════════════════════════════════════════════════════════════════════════════

class ShellAgentRunner:
    """ADK 風格 Shell Agent 執行器。

    Agentic Loop：
      Think（LLM 決定指令）
      → Act（確認 + 執行）
      → Observe（結果注入對話）
      → repeat
    """

    def __init__(self, tools_module):
        self._tools      = tools_module
        self._tools_spec = self._build_shell_spec(tools_module)

    @staticmethod
    def _build_shell_spec(tools_module) -> List[Dict]:
        """只取 run_terminal 的工具規格，給 Gemini 使用。"""
        full  = tools_module.get_gemini_tools_spec()
        decls = [
            d for group in full
            for d in group.get("functionDeclarations", [])
            if d["name"] == "run_terminal"
        ]
        return [{"functionDeclarations": decls}] if decls else []

    async def run(self, goal: str, channel: discord.TextChannel, caller_id: int):
        """主入口：執行完整 Agentic Loop。"""
        conversation: List[Dict] = [{
            "role": "user",
            "parts": [{"text": f"目標：{goal}\n請開始逐步達成它。"}],
        }]

        for step in range(1, MAX_STEPS + 1):
            await channel.send(f"🧠 **步驟 {step}/{MAX_STEPS}** — 思考中…")

            # ── Think ────────────────────────────────────────────────────
            fc, text_reply = await self._think(conversation)

            # 純文字 → 任務結束
            if text_reply is not None:
                color = discord.Color.green() if ("完成" in text_reply) else discord.Color.orange()
                embed = discord.Embed(
                    title="🏁 Shell Agent 任務結束",
                    description=text_reply,
                    color=color,
                )
                embed.set_footer(text=f"共執行 {step - 1} 步")
                await channel.send(embed=embed)
                return

            if fc is None:
                await channel.send("❌ LLM 無回應，任務中止。")
                return

            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            # ── Act（非 run_terminal：直接執行，無需確認）────────────────
            if tool_name != "run_terminal":
                result = self._tools.dispatch_tool(tool_name, tool_args, caller_id=caller_id)
                conversation.append({"role": "model", "parts": [{"functionCall": fc}]})
                conversation.append({"role": "user", "parts": [{"functionResponse": {
                    "name": tool_name, "response": {"result": str(result)},
                }}]})
                continue

            # ── Act（run_terminal：Discord 確認後執行）────────────────────
            shell_cmd   = tool_args.get("command", "").strip()
            timeout_sec = int(tool_args.get("timeout_sec", 30))
            if not shell_cmd:
                await channel.send("⚠️ 空白指令，跳過。")
                continue

            confirm_embed = discord.Embed(
                title=f"🔐 步驟 {step} — 確認執行 Shell 指令",
                description=f"```bash\n{shell_cmd}\n```",
                color=discord.Color.yellow(),
            )
            confirm_embed.add_field(name="⏱️ 逾時設定", value=f"{timeout_sec}s", inline=True)
            confirm_embed.set_footer(text=f"等待確認（{CONFIRM_TIMEOUT}s 後自動取消）")

            view = ConfirmCommandView(command=shell_cmd)
            await channel.send(embed=confirm_embed, view=view)

            try:
                await asyncio.wait_for(view.wait(), timeout=CONFIRM_TIMEOUT)
            except asyncio.TimeoutError:
                await channel.send(f"⏰ 確認超時（{CONFIRM_TIMEOUT}s），任務中止。")
                return

            if view.confirmed is False:
                await channel.send("🔴 任務已被管理員中止。")
                return

            # ── Observe ──────────────────────────────────────────────────
            exec_msg = await channel.send(f"⚙️ 執行中：`{shell_cmd}`…")
            tool_result = self._tools.dispatch_tool(
                "run_terminal",
                {"command": shell_cmd, "timeout_sec": timeout_sec},
                caller_id=caller_id,
            )

            result_embed = discord.Embed(
                title=f"📋 步驟 {step} 執行結果",
                description=f"```\n{str(tool_result)[:1500]}\n```",
                color=discord.Color.blue(),
            )
            await exec_msg.edit(content="", embed=result_embed)

            # 注入官方 Function Calling 格式（model 呼叫 + user 回應）
            conversation.append({"role": "model", "parts": [{"functionCall": fc}]})
            conversation.append({"role": "user", "parts": [{"functionResponse": {
                "name": "run_terminal",
                "response": {"result": str(tool_result)},
            }}]})

        await channel.send(f"⚠️ 已達最大步驟數（{MAX_STEPS} 步），任務終止。")

    async def _think(self, conversation: List[Dict]):
        """呼叫 LLM，回傳 (functionCall | None, text | None)。

        優先 Gemini（主 Key → 備用 Key）；全部失敗時降級 Groq（純文字解析）。
        """
        # ── Gemini ───────────────────────────────────────────────────────
        for key in filter(None, [_GEMINI_KEY, _GEMINI_KEY_BK]):
            candidate = await self._gemini_call(key, conversation)
            if candidate is None:
                continue
            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                continue
            if "text" in parts[0]:
                return None, parts[0]["text"].strip()
            if "functionCall" in parts[0]:
                return parts[0]["functionCall"], None

        # ── Groq 降級（無工具，解析純文字指令）──────────────────────────
        if not _GROQ_KEY:
            return None, None

        groq_msgs = [
            {
                "role": "system",
                "content": (
                    _SHELL_SYSTEM
                    + "\n重要：回覆必須以 CMD:<shell指令> 或 DONE:<摘要> 開頭"
                ),
            }
        ]
        for turn in conversation:
            role = "assistant" if turn["role"] == "model" else turn["role"]
            parts_text = " ".join(
                p.get("text")
                or str(p.get("functionCall", p.get("functionResponse", "")))
                for p in turn["parts"]
            )
            groq_msgs.append({"role": role, "content": parts_text})

        try:
            payload = {
                "model": _GROQ_MODEL,
                "messages": groq_msgs,
                "temperature": 0.2,
                "max_tokens": 200,
            }
            headers = {
                "Authorization": f"Bearer {_GROQ_KEY}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(_GROQ_URL, json=payload, headers=headers) as r:
                    if r.status != 200:
                        logger.warning(f"⚠️ Groq Shell HTTP {r.status}")
                        return None, None
                    data    = await r.json()
                    reply   = data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"⚠️ Groq Shell 錯誤: {e}")
            return None, None

        if reply.startswith("CMD:"):
            cmd = reply[4:].strip()
            return {"name": "run_terminal", "args": {"command": cmd, "timeout_sec": 30}}, None
        if reply.startswith("DONE:"):
            return None, reply[5:].strip()
        return None, reply  # 直接當純文字處理

    async def _gemini_call(self, api_key: str, conversation: List[Dict]) -> Optional[Dict]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{_GEMINI_MODEL}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": _SHELL_SYSTEM}]},
            "contents": conversation,
            "tools": self._tools_spec,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                ) as r:
                    if r.status != 200:
                        logger.warning(f"⚠️ Gemini Shell HTTP {r.status}")
                        return None
                    data  = await r.json()
                    cands = data.get("candidates", [])
                    return cands[0] if cands else None
        except Exception as e:
            logger.warning(f"⚠️ Gemini Shell 錯誤: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
# 3. ShellAgent — Discord Cog
# ══════════════════════════════════════════════════════════════════════════════

class ShellAgent(commands.Cog):
    """Shell Agent：讓 AI 在管理員監督下自主操作伺服器。"""

    def __init__(self, bot: commands.Bot):
        self.bot     = bot
        self._runner: Optional[ShellAgentRunner] = None
        try:
            import agent_tools as _at
            self._runner = ShellAgentRunner(_at)
            logger.info("✅ ShellAgent（ADK 架構）初始化完成")
        except ImportError:
            logger.warning("⚠️ agent_tools 未載入，ShellAgent 無工具支援")

    def _has_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == LEADER_DISCORD_ID:
            return True
        return any(r.name == ADMIN_ROLE_NAME for r in getattr(interaction.user, "roles", []))

    @app_commands.command(
        name="shellagent",
        description="啟動 AI Shell Agent（管理員限定）",
    )
    @app_commands.describe(goal="任務目標，例如：查看 bot.service 最近 20 筆錯誤日誌")
    async def shellagent(self, interaction: discord.Interaction, goal: str):
        if not self._has_permission(interaction):
            await interaction.response.send_message("❌ 此指令僅限管理員使用。", ephemeral=True)
            return
        if not self._runner:
            await interaction.response.send_message(
                "❌ agent_tools 未載入，無法啟動。", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"🤖 **Shell Agent 啟動**\n"
            f"📌 目標：{goal}\n"
            f"⚙️ 最多 {MAX_STEPS} 步，每步需管理員確認。"
        )
        await self._runner.run(goal, interaction.channel, interaction.user.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShellAgent(bot))
