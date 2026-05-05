"""KK園區日誌事件監控（事件驅動，非輪詢）
=============================================

原理：
    journalctl -u bot.service -u shopbot.service -u uibot.service \\
               -f -n 0 --output=cat

    asyncio 持續讀取 stdout，有新行才觸發；閒置時 CPU ≈ 0。
    不做定時掃描，完全由系統日誌事件驅動。

流程：
    新日誌行 → 模式匹配（ERROR / CRITICAL / Traceback / Exception）
    → Debounce 30s（累積同批錯誤）
    → LLMClient 分析根本原因 + 建議修復
    → Discord 通知管理員

安全機制：
    - 同類錯誤 10 分鐘內只通知一次（冷却）
    - subprocess 意外死亡自動重啟（60s 後）
    - 所有功能可透過 /logmonitor 指令手動控制
"""

import asyncio
import os
import re
import time
import logging
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from cogs.common.AI import LLMClient

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 設定 ─────────────────────────────────────────────────────────────────────
_LOG_CHANNEL_ID:   int = int(os.getenv("LOG_CHANNEL_ID",      "0"))
_STAFF_CHANNEL_ID: int = int(os.getenv("STAFF_ID_CHANNEL_ID", "0"))
_ADMIN_CHANNEL_ID: int = int(os.getenv("ADMIN_CHANNEL_ID",    "0"))
_LEADER_ID:        int = int(os.getenv("LEADER_DISCORD_ID",   "0"))
_ADMIN_ROLE:       str = os.getenv("ADMIN_ROLE_NAME", "管理員")

# 通知頻道優先順序：LOG_CHANNEL_ID > STAFF_ID_CHANNEL_ID > ADMIN_CHANNEL_ID
_ALERT_CHANNEL_ID: int = _LOG_CHANNEL_ID or _STAFF_CHANNEL_ID or _ADMIN_CHANNEL_ID

_SERVICES = ["bot.service", "shopbot.service", "uibot.service"]

# 監控的模式（任一匹配就算「錯誤事件」）
_ERROR_PATTERNS = re.compile(
    r"(ERROR|CRITICAL|Traceback|Exception|Fatal|Unhandled|failed to load)",
    re.IGNORECASE,
)

_DEBOUNCE_SEC:  int   = 30    # 累積錯誤的時間窗口（秒）
_COOLDOWN_SEC:  int   = 600   # 同類錯誤再次通知的最短間隔（秒）
_MAX_LOG_LINES: int   = 20    # 送給 LLM 分析的最大行數
_RESTART_DELAY: int   = 60    # subprocess 死亡後等待重啟的秒數


# ══════════════════════════════════════════════════════════════════════════════
# LogMonitorEngine — 核心事件驅動引擎
# ══════════════════════════════════════════════════════════════════════════════

