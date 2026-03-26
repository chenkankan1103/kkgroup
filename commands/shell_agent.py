"""
KK園區 Shell Agent（Agentic Loop + Discord 安全閥）
=====================================================

讓 Gemini 扮演「自主 Shell 工程師」：
    1. 接收一個自然語言「目標」
    2. 進入 Agentic Loop：
           AI 思考 → 提議 Shell 指令 → Discord Button 確認 → 執行 → 回饋結果 → 再思考
    3. 直到 AI 回報「目標已達成」或超出最大步驟數

🔒 安全設計：
    - /shellagent 指令僅限擁有 ADMIN_ROLE_NAME 身分組的使用者
    - 每一條 Shell 指令都必須先在 Discord 上通過 ✅ 確認  才執行
    - 管理員可隨時按 ❌ 中止整個 Agent 任務
    - 最多執行 MAX_STEPS 步，防止無限迴圈

📌 使用方式：
    /shellagent goal:查看 Bot 的記憶體使用狀況並報告摘要
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import json
import os
import logging
from typing import Optional, List, Dict
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ==================== 設定 ====================

AI_API_KEY   = os.getenv("AI_API_KEY")
AI_API_URL   = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gemini-2.0-flash")

LEADER_DISCORD_ID: int = int(os.getenv("LEADER_DISCORD_ID", "0"))
ADMIN_ROLE_NAME: str   = os.getenv("ADMIN_ROLE_NAME", "管理員")  # 可執行 /shellagent 的身分組

MAX_STEPS      = 10    # 最多執行幾個 Shell 步驟
CONFIRM_TIMEOUT = 60   # Discord Button 等待管理員確認的秒數

SHELL_AGENT_SYSTEM_PROMPT = """\
你是 KK園區的 Shell Agent，一個專業的 Linux 伺服器工程師助手。
你的任務是達成管理員給你的目標，方法是一步一步執行 Shell 指令。

規則：
1. 每次只能提議「一條」Shell 指令
2. 指令必須安全、非破壞性（禁止使用 rm -rf /、shutdown、reboot 等）
3. 當目標已達成時，請用普通文字回覆「任務完成：<摘要>」，不要再呼叫任何工具
4. 如果任務無法完成，請說明原因並停止

