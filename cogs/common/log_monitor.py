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
import json
import requests
from datetime import datetime
from typing import Optional

import os
import sys

# 添加項目根目錄到Python路徑
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from cogs.common.AI import LLMClient
from utils.google_ai import GoogleAIClient
from utils.nvidia_ai import NVIDIAAIClient

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 設定 ─────────────────────────────────────────────────────────────────────
_LOG_CHANNEL_ID:   int = int(os.getenv("LOG_CHANNEL_ID") or os.getenv("DASHBOARD_CHANNEL_ID", "1470272652429099125"))
_STAFF_CHANNEL_ID: int = int(os.getenv("STAFF_ID_CHANNEL_ID", "0"))
_ADMIN_CHANNEL_ID: int = int(os.getenv("ADMIN_CHANNEL_ID",    "0"))
_ADMIN_USER_ID:    int = int(os.getenv("ADMIN_USER_ID",       "0"))
_ADMIN_ROLE_ID:    int = int(os.getenv("ADMIN_ROLE_ID",       "0"))
_ADMIN_ROLE:       str = os.getenv("ADMIN_ROLE_NAME", "管理員")

# 通知頻道優先順序：LOG_CHANNEL_ID > STAFF_ID_CHANNEL_ID > ADMIN_CHANNEL_ID
_ALERT_CHANNEL_ID: int = _LOG_CHANNEL_ID or _STAFF_CHANNEL_ID or _ADMIN_CHANNEL_ID

_SERVICES = ["bot.service", "shopbot.service", "uibot.service"]

# 監控的模式（任一匹配就算「錯誤事件」）
_ERROR_PATTERNS = re.compile(
    r"(" 
    r"ERROR|CRITICAL|Traceback|Exception|Fatal|Unhandled|"
    r"failed to load|failed with result|status=\d+/FAILURE|"
    r"timeout|timed out|crash(?:ed)?|panic|oom|killed process|"
    r"connection (?:reset|refused|closed)|cannot connect|can't connect|"
    r"permission denied|\b429\b|(?:HTTP|http)\s*[45]\d\d|"
    r"Gemini HTTP|Groq HTTP|rate limit|quota"
    r")",
    re.IGNORECASE,
)

_BENIGN_PATTERNS = re.compile(
    r"("
    r"\bINFO\b|"
    r"✅|成功|已更新|已編輯|編輯成功|"
    r"SET_USER|成功寫入數據庫|欄位數=|"
    r"編輯事件訊息|工作系統訊息|公告已編輯|"
    r"冷却中|進入冷却|cooldown"
    r")",
    re.IGNORECASE,
)

# 排除這些誤報：Entry Point 警告、單獨的 JSON 欄位片段、已知忽略訊息
_IGNORE_PATTERNS = re.compile(
    r"(Entry Point.*(?:warning|ignored|警告|命令)|"
    r"error code: 50240|"
    r'"error":\s*[{\[]|'                        # JSON error 欄位（任何開頭，無 ^ anchor）
    r"command sync warning|"
    r"已忽略|"
    r"FILE_LOG.*Entry Point|"
    r"BOT_DEBUG.*Entry Point)",
    re.IGNORECASE,
)

# 高危錯誤判斷（只要命中此模式，視為需要升級到 Gemini 的情況）
_HIGH_SEVERITY_PATTERNS = re.compile(
    r"(Traceback|CRITICAL|Fatal|Unhandled|oom|killed process|failed with result|status=\d+/FAILURE|panic|permission denied|cannot connect|connection (?:reset|refused|closed))",
    re.IGNORECASE,
)

_DEBOUNCE_SEC:  int   = 30    # 累積錯誤的時間窗口（秒）
_COOLDOWN_SEC:  int   = 600   # 同類錯誤再次通知的最短間隔（秒）
_MAX_LOG_LINES: int   = 20    # 送給 LLM 分析的最大行數
_RESTART_DELAY: int   = 60    # subprocess 死亡後等待重啟的秒數
_MAX_ACTIVE_INCIDENTS: int = 8
_MAX_EMBED_INCIDENTS: int = 5


