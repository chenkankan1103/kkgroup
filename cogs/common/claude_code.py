"""
KK園區 Claude Code CLI Discord Adapter
====================================================================
薄層 Discord Adapter，將 /cc 指令轉發到獨立的 Agent Server (FastAPI)。

架構變更 (2026-08):
- 核心 Agent 邏輯已移至 shared.agent (獨立進程 agent_server.py)
- 本模組僅負責：權限檢查、指令接收、HTTP API 呼叫、進度顯示
- 任務在獨立進程執行，不阻塞 Discord Bot Event Loop
- 支援長任務、取消/暫停/恢復、Webhook 回調

指令：
- /cc <prompt> - 提交代碼任務到 Agent Server
- /cc_status - 查看 Agent Server 狀態
- /cc_clear - 清除本地活躍任務記錄
"""

import asyncio
import logging
import os
import uuid
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 環境變數與權限設定 ─────────────────────────────────────────────────────
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
if not NVIDIA_API_KEY:
    logger.warning("⚠️ NVIDIA_API_KEY 未設定，Claude Code 功能將無法使用")

# Agent Server 設定
AGENT_SERVER_URL = os.getenv("AGENT_SERVER_URL", "http://localhost:8081")
AGENT_SERVER_TIMEOUT = int(os.getenv("AGENT_SERVER_TIMEOUT", "300"))  # 秒

MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "20"))
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))