你只能使用 run_terminal 工具來操作伺服器。
每次根據前面指令的輸出結果，再決定下一步。
"""


# ==================== Discord UI 元件 ====================

class ConfirmCommandView(discord.ui.View):
    """
    顯示「✅ 執行」與「❌ 取消」按鈕的確認介面

    管理員點 ✅ → confirmed = True
    管理員點 ❌ → confirmed = False（同時中止整個任務）
    """

    def __init__(self, command: str, step: int, total: int, requester_id: int):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.command      = command
        self.confirmed    = None   # True / False / None（超時）
        self.requester_id = requester_id

    def _check_permission(self, interaction: discord.Interaction) -> bool:
        """只允許有 ADMIN_ROLE_NAME 或是 LEADER_DISCORD_ID 的用戶確認"""
        if interaction.user.id == LEADER_DISCORD_ID:
            return True
        return any(r.name == ADMIN_ROLE_NAME for r in getattr(interaction.user, 'roles', []))

    @discord.ui.button(label="✅ 執行", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 你沒有權限確認 Shell 指令。", ephemeral=True)
            return
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🟢 已核准執行:\n```bash\n{self.command}\n```",
            view=self
        )
        self.stop()

    @discord.ui.button(label="❌ 取消任務", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 你沒有權限中止任務。", ephemeral=True)
            return
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🔴 任務已由 {interaction.user.mention} 中止。",
            view=self
        )
        self.stop()


# ==================== Gemini 呼叫（帶工具清單）====================

async def call_gemini_with_tools(
    conversation: List[Dict],
    tools_spec: List[Dict]
) -> Optional[Dict]:
    """
    送出完整對話歷史 + 工具清單到 Gemini，回傳原始 candidate 字典。

    Args:
        conversation: 多輪對話歷史（Gemini contents 格式）
        tools_spec:   Gemini functionDeclarations 清單

    Returns:
        dict 或 None（失敗時）
    """
    if not AI_API_KEY or not AI_API_URL:
        logger.error("Gemini API 未設定")
        return None

    # 過濾出 run_terminal 工具（Shell Agent 專用）
    shell_tools = [{
        "functionDeclarations": [
            decl for group in tools_spec
            for decl in group.get("functionDeclarations", [])
            if decl["name"] == "run_terminal"
        ]
    }]

    payload = {
        "contents": conversation,
        "tools": shell_tools,
        "generationConfig": {
            "temperature": 0.2,      # 低溫=較確定性輸出，適合工程任務
            "maxOutputTokens": 400
        },
        "systemInstruction": {
            "parts": [{"text": SHELL_AGENT_SYSTEM_PROMPT}]
        }
    }

    url = f"{AI_API_URL}?key={AI_API_KEY}"
    headers = {"Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Gemini API 錯誤 {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return None
                return candidates[0]
    except asyncio.TimeoutError:
        logger.error("Gemini API 超時")
        return None
    except Exception as e:
        logger.error(f"Gemini API 錯誤: {e}")
        return None


# ==================== Shell Agent Cog ====================

class ShellAgent(commands.Cog):
    """
    Shell Agent：讓 Gemini 在 Discord 管理員監督下自主操作伺服器。
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 嘗試載入工具模組
        try:
            import agent_tools as _at
            self._tools = _at
            self._tools_spec = _at.get_gemini_tools_spec()
        except ImportError:
            self._tools = None
            self._tools_spec = []
            logger.warning("agent_tools 不可用，Shell Agent 工具呼叫無法使用")

    def _has_permission(self, interaction: discord.Interaction) -> bool:
        """確認發令者有管理員角色或是 LEADER_DISCORD_ID"""
        if interaction.user.id == LEADER_DISCORD_ID:
            return True
        return any(r.name == ADMIN_ROLE_NAME for r in getattr(interaction.user, 'roles', []))

    @app_commands.command(
        name="shellagent",
        description="啟動 AI Shell Agent（管理員限定）：讓 Gemini 幫你自動達成伺服器任務"
    )
    @app_commands.describe(goal="告訴 AI 你的目標，例如：查看 bot.service 最近 20 筆錯誤日誌")
    async def shellagent(self, interaction: discord.Interaction, goal: str):
        """
        /shellagent goal:<自然語言目標>

        Gemini 會分析目標、逐步提議 Shell 指令，
        每步都需要你在 Discord 上按 ✅ 才能真正執行。
        """
        # 權限檢查
        if not self._has_permission(interaction):
            await interaction.response.send_message(
                "❌ 此指令僅限管理員使用。", ephemeral=True
            )
            return

        if not self._tools:
            await interaction.response.send_message(
                "❌ agent_tools 模組未載入，無法啟動 Shell Agent。", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"🤖 **Shell Agent 啟動**\n"
            f"📌 目標：{goal}\n"
            f"⚙️ 最多執行 {MAX_STEPS} 步，每步都需要你確認。",
            ephemeral=False
        )

        channel      = interaction.channel
        caller_id    = interaction.user.id

        # 初始化對話歷史
        conversation: List[Dict] = [
            {
                "role": "user",
                "parts": [{"text": f"目標：{goal}\n\n請開始逐步達成它。"}]
            }
        ]

        completed = False

        for step in range(1, MAX_STEPS + 1):
            # ── Step 1: 問 Gemini 下一步 ────────────────────────────────
            await channel.send(f"🧠 **步驟 {step}/{MAX_STEPS}** — 思考中…")

            candidate = await call_gemini_with_tools(conversation, self._tools_spec)

            if candidate is None:
                await channel.send("❌ Gemini API 無回應，任務中止。")
                break

            parts = candidate.get("content", {}).get("parts", [])

            if not parts:
                await channel.send("❌ Gemini 回傳空內容，任務中止。")
                break

            # ── Step 2: 判斷回傳類型 ────────────────────────────────────
            first_part = parts[0]

            # 2a. 純文字回覆 → 任務完成或無法完成
            if "text" in first_part:
                text_reply = first_part["text"].strip()
                if "任務完成" in text_reply or "已完成" in text_reply or "無法完成" in text_reply:
                    embed = discord.Embed(
                        title="🏁 Shell Agent 任務結束",
                        description=text_reply,
                        color=discord.Color.green() if "完成" in text_reply else discord.Color.orange()
                    )
                    embed.set_footer(text=f"共執行 {step - 1} 步")
                    await channel.send(embed=embed)
                    completed = True
                    break
                else:
                    # 只是普通文字，顯示給管理員看
                    await channel.send(f"💬 Gemini：{text_reply[:500]}")
                    conversation.append({
                        "role": "model",
                        "parts": [{"text": text_reply}]
                    })
                    continue

            # 2b. Function Call → 提議執行 Shell 指令
            if "functionCall" not in first_part:
                await channel.send(f"⚠️ 無法解析 Gemini 回應，跳過此步。")
                continue

            fc = first_part["functionCall"]
            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            if tool_name != "run_terminal":
                # 非 Shell 工具，直接執行（使用既有分發器）
                result = self._tools.dispatch_tool(tool_name, tool_args, caller_id=caller_id)
                conversation.append({"role": "model", "parts": [{"functionCall": fc}]})
                conversation.append({
                    "role": "user",
                    "parts": [{"functionResponse": {
                        "name": tool_name,
                        "response": {"result": str(result)}
                    }}]
                })
                continue

            # 2c. run_terminal → 顯示安全確認介面 ─────────────────────
            shell_cmd = tool_args.get("command", "").strip()
            timeout_sec = tool_args.get("timeout_sec", 30)

            if not shell_cmd:
                await channel.send("⚠️ Gemini 提供了空白指令，跳過。")
                continue

            # 安全提示 Embed
            confirm_embed = discord.Embed(
                title=f"🔐 步驟 {step} — 確認執行 Shell 指令",
                description=f"```bash\n{shell_cmd}\n```",
                color=discord.Color.yellow()
            )
            confirm_embed.add_field(
                name="⏱️ 超時設定", value=f"{timeout_sec} 秒", inline=True
            )
            confirm_embed.add_field(
                name="⚠️ 請確認", value="此指令將在伺服器上執行，確定嗎？", inline=True
            )
            confirm_embed.set_footer(text=f"等待確認中（{CONFIRM_TIMEOUT} 秒後自動取消）")

            view = ConfirmCommandView(
                command=shell_cmd, step=step, total=MAX_STEPS, requester_id=caller_id
            )
            confirm_msg = await channel.send(embed=confirm_embed, view=view)

            # 等待管理員按鈕
            await view.wait()

            if view.confirmed is None:
                await channel.send(f"⏰ 確認超時（{CONFIRM_TIMEOUT} 秒），任務中止。")
                break

            if view.confirmed is False:
                await channel.send("🔴 任務已被管理員手動中止。")
                break

            # ── Step 3: 執行指令 ─────────────────────────────────────
            exec_msg = await channel.send(f"⚙️ 執行中：`{shell_cmd}`…")

            tool_result = self._tools.dispatch_tool(
                "run_terminal",
                {"command": shell_cmd, "timeout_sec": timeout_sec},
                caller_id=caller_id
            )

            # 顯示執行結果
            result_preview = str(tool_result)[:1500]
            result_embed = discord.Embed(
                title=f"📋 步驟 {step} 執行結果",
                description=f"```\n{result_preview}\n```",
                color=discord.Color.blue()
            )
            await exec_msg.edit(content="", embed=result_embed)

            # 更新對話歷史，讓 Gemini 知道結果
            conversation.append({
                "role": "model",
                "parts": [{"functionCall": fc}]
            })
            conversation.append({
                "role": "user",
                "parts": [{"functionResponse": {
                    "name": "run_terminal",
                    "response": {"result": str(tool_result)}
                }}]
            })

        # ── 結尾 ────────────────────────────────────────────────────────
        if not completed:
            await channel.send(
                f"⚠️ Shell Agent 已達到最大步驟數（{MAX_STEPS} 步）或提前終止。"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ShellAgent(bot))