def _save_message_state(message_id: int):
    """保存訊息 ID 到 .env 檔案"""
    try:
        env_file = os.path.join(parent_dir, ".env")
        
        # 讀取現有 .env 內容
        lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        # 移除舊的 LOGMONITOR_MESSAGE_ID 行
        lines = [line for line in lines if not line.strip().startswith('LOGMONITOR_MESSAGE_ID=')]
        
        # 添加新的 message ID
        lines.append(f"LOGMONITOR_MESSAGE_ID={message_id}\n")
        
        # 寫回檔案
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        logger.info(f"[LogMonitor] 已保存訊息 ID 到 .env: {message_id}")
    except Exception as e:
        logger.error(f"[LogMonitor] 保存訊息 ID 到 .env 失敗: {e}")


def _load_message_state() -> Optional[int]:
    """從 .env 載入訊息 ID"""
    try:
        message_id = os.getenv("LOGMONITOR_MESSAGE_ID")
        if message_id:
            logger.info(f"[LogMonitor] 已從 .env 載入訊息 ID: {message_id}")
            return int(message_id)
        return None
    except Exception as e:
        logger.error(f"[LogMonitor] 從 .env 載入訊息 ID 失敗: {e}")
        return None


def _clear_message_state():
    """從 .env 清除訊息 ID"""
    try:
        env_file = os.path.join(parent_dir, ".env")
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 移除 LOGMONITOR_MESSAGE_ID 行
            lines = [line for line in lines if not line.strip().startswith('LOGMONITOR_MESSAGE_ID=')]
            
            with open(env_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info("[LogMonitor] 已從 .env 清除訊息 ID")
    except Exception as e:
        logger.error(f"[LogMonitor] 從 .env 清除訊息 ID 失敗: {e}")


def _has_admin_access(user) -> bool:
    if getattr(user, "id", 0) == _ADMIN_USER_ID:
        return True
    return any(
        (_ADMIN_ROLE_ID and r.id == _ADMIN_ROLE_ID) or r.name == _ADMIN_ROLE
        for r in getattr(user, "roles", [])
    )


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _extract_severity(ai_text: str) -> str:
    match = re.search(r"【緊急程度】\s*(高|中|低)", ai_text)
    return match.group(1) if match else "未標註"


def _estimate_severity_from_lines(lines: list[str]) -> str:
    """根據原始日誌行推估嚴重度：返回 'high'/'medium'/'low'"""
    joined = "\n".join(lines)
    if _HIGH_SEVERITY_PATTERNS.search(joined):
        return "high"
    if re.search(r"\b429\b|rate limit|quota|(?:HTTP|http)\s*[45]\d\d", joined, re.IGNORECASE):
        return "medium"
    return "low"


def _extract_relevant_lines(blob: str) -> list[str]:
    relevant_lines: list[str] = []
    for raw_line in blob.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _IGNORE_PATTERNS.search(line):
            continue
        if not _ERROR_PATTERNS.search(line):
            continue
        if _BENIGN_PATTERNS.search(line) and not re.search(r"\b(ERROR|CRITICAL|Traceback|Exception|Fatal|Unhandled)\b", line, re.IGNORECASE):
            continue
        relevant_lines.append(line)
    return relevant_lines


def _is_benign_yfinance_line(line: str) -> bool:
    return bool(re.search(r"\[yfinance\].*possibly delisted; no price data found", line, re.IGNORECASE))


def _build_local_fallback_summary(lines: list[str]) -> str:
    if lines and all(_is_benign_yfinance_line(line) for line in lines):
        return (
            "【根本原因】資料來源 yfinance 對部分商品代號暫時取不到價格，屬外部資料缺口，不一定是 Bot 程式異常。\n"
            "【建議修復】1. 檢查代號是否仍有效 2. 對無資料情況改為跳過或降級為 warning 3. 避免將此類訊息列入重大錯誤通知\n"
            "【緊急程度】低"
        )

    joined = "\n".join(lines)
    if re.search(r"\b429\b|rate limit|quota", joined, re.IGNORECASE):
        return (
            "【根本原因】外部 AI 或 API 配額／速率限制觸發。\n"
            "【建議修復】1. 檢查 API 配額 2. 增加退避與重試 3. 降低短時間內請求量\n"
            "【緊急程度】中"
        )

    if re.search(r"Traceback|Exception|CRITICAL|Fatal|Unhandled", joined, re.IGNORECASE):
        return (
            "【根本原因】Bot 執行流程拋出未處理例外，需依 traceback 定位故障點。\n"
            "【建議修復】1. 依錯誤堆疊檢查對應函式 2. 補上防呆與例外處理 3. 修正後重新驗證相同行為\n"
            "【緊急程度】高"
        )

    return (
        "【根本原因】LogMonitor 偵測到異常日誌，但 LLM 分析不可用，需人工判讀。\n"
        "【建議修復】1. 檢查原始錯誤段 2. 驗證對應模組近期變更 3. 如屬已知誤報則加入排除規則\n"
        "【緊急程度】中"
    )


# ══════════════════════════════════════════════════════════════════════════════
# AutoFixView — 「啟動自動修復」按鈕
# ══════════════════════════════════════════════════════════════════════════════

class LogMonitorSummaryView(discord.ui.View):
    """單一彙整訊息的操作按鈕。"""

    def __init__(self, engine, runner, channel: Optional[discord.TextChannel] = None):
        super().__init__(timeout=None)
        self._engine = engine
        self._runner = runner
        self._channel = channel

    @discord.ui.button(
        label="🔧 啟動自動修復",
        style=discord.ButtonStyle.danger,
        custom_id="logmonitor:auto_fix",
    )
    async def auto_fix(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            logger.info(f"[LogMonitorView] auto_fix 按鈕被點擊，用戶: {interaction.user}")
            
            if not _has_admin_access(interaction.user):
                logger.warning(f"[LogMonitorView] 用戶 {interaction.user} 無管理員權限")
                await interaction.response.send_message("❌ 管理員限定。", ephemeral=True)
                return

            if not self._runner:
                logger.warning("[LogMonitorView] ShellAgentRunner 未載入")
                await interaction.response.send_message("❌ 自動修復模組未載入。", ephemeral=True)
                return

            if not self._channel:
                logger.warning("[LogMonitorView] _channel 為 None")
                await interaction.response.send_message("❌ 通知頻道未設定。", ephemeral=True)
                return

            fix_goal = self._engine.build_fix_goal()
            if not fix_goal:
                logger.info("[LogMonitorView] 沒有待修復的錯誤")
                await interaction.response.send_message("✅ 目前沒有待修復的彙整錯誤。", ephemeral=True)
                return

            await interaction.response.send_message("🚀 已啟動自動修復，請稍候。", ephemeral=True)
            await self._channel.send(
                f"🚀 **自動修復啟動** — 由 {interaction.user.mention} 觸發"
            )
            asyncio.create_task(
                self._runner.run(fix_goal, self._channel, _ADMIN_USER_ID)
            )
            logger.info("[LogMonitorView] auto_fix 執行完成")
        except Exception as e:
            logger.error(f"[LogMonitorView] auto_fix 異常: {e}", exc_info=True)
            try:
                await interaction.response.send_message(f"❌ 發生錯誤: {e}", ephemeral=True)
            except Exception as e2:
                logger.error(f"[LogMonitorView] 發送錯誤訊息失敗: {e2}")

    @discord.ui.button(
        label="✅ 已修復，清空",
        style=discord.ButtonStyle.success,
        custom_id="logmonitor:clear",
    )
    async def clear_errors(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            logger.info(f"[LogMonitorView] clear_errors 按鈕被點擊，用戶: {interaction.user}")
            
            if not _has_admin_access(interaction.user):
                logger.warning(f"[LogMonitorView] 用戶 {interaction.user} 無管理員權限")
                await interaction.response.send_message("❌ 管理員限定。", ephemeral=True)
                return

            embed = self._engine.clear_summary(interaction.user.display_name)
            await interaction.response.edit_message(embed=embed, view=None)
            logger.info("[LogMonitorView] clear_errors 執行完成")
        except Exception as e:
            logger.error(f"[LogMonitorView] clear_errors 異常: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ 發生錯誤: {e}", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
# LogMonitorEngine — 核心事件驅動引擎
# ══════════════════════════════════════════════════════════════════════════════

class LogMonitorEngine:
    """journalctl -f 事件驅動引擎。

    - 持續讀取日誌流（asyncio subprocess）
    - Debounce 累積後呼叫 LLM 分析
    - Discord 通知（帶冷却）
    """

    def __init__(self, bot: commands.Bot, llm: LLMClient, shell_runner=None):
        self.bot          = bot
        self.llm          = llm
        self.shell_runner = shell_runner  # ShellAgentRunner，可為 None
        self.enabled      = True
        self.cog_instance = None  # 引用 Cog 實例（由 Cog.__init__ 設定）

        self._proc:          Optional[asyncio.subprocess.Process] = None
        self._error_buffer:  list[str] = []
        self._debounce_task: Optional[asyncio.Task]               = None
        self._cooldowns:     dict[str, float]                     = {}
        self._active_incidents: list[dict[str, str]]              = []
        self._summary_message: Optional[discord.Message]          = None
        self._message_lock = asyncio.Lock()
        
        # 標記需要恢復訊息引用
        self._need_restore = True

    async def _analyze_with_debug_ai(self, log_text: str, severity_hint: str = "low") -> Optional[str]:
        prompt = (
            "你是 KK園區的 DevOps 工程師，專門分析 Discord Bot 的系統日誌。\n"
            "請用繁體中文回覆，格式如下：\n"
            "【根本原因】一句話說明\n"
            "【建議修復】1~3 個具體步驟\n"
            "【緊急程度】高 / 中 / 低\n\n"
            f"以下是剛發生的錯誤日誌：\n```\n{log_text}\n```\n請分析。"
        )
        messages = [
            {"role": "system", "content": "你是 KK園區的 DevOps 工程師。請依指定格式輸出。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await NVIDIAAIClient().call_api(
                messages,
                model="deepseek-ai/deepseek-v4-pro",
                temperature=0.2,
                max_tokens=500,
            )
            if response:
                logger.info("[LogMonitor] 使用 NVIDIA 完成日誌分析")
                return response.strip()
        except Exception as exc:
            logger.warning(f"[LogMonitor] NVIDIA 分析失敗: {exc}")

        # 只有在推估為高危的情況下才使用 Gemini（以節省配額）
        if severity_hint != "high":
            logger.info(f"[LogMonitor] severity_hint={severity_hint} 且 NVIDIA 無回應，跳過 Gemini 以節省配額")
            return None

        try:
            response = await GoogleAIClient().call_api(
                messages,
                temperature=0.2,
                max_tokens=500,
            )
            if response:
                logger.info("[LogMonitor] 使用 Gemini 備援完成日誌分析")
                return response.strip()
        except Exception as exc:
            logger.warning(f"[LogMonitor] Gemini 備援分析失敗: {exc}")

        return None

    async def _restore_message_reference(self):
        """嘗試恢復舊訊息的引用"""
        if not self._need_restore:
            return
            
        message_id = _load_message_state()
        if not message_id:
            self._need_restore = False
            return
        
        try:
            # 等待 bot 準備就緒
            await self.bot.wait_until_ready()
            
            channel = self.bot.get_channel(_ALERT_CHANNEL_ID)
            if not channel:
                logger.warning(f"[LogMonitor] 找不到通知頻道 {_ALERT_CHANNEL_ID}，無法恢復訊息")
                self._need_restore = False
                return
            
            # 嘗試獲取舊訊息
            try:
                message = await channel.fetch_message(message_id)
                self._summary_message = message
                logger.info(f"[LogMonitor] ✅ 成功恢復舊訊息引用: {message_id}")
            except discord.NotFound:
                logger.info(f"[LogMonitor] 舊訊息 {message_id} 已被刪除，將創建新訊息")
                _clear_message_state()
            except discord.Forbidden:
                logger.warning(f"[LogMonitor] 沒有權限存取訊息 {message_id}")
                _clear_message_state()
                
        except Exception as e:
            logger.error(f"[LogMonitor] 恢復訊息引用時發生錯誤: {e}")
        finally:
            self._need_restore = False

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
            ["/usr/bin/journalctl"]
            + [arg for svc in _SERVICES for arg in ("-u", svc)]
            + ["-f", "-n", "0", "--output=cat", "--no-pager"]
        )
        # 設定 UTF-8 locale，避免 subprocess 讀到亂碼
        env = os.environ.copy()
        env["LANG"]   = "C.UTF-8"
        env["LC_ALL"] = "C.UTF-8"
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        logger.info("[LogMonitor] journalctl -f 已啟動（事件驅動模式）")

        async for raw in self._proc.stdout:
            decoded = raw.decode("utf-8", errors="replace").rstrip()
            for line in _extract_relevant_lines(decoded):
                self._on_error_line(line)

        await self._proc.wait()

    # ── Debounce：累積 → 批量分析 ─────────────────────────────────────────────

    def _on_error_line(self, line: str):
        if _is_benign_yfinance_line(line):
            logger.info(f"[LogMonitor] 略過已知 yfinance 誤報: {line}")
            return

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

        # 根據原始日誌先推估嚴重度，供備援策略使用
        severity_hint = _estimate_severity_from_lines(lines)
        ai_text = await self._analyze_with_debug_ai(log_text, severity_hint)
        if not ai_text:
            # Groq 降級
            ai_text_raw = await self.llm.groq([
                {"role": "system", "content": "你是 DevOps 工程師，分析 Discord Bot 日誌。繁體中文，簡潔。"},
                {"role": "user",   "content": f"錯誤日誌：\n{log_text}\n\n請分析根本原因和建議修復。"},
            ], max_tokens=300)
            ai_text = ai_text_raw or _build_local_fallback_summary(lines)

        # 🔥 新增：觸發 GitHub Actions AI 分析
        await self._trigger_github_actions_analysis(log_text, ai_text)
        
        # 送出 Discord Embed
        channel = self.bot.get_channel(_ALERT_CHANNEL_ID)
        if not channel:
            logger.warning(f"[LogMonitor] 找不到通知頻道 ID={_ALERT_CHANNEL_ID}")
            return

        self._active_incidents.append({
            "created_at": datetime.utcnow().strftime("%m-%d %H:%M:%S UTC"),
            "log_text": log_text,
            "ai_text": ai_text,
            "severity": _extract_severity(ai_text),
        })
        self._active_incidents = self._active_incidents[-_MAX_ACTIVE_INCIDENTS:]

        try:
            await self._upsert_summary_message(channel)
            logger.info("[LogMonitor] 已更新 Discord 彙整通知")
        except Exception as e:
            logger.error(f"[LogMonitor] 送出通知失敗: {e}")

    async def _trigger_github_actions_analysis(self, log_text: str, ai_text: str):
        """觸發 GitHub Actions 進行更深入的 AI 分析"""
        try:
            # 檢查是否需要觸發（高緊急程度或特定錯誤類型）
            severity = _extract_severity(ai_text)
            should_trigger = (
                severity == "高" or
                "Traceback" in log_text or
                "Exception" in log_text or
                "CRITICAL" in log_text or
                "Fatal" in log_text
            )
            
            if not should_trigger:
                logger.info(f"[LogMonitor] 錯誤緊急程度為{severity}，跳過 GitHub Actions 觸發")
                return
            
            # 準備 webhook 資料
            webhook_data = {
                "event_type": "error_analysis",
                "client_payload": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "log_text": log_text[:2000],  # 限制長度
                    "ai_analysis": ai_text[:1000],  # 限制長度
                    "severity": severity,
                    "source": "log_monitor_realtime"
                }
            }
            
            # 發送到 GitHub repository_dispatch webhook
            repo_url = "https://api.github.com/repos/chenkankan1103/kkgroup/dispatches"
            token = os.getenv("GITHUB_TOKEN")  # 需要在 .env 中設定 GitHub Token
            
            if not token:
                logger.warning("[LogMonitor] GITHUB_TOKEN 未設定，無法觸發 GitHub Actions")
                return
            
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json"
            }
            
            response = requests.post(repo_url, json=webhook_data, headers=headers, timeout=10)
            
            if response.status_code == 204:
                logger.info(f"[LogMonitor] ✅ 已觸發 GitHub Actions AI 分析 (緊急程度: {severity})")
            else:
                logger.error(f"[LogMonitor] ❌ 觸發 GitHub Actions 失敗: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"[LogMonitor] 觸發 GitHub Actions 時發生錯誤: {e}", exc_info=True)
    
    def build_fix_goal(self) -> str:
        if not self._active_incidents:
            return ""

        parts = []
        for index, incident in enumerate(self._active_incidents[-3:], start=1):
            parts.append(
                f"事件 {index}（{incident['created_at']} / 緊急程度 {incident['severity']}）\n"
                f"AI 分析摘要：{_truncate_text(incident['ai_text'], 350)}\n"
                f"原始錯誤日誌：{_truncate_text(incident['log_text'], 280)}"
            )
        return "根據以下 Bot 未清除錯誤彙整，請診斷並嘗試修復問題。\n\n" + "\n\n".join(parts)

    def clear_summary(self, cleared_by: str) -> discord.Embed:
        self._active_incidents.clear()
        # 清除 .env 中的訊息 ID，因為訊息內容已經改變
        _clear_message_state()
        embed = discord.Embed(
            title="✅ Bot 日誌錯誤已清空",
            description="目前沒有待處理的錯誤彙整。新錯誤發生時會更新同一則訊息。",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=f"由 {cleared_by} 清空")
        return embed

    def _build_summary_embed(self) -> discord.Embed:
        incident_count = len(self._active_incidents)
        latest = self._active_incidents[-_MAX_EMBED_INCIDENTS:]
        embed = discord.Embed(
            title="🚨 Bot 日誌錯誤彙整",
            description=(
                f"目前累積 **{incident_count}** 筆未清除事件。\n"
                "新的重大錯誤會更新這則訊息，而不是持續新增新訊息。"
            ),
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )

        for index, incident in enumerate(latest, start=max(1, incident_count - len(latest) + 1)):
            log_excerpt = _truncate_text(incident["log_text"], 280)
            ai_excerpt = _truncate_text(incident["ai_text"], 420)
            embed.add_field(
                name=f"【事件 #{index}】{incident['created_at']} · 緊急程度 {incident['severity']}",
                value=(
                    f"**錯誤段**\n```\n{log_excerpt}\n```\n"
                    f"**AI 總結**\n{ai_excerpt}"
                )[:1024],
                inline=False,
            )

        embed.set_footer(text="事件驅動監控 · 修復後可按下「已修復，清空」")
        return embed

    async def _upsert_summary_message(self, channel: discord.TextChannel):
        embed = self._build_summary_embed()
        
        # ✅ 使用已註冊的全局視圖（而非每次都新建）
        view = None
        if self.cog_instance and self.cog_instance._global_view:
            view = self.cog_instance._global_view
            # 更新視圖的引用，確保指向最新的引擎狀態
            view._engine = self
            view._runner = self.shell_runner
            view._channel = channel

        async with self._message_lock:
            if self._summary_message and self._summary_message.channel.id == channel.id:
                try:
                    await self._summary_message.edit(embed=embed, view=view)
                    return
                except discord.NotFound:
                    self._summary_message = None

            # 創建新訊息並保存 ID 到 .env
            self._summary_message = await channel.send(
                embed=embed,
                view=view,
                silent=True,
            )
            _save_message_state(self._summary_message.id)


# ══════════════════════════════════════════════════════════════════════════════
# LogMonitor — Discord Cog
# ══════════════════════════════════════════════════════════════════════════════

class LogMonitor(commands.Cog):
    """日誌事件監控 Cog（事件驅動）。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._llm = LLMClient()

        # 嘗試載入 ShellAgentRunner（需要 agent_tools）
        _shell_runner = None
        try:
            from cogs.common.shell_agent import ShellAgentRunner
            import agent_tools as _at
            _shell_runner = ShellAgentRunner(_at)
            logger.info("[LogMonitor] ✅ ShellAgentRunner 已載入，支援自動修復")
        except Exception as e:
            logger.warning(f"[LogMonitor] ShellAgentRunner 未載入（{e}），自動修復按鈕不可用")

        self._engine = LogMonitorEngine(bot, self._llm, shell_runner=_shell_runner)
        self._engine.cog_instance = self  # ✅ 設定引用，讓 engine 能訪問全局視圖
        self._task: Optional[asyncio.Task] = None
        self._global_view = None  # 全局視圖實例，用於持久化按鈕
        
        # ✅ 直接在 __init__ 時註冊持久化視圖（而不是等待 cog_load）
        try:
            if _ALERT_CHANNEL_ID and _ALERT_CHANNEL_ID > 0:
                # 建立模板視圖實例
                self._global_view = LogMonitorSummaryView(self._engine, self._engine.shell_runner, None)
                self.bot.add_view(self._global_view)
                logger.info(f"[LogMonitor] ✅ 持久化視圖已在 __init__ 註冊到 bot（頻道 {_ALERT_CHANNEL_ID}）")
            else:
                logger.warning(f"[LogMonitor] ⚠️ _ALERT_CHANNEL_ID 無效或未設定 ({_ALERT_CHANNEL_ID})")
        except Exception as e:
            logger.error(f"[LogMonitor] ❌ 在 __init__ 中視圖註冊失敗: {e}", exc_info=True)
        
        logger.info("✅ LogMonitor Cog 已初始化")

    async def cog_load(self):
        """Cog 載入時啟動監控。"""
        if _ALERT_CHANNEL_ID and _ALERT_CHANNEL_ID > 0:
            self._task = asyncio.create_task(self._engine.start())
            logger.info(f"[LogMonitor] 監控已在 cog_load 中啟動（通知頻道 {_ALERT_CHANNEL_ID}）")
        else:
            logger.warning("[LogMonitor] 通知頻道未設定，監控未啟動")

    async def cog_unload(self):
        if self._task:
            self._engine.pause()
            self._task.cancel()

    def _check_perm(self, interaction: discord.Interaction) -> bool:
        return _has_admin_access(interaction.user)

    @app_commands.command(name="logmonitor", description="日誌監控控制（管理員限定）")
    @app_commands.describe(action="pause=暫停 / resume=恢復 / status=狀態 / test=測試")
    @app_commands.choices(action=[
        app_commands.Choice(name="status",  value="status"),
        app_commands.Choice(name="pause",   value="pause"),
        app_commands.Choice(name="resume",  value="resume"),
        app_commands.Choice(name="test",    value="test"),
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
            incident_len = len(self._engine._active_incidents)
            embed   = discord.Embed(
                title="📊 日誌監控狀態",
                color=discord.Color.green() if (running and enabled) else discord.Color.orange(),
            )
            embed.add_field(name="監控",     value="✅ 運行中" if (running and enabled) else "⏸️ 已暫停", inline=True)
            embed.add_field(name="🔕 靜音送出", value="已啟用", inline=True)
            embed.add_field(name="監控服務", value="\n".join(_SERVICES),                                  inline=True)
            embed.add_field(name="緩衝行數", value=str(buf_len),                                          inline=True)
            embed.add_field(name="未清除事件", value=str(incident_len),                                   inline=True)
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

        elif action == "test":
            await interaction.response.defer(ephemeral=True)
            fake_lines = [
                "[TEST] ERROR: 這是一筆測試錯誤日誌 — LogMonitor test triggered",
                "[TEST] Traceback (most recent call last):",
                "[TEST]   File 'cogs/common/AI.py', line 99, in run",
                "[TEST] RuntimeError: 模擬錯誤：用於驗證 LogMonitor 分析流程",
            ]
            # 繞過冷却，直接呼叫分析
            self._engine._cooldowns.clear()
            asyncio.create_task(self._engine._analyze_and_notify(fake_lines))
            await interaction.followup.send(
                "🧪 測試觸發成功！\n"
                "已注入假錯誤日誌並呼叫 LLM 分析，"
                f"結果將送至 <#{_ALERT_CHANNEL_ID}>（約 5-15 秒後出現）。",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    cog = LogMonitor(bot)
    await bot.add_cog(cog)
    
    # ℹ️ 視圖已在 Cog.__init__() 中註冊，此處無需重複註冊
    # 但我們驗證視圖是否成功創建
    if cog._global_view:
        print(f"[LogMonitor] ✅ 視圖已正確初始化並註冊（custom_ids: {[b.custom_id for b in cog._global_view.children]}）")
    else:
        print(f"[LogMonitor] ⚠️ 警告：視圖未被創建（_ALERT_CHANNEL_ID={_ALERT_CHANNEL_ID}）")