# ─── 工具類別 ───────────────────────────────────────────────────────────────
class AgentAPIClient:
    """Agent Server HTTP API 客戶端"""

    def __init__(self, base_url: str = AGENT_SERVER_URL, timeout: int = AGENT_SERVER_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def submit_task(
        self,
        instruction: str,
        user_id: int,
        channel_id: int,
        continue_conv: bool = False,
        task_id: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> dict:
        """提交任務到 Agent Server"""
        payload = {
            "task_type": "code_agent",
            "payload": {
                "instruction": instruction,
                "user_id": user_id,
                "channel_id": channel_id,
                "continue_conv": continue_conv,
                "task_id": task_id,
            },
            "callback_url": callback_url,
        }
        async with self.session.post(f"{self.base_url}/agent/task", json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Agent Server Error {resp.status}: {text}")
            return await resp.json()

    async def get_task_status(self, task_id: str) -> dict:
        """查詢任務狀態"""
        async with self.session.get(f"{self.base_url}/agent/task/{task_id}") as resp:
            if resp.status == 404:
                raise ValueError("Task not found")
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Agent Server Error {resp.status}: {text}")
            return await resp.json()

    async def get_task_progress(self, task_id: str, wait: bool = False) -> dict:
        """查詢任務進度"""
        async with self.session.get(
            f"{self.base_url}/agent/task/{task_id}/progress", params={"wait": wait}
        ) as resp:
            if resp.status == 404:
                raise ValueError("Task not found")
            return await resp.json()

    async def cancel_task(self, task_id: str, force: bool = False) -> dict:
        """取消任務"""
        async with self.session.post(
            f"{self.base_url}/agent/task/{task_id}/cancel", json={"force": force}
        ) as resp:
            return await resp.json()

    async def health_check(self) -> dict:
        """健康檢查"""
        async with self.session.get(f"{self.base_url}/health") as resp:
            return await resp.json()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ─── 本地任務追蹤（簡單記憶體，用於顯示進度 View） ─────────────────────────
class LocalTaskTracker:
    """追蹤本地 Discord 互動對應的遠端任務"""

    def __init__(self):
        # (user_id, channel_id) -> {"task_id": ..., "message_id": ..., "updated_at": ...}
        self._tasks: dict[tuple, dict] = {}

    def set(self, user_id: int, channel_id: int, task_id: str, message_id: int):
        self._tasks[(user_id, channel_id)] = {
            "task_id": task_id,
            "message_id": message_id,
            "updated_at": asyncio.get_event_loop().time(),
        }

    def get(self, user_id: int, channel_id: int) -> Optional[dict]:
        return self._tasks.get((user_id, channel_id))

    def clear(self, user_id: int, channel_id: int):
        self._tasks.pop((user_id, channel_id), None)

    def get_task_id(self, user_id: int, channel_id: int) -> Optional[str]:
        task = self._tasks.get((user_id, channel_id))
        return task["task_id"] if task else None


# ─── Discord Views ──────────────────────────────────────────────────────────
class StopView(discord.ui.View):
    """停止/暫停按鈕 View"""

    def __init__(self, cog: "ClaudeCodeCog", user_id: int, task_id: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.task_id = task_id

    @discord.ui.button(label="⏸️ 暫停", style=discord.ButtonStyle.danger, custom_id="claude_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 只有發起者能暫停任務", ephemeral=True)
            return

        try:
            await self.cog.api.cancel_task(self.task_id, force=False)
            button.disabled = True
            button.label = "⏸️ 已暫停"
            self.clear_items()
            resume_button = discord.ui.Button(
                label="▶️ 恢復", style=discord.ButtonStyle.success, custom_id="claude_resume"
            )
            resume_button.callback = self._create_resume_callback(interaction)
            self.add_item(resume_button)
            await interaction.response.edit_message(content="⏸️ 任務已暫停", view=self)
        except Exception as e:
            await interaction.response.send_message(f"❌ 暫停失敗: {e}", ephemeral=True)

    def _create_resume_callback(self, original_interaction: discord.Interaction):
        async def resume_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ 只有發起者能恢復任務", ephemeral=True)
                return
            try:
                await self.cog.api.cancel_task(self.task_id, force=False)  # 暫停用 cancel force=false
                self.clear_items()
                new_stop = discord.ui.Button(label="⏸️ 暫停", style=discord.ButtonStyle.danger, custom_id="claude_stop")
                new_stop.callback = self.stop_button
                self.add_item(new_stop)
                await interaction.response.edit_message(content="▶️ 任務已恢復", view=self)
            except Exception as e:
                await interaction.response.send_message(f"❌ 恢復失敗: {e}", ephemeral=True)
        return resume_callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class ContinueView(discord.ui.View):
    """繼續執行按鈕"""

    def __init__(self, cog: "ClaudeCodeCog", user_id: int, task_id: str, original_prompt: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.task_id = task_id
        self.original_prompt = original_prompt

    @discord.ui.button(label="▶️ 繼續執行", style=discord.ButtonStyle.success, custom_id="claude_continue")
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 只有發起者能繼續任務", ephemeral=True)
            return

        button.disabled = True
        button.label = "⏳ 繼續中..."
        await interaction.response.edit_message(view=self)

        # 重新提交任務（續傳模式）
        try:
            result = await self.cog.api.submit_task(
                instruction=self.original_prompt,
                user_id=self.user_id,
                channel_id=interaction.channel_id,
                continue_conv=True,
                task_id=self.task_id,
            )
            new_task_id = result.get("task_id")
            self.cog.tracker.set(self.user_id, interaction.channel_id, new_task_id, interaction.message.id)

            # 新的進度訊息
            stop_view = StopView(self.cog, self.user_id, new_task_id)
            progress_msg = await interaction.followup.send("🔄 繼續執行...", view=stop_view)
            self.cog.tracker.set(self.user_id, interaction.channel_id, new_task_id, progress_msg.id)

            # 背景輪詢進度
            asyncio.create_task(self._poll_progress(progress_msg, new_task_id, stop_view))
        except Exception as e:
            await interaction.followup.send(f"❌ 繼續失敗: {e}")

    async def _poll_progress(self, message: discord.Message, task_id: str, view: StopView):
        """背景輪詢進度並更新訊息"""
        last_progress = ""
        for _ in range(1800):  # 最多 30 分鐘
            await asyncio.sleep(1)
            try:
                progress_data = await self.cog.api.get_task_progress(task_id, wait=True)
                progress = progress_data.get("progress", "")
                status = progress_data.get("status", "")

                if progress != last_progress and progress:
                    last_progress = progress
                    try:
                        chunks = self._chunk_text(progress, 1900)
                        if len(chunks) == 1:
                            await message.edit(content=chunks[0], view=view)
                        else:
                            await message.edit(content=chunks[0], view=view)
                    except (discord.NotFound, discord.HTTPException):
                        break

                if status in ("completed", "failed", "cancelled"):
                    # 最終結果
                    task = await self.cog.api.get_task_status(task_id)
                    result = task.get("result", {})
                    output = result.get("output", task.get("error", "完成"))
                    await message.edit(view=None)  # 移除按鈕
                    for chunk in self._chunk_text(str(output), 1900):
                        await message.channel.send(chunk)
                    self.cog.tracker.clear(self.user_id, message.channel.id)
                    break
            except Exception:
                break

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> list[str]:
        if len(text) <= max_len:
            return [text]
        return [text[i:i+max_len] for i in range(0, len(text), max_len)]

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ─── Discord Cog ────────────────────────────────────────────────────────────
class ClaudeCodeCog(commands.Cog):
    """Claude Code CLI Discord 整合 (Adapter 模式)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = AgentAPIClient()
        self.tracker = LocalTaskTracker()
        logger.info("✅ ClaudeCodeCog (Adapter) 初始化完成")

    def _check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == ADMIN_USER_ID:
            return True
        admin_role = os.getenv("ADMIN_ROLE_NAME", "管理員")
        return any(r.name == admin_role for r in getattr(interaction.user, "roles", []))

    @app_commands.command(name="cc", description="Claude Code Agent - AI 程式開發助手（管理員限定）")
    @app_commands.describe(prompt="任務描述，例如：幫我新增一個 /ping 指令", continue_conv="繼續上一輪對話")
    async def cc(self, interaction: discord.Interaction, prompt: str, continue_conv: bool = False):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 僅限 Discord 管理員使用。", ephemeral=True)
            return

        if not NVIDIA_API_KEY:
            await interaction.response.send_message("❌ NVIDIA_API_KEY 未設定。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            user_id = interaction.user.id
            channel_id = interaction.channel_id

            # 檢查是否有進行中的任務
            existing = self.tracker.get(user_id, channel_id)
            task_id = existing["task_id"] if (continue_conv and existing) else None

            # 提交任務
            result = await self.api.submit_task(
                instruction=prompt,
                user_id=user_id,
                channel_id=channel_id,
                continue_conv=continue_conv,
                task_id=task_id,
            )
            task_id = result["task_id"]

            # 發送初始進度訊息
            stop_view = StopView(self, user_id, task_id)
            initial_msg = await interaction.followup.send(
                f"✅ 任務已提交\n🆔 Task ID: `{task_id}`\n🔄 處理中...",
                view=stop_view,
                ephemeral=True,
            )

            # 記錄區域追蹤
            self.tracker.set(user_id, channel_id, task_id, initial_msg.id)

            # 背景輪詢進度
            asyncio.create_task(self._poll_progress(initial_msg, task_id, stop_view, prompt))

        except Exception as e:
            logger.exception("CC command error")
            await interaction.followup.send(f"❌ 提交失敗: {e}", ephemeral=True)

    async def _poll_progress(
        self, message: discord.Message, task_id: str, view: StopView, original_prompt: str
    ):
        """背景輪詢 Agent Server 進度並更新 Discord 訊息"""
        last_progress = ""
        user_id = message.interaction.user.id if message.interaction else 0
        channel_id = message.channel.id

        for _ in range(1800):  # 30 分鐘最長等待
            await asyncio.sleep(1)
            try:
                progress_data = await self.api.get_task_progress(task_id, wait=True)
                progress = progress_data.get("progress", "")
                status = progress_data.get("status", "")

                if progress != last_progress and progress:
                    last_progress = progress
                    try:
                        chunks = self._chunk_text(progress, 1900)
                        if len(chunks) == 1:
                            await message.edit(content=chunks[0], view=view)
                        else:
                            await message.edit(content=chunks[0], view=view)
                            for chunk in chunks[1:]:
                                await message.channel.send(chunk)
                    except (discord.NotFound, discord.HTTPException):
                        break

                if status in ("completed", "failed", "cancelled"):
                    task = await self.api.get_task_status(task_id)
                    result = task.get("result", {})
                    error = task.get("error")
                    output = result.get("output", error or "任務完成")

                    # 移除按鈕
                    try:
                        await message.edit(view=None)
                    except Exception:
                        pass

                    # 發送最終結果
                    for chunk in self._chunk_text(str(output), 1900):
                        await message.channel.send(chunk)

                    # 清理追蹤
                    self.tracker.clear(user_id, channel_id)
                    break

            except Exception as e:
                logger.warning(f"Progress poll error: {e}")
                break

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> list[str]:
        if len(text) <= max_len:
            return [text]
        return [text[i:i+max_len] for i in range(0, len(text), max_len)]

    @app_commands.command(name="cc_status", description="查看 Agent Server 狀態")
    async def cc_status(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
            return

        try:
            health = await self.api.health_check()
            local_active = len(self.tracker._tasks)

            embed = discord.Embed(title="🤖 Agent Server 狀態", color=discord.Color.blue())
            embed.add_field(name="Server 狀態", value=health.get("status", "unknown"), inline=True)
            embed.add_field(name="執行中任務", value=str(health.get("running_tasks", 0)), inline=True)
            embed.add_field(name="本地追蹤任務", value=str(local_active), inline=True)
            embed.add_field(name="Server URL", value=AGENT_SERVER_URL, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 無法連線 Agent Server: {e}", ephemeral=True)

    @app_commands.command(name="cc_clear", description="清除本地任務追蹤記錄")
    async def cc_clear(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
            return

        user_id = interaction.user.id
        channel_id = interaction.channel_id
        self.tracker.clear(user_id, channel_id)
        await interaction.response.send_message("✅ 已清除本地任務記錄", ephemeral=True)

    async def cog_unload(self):
        await self.api.close()
        logger.info("ClaudeCodeCog unloaded")


async def setup(bot: commands.Bot):
    await bot.add_cog(ClaudeCodeCog(bot))