class LogMonitorEngine:
    """journalctl -f 事件驅動引擎。

    - 持續讀取日誌流（asyncio subprocess）
    - Debounce 累積後呼叫 LLM 分析
    - Discord 通知（帶冷却）
    """

    def __init__(self, bot: commands.Bot, llm: LLMClient):
        self.bot     = bot
        self.llm     = llm
        self.enabled = True

        self._proc:          Optional[asyncio.subprocess.Process] = None
        self._error_buffer:  list[str] = []
        self._debounce_task: Optional[asyncio.Task]               = None
        self._cooldowns:     dict[str, float]                     = {}

    # ── 公開控制 ──────────────────────────────────────────────────────────────

    async def start(self):
        """啟動監控循環（自動重啟）"""
        while True:
            if not self.enabled:
                await asyncio.sleep(5)
                continue
            try:
                await self._run_once()
            except Exception as e:
                logger.error(f"[LogMonitor] 監控迴圈異常: {e}", exc_info=True)
            logger.warning(f"[LogMonitor] subprocess 結束，{_RESTART_DELAY}s 後重啟…")
            await asyncio.sleep(_RESTART_DELAY)

    def pause(self):
        self.enabled = False
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()

    def resume(self):
        self.enabled = True

    # ── 核心：讀取日誌流 ──────────────────────────────────────────────────────

    async def _run_once(self):
        cmd = (
            ["journalctl"]
            + [arg for svc in _SERVICES for arg in ("-u", svc)]
            + ["-f", "-n", "0", "--output=cat", "--no-pager"]
        )
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        logger.info("[LogMonitor] journalctl -f 已啟動（事件驅動模式）")

        async for raw in self._proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if _ERROR_PATTERNS.search(line):
                self._on_error_line(line)

        await self._proc.wait()

    # ── Debounce：累積 → 批量分析 ─────────────────────────────────────────────

    def _on_error_line(self, line: str):
        self._error_buffer.append(line)

        # 重置 debounce 計時器
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._debounce_task = asyncio.create_task(
            self._flush_after_debounce()
        )

    async def _flush_after_debounce(self):
        await asyncio.sleep(_DEBOUNCE_SEC)

        batch        = self._error_buffer[:_MAX_LOG_LINES]
        self._error_buffer.clear()
        self._debounce_task = None

        if not batch:
            return

        # 冷却檢查（取第一行做指紋）
        fingerprint = batch[0][:80]
        if time.time() < self._cooldowns.get(fingerprint, 0):
            logger.info("[LogMonitor] 冷却中，跳過通知")
            return
        self._cooldowns[fingerprint] = time.time() + _COOLDOWN_SEC

        await self._analyze_and_notify(batch)

    # ── LLM 分析 + Discord 通知 ────────────────────────────────────────────────

    async def _analyze_and_notify(self, lines: list[str]):
        log_text = "\n".join(lines)
        logger.info(f"[LogMonitor] 觸發分析（{len(lines)} 行錯誤）")

        # Gemini 分析
        analysis = await self.llm.gemini(
            api_key=os.getenv("AI_API_KEY", ""),
            model=os.getenv("AI_API_MODEL", "gemini-2.0-flash"),
            system=(
                "你是 KK園區的 DevOps 工程師，專門分析 Discord Bot 的系統日誌。\n"
                "請用繁體中文回覆，格式如下：\n"
                "【根本原因】一句話說明\n"
                "【建議修復】1~3 個具體步驟\n"
                "【緊急程度】高 / 中 / 低"
            ),
            contents=[{
                "role": "user",
                "parts": [{"text": f"以下是剛發生的錯誤日誌：\n```\n{log_text}\n```\n請分析。"}],
            }],
        )

        # 解析分析結果
        if analysis:
            parts = analysis.get("content", {}).get("parts", [])
            ai_text = parts[0].get("text", "（無法解析分析結果）").strip() if parts else "（LLM 無回應）"
        else:
            # Groq 降級
            ai_text_raw = await self.llm.groq([
                {"role": "system", "content": "你是 DevOps 工程師，分析 Discord Bot 日誌。繁體中文，簡潔。"},
                {"role": "user",   "content": f"錯誤日誌：\n{log_text}\n\n請分析根本原因和建議修復。"},
            ], max_tokens=300)
            ai_text = ai_text_raw or "LLM 分析失敗，請手動檢查日誌。"

        # 送出 Discord Embed
        channel = self.bot.get_channel(_ALERT_CHANNEL_ID)
        if not channel:
            logger.warning(f"[LogMonitor] 找不到通知頻道 ID={_ALERT_CHANNEL_ID}")
            return

        embed = discord.Embed(
            title="🚨 Bot 日誌偵測到錯誤",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(
            name="📋 錯誤日誌",
            value=f"```\n{log_text[:800]}\n```",
            inline=False,
        )
        embed.add_field(
            name="🤖 AI 分析",
            value=ai_text[:1000],
            inline=False,
        )
        embed.set_footer(text=f"事件驅動監控 · 冷却 {_COOLDOWN_SEC//60} 分鐘")

        try:
            await channel.send(embed=embed)
            logger.info("[LogMonitor] 已送出 Discord 通知")
        except Exception as e:
            logger.error(f"[LogMonitor] 送出通知失敗: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# LogMonitor — Discord Cog
# ══════════════════════════════════════════════════════════════════════════════

class LogMonitor(commands.Cog):
    """日誌事件監控 Cog（事件驅動）。"""

    def __init__(self, bot: commands.Bot):
        self.bot    = bot
        self._llm   = LLMClient()
        self._engine = LogMonitorEngine(bot, self._llm)
        self._task: Optional[asyncio.Task] = None
        logger.info("✅ LogMonitor Cog 已載入")

    async def cog_load(self):
        if _ALERT_CHANNEL_ID:
            self._task = asyncio.create_task(self._engine.start())
            logger.info(f"[LogMonitor] 監控已啟動（通知頻道 {_ALERT_CHANNEL_ID}）")
        else:
            logger.warning("[LogMonitor] LOG_CHANNEL_ID / ADMIN_CHANNEL_ID 未設定，監控未啟動")

    async def cog_unload(self):
        if self._task:
            self._engine.pause()
            self._task.cancel()

    def _check_perm(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == _LEADER_ID:
            return True
        return any(r.name == _ADMIN_ROLE for r in getattr(interaction.user, "roles", []))

    @app_commands.command(name="logmonitor", description="日誌監控控制（管理員限定）")
    @app_commands.describe(action="pause=暫停 / resume=恢復 / status=狀態")
    @app_commands.choices(action=[
        app_commands.Choice(name="status",  value="status"),
        app_commands.Choice(name="pause",   value="pause"),
        app_commands.Choice(name="resume",  value="resume"),
    ])
    async def logmonitor(self, interaction: discord.Interaction, action: str):
        if not self._check_perm(interaction):
            await interaction.response.send_message("❌ 管理員限定。", ephemeral=True)
            return

        if action == "status":
            proc    = self._engine._proc
            running = proc is not None and proc.returncode is None
            enabled = self._engine.enabled
            buf_len = len(self._engine._error_buffer)
            embed   = discord.Embed(
                title="📊 日誌監控狀態",
                color=discord.Color.green() if (running and enabled) else discord.Color.orange(),
            )
            embed.add_field(name="監控",     value="✅ 運行中" if (running and enabled) else "⏸️ 已暫停", inline=True)
            embed.add_field(name="監控服務", value="\n".join(_SERVICES),                                  inline=True)
            embed.add_field(name="緩衝行數", value=str(buf_len),                                          inline=True)
            embed.add_field(name="通知頻道", value=f"<#{_ALERT_CHANNEL_ID}>",                            inline=True)
            await interaction.response.send_message(embed=embed)

        elif action == "pause":
            self._engine.pause()
            await interaction.response.send_message("⏸️ 日誌監控已暫停。")

        elif action == "resume":
            self._engine.resume()
            if not self._task or self._task.done():
                self._task = asyncio.create_task(self._engine.start())
            await interaction.response.send_message("▶️ 日誌監控已恢復。")


async def setup(bot: commands.Bot):
    await bot.add_cog(LogMonitor(bot))
