#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VM 自我修復守護程式 (VM Self-Healing Daemon)

取代原本 GitHub Actions 主導的 debug 流程，改為 VM 內部自主：
1. 監控 systemd journal 錯誤日誌
2. 分級修復 (L1 自動 / L2 AI 輔助 / L3 通知人工)
3. 自動備份 → 修復 → 驗證 → 回滾
4. Git auto commit + push
5. Discord 通知

Usage:
    python3 scripts/auto_self_heal.py          # 單次執行
    python3 scripts/auto_self_heal.py --watch  # 持續監控模式
"""

import os
import sys
import re
import json
import asyncio
import subprocess
import shutil
import argparse
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# ─── 專案根目錄 (需在 shared import 之前加入 sys.path) ─────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

# ─── 路徑設定 ────────────────────────────────────────────────
BACKUP_DIR = PROJECT_ROOT / "archive" / "self_heal_backups"
FIXES_DIR = PROJECT_ROOT / "archive" / "self_heal_fixes"
MEMORY_DIR = PROJECT_ROOT / "data"
MEMORY_FILE = MEMORY_DIR / "self_heal_agent_memory.json"
STATE_FILE = PROJECT_ROOT / "data" / "self_heal_state.json"

from shared.utils.llm_text_router import GROQ_MODEL

# ─── 工具模組 ────────────────────────────────────────────────
from utils.nvidia_ai import call_nvidia_ai

# ─── 導入 ClaudeCodeAgent (完整工具集: read/write/edit/list/glob/bash/task)
try:
    from cogs.common.claude_code import (
        ClaudeCodeAgent,
        WORK_DIR as CLAUDE_WORK_DIR,
        NVIDIA_API_KEY as CLAUDE_NVIDIA_KEY,
    )
    CLAUDE_CODE_AVAILABLE = True
except ImportError as e:
    _log(f"⚠️ 無法導入 ClaudeCodeAgent: {e}", "WARN")
    CLAUDE_CODE_AVAILABLE = False
    CLAUDE_WORK_DIR = PROJECT_ROOT
    CLAUDE_NVIDIA_KEY = os.getenv("NVIDIA_API_KEY", "")

# ─── 防呆設定 ────────────────────────────────────────────────
MAX_AGENT_RETRIES = int(os.getenv("SELF_HEAL_MAX_RETRIES", "5"))  # 連續失敗 N 次回滾
ROLLBACK_BRANCH = os.getenv("SELF_HEAL_ROLLBACK_BRANCH", "main")  # 回滾目標分支
STABLE_COMMIT_FILE = PROJECT_ROOT / "data" / "self_heal_stable_commit.txt"

# ─── 錯誤分級 ────────────────────────────────────────────────
# L1: 可直接自動修復的錯誤類型
L1_PATTERNS = {
    "import_error": {
        "pattern": r"ImportError: No module named ['\"](.+?)['\"]",
        "description": "缺少模組匯入",
    },
    "syntax_error": {
        "pattern": r"SyntaxError: (.+)",
        "description": "語法錯誤",
    },
    "indentation_error": {
        "pattern": r"IndentationError: (.+)",
        "description": "縮排錯誤",
    },
    "name_error": {
        "pattern": r"NameError: name ['\"](.+?)['\"] is not defined",
        "description": "名稱未定義",
    },
    "attribute_error": {
        "pattern": r"AttributeError: ['\"](.+?)['\"] object has no attribute ['\"](.+?)['\"]",
        "description": "屬性不存在",
    },
    "file_not_found": {
        "pattern": r"FileNotFoundError: \[Errno 2\] No such file or directory: ['\"](.+?)['\"]",
        "description": "檔案不存在",
    },
    "module_not_found": {
        "pattern": r"ModuleNotFoundError: No module named ['\"](.+?)['\"]",
        "description": "模組未安裝",
    },
    "key_error": {
        "pattern": r"KeyError: ['\"](.+?)['\"]",
        "description": "鍵值錯誤",
    },
    "type_error": {
        "pattern": r"TypeError: (.+)",
        "description": "型別錯誤",
    },
    "value_error": {
        "pattern": r"ValueError: (.+)",
        "description": "數值錯誤",
    },
    "zero_division": {
        "pattern": r"ZeroDivisionError: (.+)",
        "description": "除以零",
    },
    "index_error": {
        "pattern": r"IndexError: (.+)",
        "description": "索引錯誤",
    },
    "runtime_error": {
        "pattern": r"RuntimeError: (.+)",
        "description": "執行期錯誤",
    },
    "os_error": {
        "pattern": r"OSError: (.+)",
        "description": "系統呼叫錯誤",
    },
    "permission_error": {
        "pattern": r"PermissionError: \[Errno 13\] (.+)",
        "description": "權限錯誤",
    },
    "connection_error": {
        "pattern": r"ConnectionError: (.+)",
        "description": "連線錯誤",
    },
    "timeout_error": {
        "pattern": r"TimeoutError: (.+)",
        "description": "逾時錯誤",
    },
    "json_decode_error": {
        "pattern": r"json\.decoder\.JSONDecodeError: (.+)",
        "description": "JSON 解析錯誤",
    },
    "unicode_decode_error": {
        "pattern": r"UnicodeDecodeError: (.+)",
        "description": "編碼解碼錯誤",
    },
    "discord_not_found": {
        "pattern": r"discord\.(NotFound|HTTPException): (\d+)",
        "description": "Discord API 404",
    },
    "discord_forbidden": {
        "pattern": r"discord\.Forbidden: (\d+)",
        "description": "Discord 權限不足",
    },
    # Benign patterns - ignore with backoff (no actual fix needed)
    "gemini_quota": {
        "pattern": r"(google api 錯誤\s*429|quota exceeded.*gemini|generativelanguage\.googleapis\.com.*429|generatecontent.*free.?tier.*limit)",
        "description": "Gemini API 配額耗盡",
        "action": "ignore_with_backoff",
        "backoff_seconds": 300,
    },
    "discord_gateway_reconnect": {
        "pattern": r"(\[discord\]\s*gateway\s*disconnected|\[discord\]\s*session\s*resumed|on_disconnect\s+called|on_resumed\s+called)",
        "description": "Discord gateway 自動重連",
        "action": "ignore_with_backoff",
        "backoff_seconds": 60,
    },
    "tunnel_url_failure": {
        "pattern": r"(無法獲取隧道 url|tunnel url.*失敗)",
        "description": "隧道 URL 獲取失敗",
        "action": "ignore_with_backoff",
        "backoff_seconds": 120,
    },
}

# L2: 需要 AI 輔助分析的錯誤
L2_PATTERNS = {
    "logic_error": {
        "pattern": r"(logic error|unexpected behavior|wrong result|incorrect calculation)",
        "description": "邏輯錯誤",
    },
    "api_change": {
        "pattern": r"(deprecated|removed|moved|renamed|no longer supported)",
        "description": "API 變更",
    },
    "race_condition": {
        "pattern": r"(race condition|deadlock|concurrent|thread-safe|async issue)",
        "description": "競爭條件",
    },
    "memory_leak": {
        "pattern": r"(memory leak|out of memory|OOM|memory error)",
        "description": "記憶體洩漏",
    },
    "complex_error": {
        "pattern": r"(complex|nested|recursive|circular|infinite)",
        "description": "複雜錯誤",
    },
}

# L3: 需要人工介入的錯誤
L3_PATTERNS = {
    "database_corruption": {
        "pattern": r"(database corruption|database integrity|sqlite3\.(DatabaseError|IntegrityError)|OperationalError)",
        "description": "資料庫損毀",
    },
    "security_issue": {
        "pattern": r"(security|unauthorized|forbidden|access denied|permission denied|hack|intrusion)",
        "description": "安全問題",
    },
    "config_corruption": {
        "pattern": r"(config.*corrupt|config.*invalid|config.*parse|malformed config)",
        "description": "配置檔損毀",
    },
    "hardware_failure": {
        "pattern": r"(hardware|disk failure|I/O error|disk full|no space left)",
        "description": "硬體故障",
    },
    "network_outage": {
        "pattern": r"(network outage|DNS resolution|host unreachable|no route to host)",
        "description": "網路中斷",
    },
    "unknown_error": {
        "pattern": r"(unknown error|unhandled exception|fatal error|critical failure)",
        "description": "未知錯誤",
    },
}

# 噪音過濾模式（跳過這些日誌）
NOISE_PATTERNS = [
    r"auto_self_heal",
    r"self.heal",
    r"auto-debug",
    r"auto_error_detector",
    r"websocket.*close",
    r"shard.*disconnect",
    r"heartbeat.*ack",
    r"rate limit",
    r"429",
    r"Unknown interaction",
    r"error code:\s*10062",
    # Benign patterns that should be ignored (Gemini quota, Discord gateway reconnect, tunnel issues)
    r"google api 錯誤\s*429",
    r"google api error\s*429",
    r"quota exceeded.*gemini",
    r"generativelanguage\.googleapis\.com.*429",
    r"generatecontent.*free.?tier.*limit",
    r"\[discord\]\s*gateway\s+disconnected",
    r"\[discord\]\s*session\s+resumed",
    r"on_disconnect\s+called",
    r"on_resumed\s+called",
    r"無法獲取隧道 url",
    r"tunnel url.*失敗",
]

# ─── 工具函式 ────────────────────────────────────────────────


def _load_env():
    """載入 .env 檔案"""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                os.environ.setdefault(key, value)


def _log(msg: str, level: str = "INFO"):
    """統一日誌輸出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{timestamp}] [{level}] {msg}", flush=True)
    except UnicodeEncodeError:
        # Windows cp950 兼容：移除無法編碼的字符
        safe_msg = msg.encode("cp950", errors="ignore").decode("cp950")
        print(f"[{timestamp}] [{level}] {safe_msg}", flush=True)


def _load_state() -> dict:
    """載入狀態檔案"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_check": {}, "incidents": [], "fix_history": [], "agent_failures": 0, "last_stable_commit": ""}


def _save_state(state: dict):
    """儲存狀態檔案"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_stable_commit() -> Optional[str]:
    """獲取最後穩定的 commit hash"""
    # 1. 先嘗試從狀態檔讀取
    state = _load_state()
    commit = state.get("last_stable_commit")
    if commit:
        return commit
    # 2. 再嘗試讀取獨立檔案
    if STABLE_COMMIT_FILE.exists():
        try:
            return STABLE_COMMIT_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    # 3. 最後回退到 origin/main
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def save_stable_commit(commit_hash: str):
    """記錄穩定的 commit hash（服務正常運行時調用）"""
    state = _load_state()
    state["last_stable_commit"] = commit_hash
    _save_state(state)
    STABLE_COMMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    STABLE_COMMIT_FILE.write_text(commit_hash, encoding="utf-8")
    _log(f"💾 已記錄穩定 commit: {commit_hash[:8]}", "INFO")


def rollback_to_stable_commit(service: str) -> bool:
    """強制回滾到最後穩定 commit，並重啟服務"""
    stable_commit = get_stable_commit()
    if not stable_commit:
        _log("❌ 找不到穩定 commit，無法回滾", "ERROR")
        return False

    _log(f"🔄 觸發防呆回滾到穩定 commit: {stable_commit[:8]}", "WARN")

    try:
        # 硬重置到穩定 commit
        result = subprocess.run(
            ["git", "reset", "--hard", stable_commit],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            _log(f"❌ git reset 失敗: {result.stderr[:300]}", "ERROR")
            return False

        _log(f"✅ 已重置到穩定 commit: {stable_commit[:8]}", "INFO")

        # 重啟服務
        fix_executor = FixExecutor()
        return fix_executor._restart_service(service)

    except Exception as e:
        _log(f"❌ 回滾異常: {e}", "ERROR")
        return False


def record_agent_failure():
    """記錄 Agent 失敗次數"""
    state = _load_state()
    state["agent_failures"] = state.get("agent_failures", 0) + 1
    _save_state(state)
    return state["agent_failures"]


def reset_agent_failures():
    """重置 Agent 失敗計數（修復成功時調用）"""
    state = _load_state()
    state["agent_failures"] = 0
    _save_state(state)
    # 同時更新穩定 commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            save_stable_commit(result.stdout.strip())
    except Exception:
        pass


def _normalize_timestamp(ts_str: str) -> Optional[datetime]:
    """標準化時間戳字串為 datetime"""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%b %d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if fmt == "%b %d %H:%M:%S":
                dt = dt.replace(year=datetime.now().year)
            return dt
        except ValueError:
            continue
    return None


def _is_noise(line: str) -> bool:
    """檢查是否為噪音日誌"""
    return any(re.search(p, line, re.IGNORECASE) for p in NOISE_PATTERNS)


def _extract_file_path_from_traceback(lines: List[str]) -> Optional[str]:
    """從 traceback 中提取出錯的檔案路徑"""
    for line in lines:
        match = re.search(r'File\s+"([^"]+\.py)"', line)
        if match:
            path = match.group(1)
            # 嘗試轉換為專案內的相對路徑
            if PROJECT_ROOT.as_posix() in path:
                rel_path = os.path.relpath(path, PROJECT_ROOT.as_posix())
                return rel_path.replace("\\", "/")
            return path
    return None


def _extract_error_line_from_traceback(lines: List[str]) -> Optional[int]:
    """從 traceback 中提取出錯的行號"""
    for line in lines:
        match = re.search(r"line\s+(\d+)", line)
        if match:
            return int(match.group(1))
    return None


# ─── 錯誤分類 ────────────────────────────────────────────────


def classify_error(error_text: str) -> Tuple[str, str, str]:
    """
    分類錯誤等級。

    Returns:
        (level, error_type, description)
        level: "L1", "L2", "L3"
    """
    # 先檢查 L3（最高優先）
    for err_type, info in L3_PATTERNS.items():
        if re.search(info["pattern"], error_text, re.IGNORECASE):
            return ("L3", err_type, info["description"])

    # 再檢查 L2
    for err_type, info in L2_PATTERNS.items():
        if re.search(info["pattern"], error_text, re.IGNORECASE):
            return ("L2", err_type, info["description"])

    # 最後檢查 L1
    for err_type, info in L1_PATTERNS.items():
        if re.search(info["pattern"], error_text, re.IGNORECASE):
            return ("L1", err_type, info["description"])

    # 預設為 L3（無法分類的錯誤需要人工確認）
    return ("L3", "unclassified", "無法分類的錯誤")


# ─── 日誌監控 ────────────────────────────────────────────────


def read_journal(service: str, lines: int = 100) -> List[str]:
    """讀取 systemd journal 日誌"""
    try:
        cmd = [
            "/usr/bin/journalctl",
            "-u",
            service,
            "-n",
            str(lines),
            "--no-pager",
            "-o",
            "short-iso",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.splitlines()
        else:
            _log(f"journalctl 失敗 ({service}): {result.stderr.strip()}", "WARN")
            return []
    except FileNotFoundError:
        _log("找不到 journalctl，可能不在 VM 上", "WARN")
        return []
    except subprocess.TimeoutExpired:
        _log(f"讀取 journal {service} 逾時", "WARN")
        return []
    except Exception as e:
        _log(f"讀取 journal 異常 ({service}): {e}", "WARN")
        return []


def collect_errors(services: List[str], since_minutes: int = 10) -> List[dict]:
    """收集各服務的錯誤日誌"""
    errors = []
    state = _load_state()
    last_check = state.get("last_check", {})
    now = datetime.now().isoformat()

    for service in services:
        lines = read_journal(service, lines=200)
        if not lines:
            continue

        for line in lines:
            if _is_noise(line):
                continue

            # 檢查是否包含錯誤關鍵字
            if not re.search(
                r"(Traceback|Error|Exception|CRITICAL|FATAL|failed|traceback)",
                line,
                re.IGNORECASE,
            ):
                continue

            # 提取時間戳
            ts_match = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line)
            if not ts_match:
                continue

            ts_str = ts_match.group(1)
            ts = _normalize_timestamp(ts_str)
            if not ts:
                continue

            # 檢查是否在時間範圍內
            if (datetime.now() - ts).total_seconds() > since_minutes * 60:
                continue

            # 檢查是否已經處理過
            last_ts = last_check.get(service)
            if last_ts:
                last_dt = _normalize_timestamp(last_ts)
                if last_dt and ts <= last_dt:
                    continue

            errors.append(
                {
                    "service": service,
                    "timestamp": ts_str,
                    "message": line.strip(),
                    "raw": line,
                }
            )

    # 更新最後檢查時間（僅在有新錯誤時寫入，以減少不必要的 I/O）
    if errors:
        for service in services:
            state.setdefault("last_check", {})[service] = now
        _save_state(state)

    return errors


# ─── 備份系統 ────────────────────────────────────────────────


def backup_file(file_path: str) -> Optional[str]:
    """備份檔案，回傳備份路徑"""
    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = PROJECT_ROOT / file_path

    if not abs_path.exists():
        _log(f"備份目標不存在: {abs_path}", "WARN")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rel_path = os.path.relpath(abs_path, PROJECT_ROOT)
    safe_name = rel_path.replace("\\", "_").replace("/", "_").replace(".", "_")
    backup_path = BACKUP_DIR / f"{timestamp}_{safe_name}.bak"

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(abs_path, backup_path)
    _log(f"✅ 已備份 {rel_path} → {backup_path}", "INFO")
    return str(backup_path)


def restore_backup(backup_path: str, target_path: str) -> bool:
    """從備份還原檔案"""
    backup = Path(backup_path)
    target = Path(target_path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target_path

    if not backup.exists():
        _log(f"備份檔案不存在: {backup}", "ERROR")
        return False

    shutil.copy2(backup, target)
    _log(f"✅ 已還原 {backup} → {target}", "INFO")
    return True


def list_backups(file_path: str, max_results: int = 5) -> List[str]:
    """列出某檔案的最新備份"""
    rel_path = (
        os.path.relpath(Path(file_path), PROJECT_ROOT)
        if Path(file_path).is_absolute()
        else file_path
    )
    safe_name = rel_path.replace("\\", "_").replace("/", "_").replace(".", "_")

    backups = sorted(BACKUP_DIR.glob(f"*_{safe_name}.bak"), reverse=True)
    return [str(b) for b in backups[:max_results]]


# ─── Agent 修復引擎 (取代 L1/L2) ──────────────────────────────


class AgentFixEngine:
    """
    統一修復引擎：使用 ClaudeCodeAgent 進行完整的 ReAct 循環修復
    - 7 工具: read, write, edit, list, glob, bash, task
    - 完整代碼搜尋、編輯、測試、驗證能力
    - 內建失敗計數與自動回滾機制
    """

    def __init__(self, fix_executor: "FixExecutor", notifier: "DiscordNotifier"):
        self.fix_executor = fix_executor
        self.notifier = notifier
        self.agent = None
        self._init_agent()

    def _init_agent(self):
        """初始化 ClaudeCodeAgent"""
        if not CLAUDE_CODE_AVAILABLE:
            _log("⚠️ ClaudeCodeAgent 不可用，將使用降級模式", "WARN")
            return

        if not CLAUDE_NVIDIA_KEY:
            _log("⚠️ NVIDIA_API_KEY 未設定，ClaudeCodeAgent 無法啟動", "WARN")
            return

        try:
            # 建立 agent（無 Discord 互動，使用內部 callback 收集進度）
            self.agent = ClaudeCodeAgent(user_id=0, channel_id=0)
            self.agent.progress_callback = self._collect_progress
            self.progress_log = []
            _log("🤖 AgentFixEngine 初始化完成 (ClaudeCodeAgent)", "INFO")
        except Exception as e:
            _log(f"❌ Agent 初始化失敗: {e}", "ERROR")
            self.agent = None

    def _collect_progress(self, text: str):
        self.progress_log.append(text)

    def is_available(self) -> bool:
        return self.agent is not None

    async def diagnose_and_fix(self, error_info: dict, error_text: str, file_path: str, service: str) -> dict:
        """
        執行完整的診斷+修復循環
        返回: {"success": bool, "root_cause": str, "fixes_applied": list, "verification": str, "progress_log": list}
        """
        if not self.is_available():
            return {"success": False, "reason": "agent_unavailable", "progress_log": []}

        _log(f"🤖 AgentFixEngine 開始修復: {service}", "INFO")

        # 構建包含完整上下文的修復提示
        prompt = self._build_diagnosis_prompt(error_info, error_text, file_path, service)

        # 執行 agentic loop
        try:
            reply = await self.agent.run(prompt)
        except Exception as e:
            _log(f"❌ Agent 執行異常: {e}", "ERROR")
            return {"success": False, "reason": f"agent_exception: {e}", "progress_log": self.progress_log}

        # 解析結果
        return self._parse_repair_result(reply, service)

    def _build_diagnosis_prompt(self, error_info: dict, error_text: str, file_path: str, service: str) -> str:
        """構建包含完整上下文的修復提示"""
        return f"""你是 KKGroup Discord Bot 系統的自動修復專家（Claude Code 模式）。

## 錯誤資訊
- 服務: {service}
- 錯誤日誌:
{error_text[:4000]}
- 疑似檔案: {file_path}

## 系統環境
- 專案根目錄: {CLAUDE_WORK_DIR}
- 三服務: bot.service, shopbot.service, uibot.service
- 技術棧: Python 3.11 + Discord.py 2.0 + SQLite (WAL模式) + systemd
- 記憶體: e2-micro (1GB RAM + 4GB swap)

## 你的任務
1. **讀取**疑似檔案與相關代碼，理解錯誤根因 (用 read/glob 工具)
2. **搜尋**相關模組（用 glob/rg 工具），找出所有受影響處
3. **編輯修復**代碼（用 edit/write 工具，精確字串替換）
4. **驗證**修復：執行測試或重啟服務檢查狀態 (用 bash 工具)
5. **輸出**結構化總結

## 可用工具
- read <path>: 讀取檔案
- write <path> <content>: 寫入檔案
- edit <path> <old_str> <new_str>: 精確編輯
- list <path>: 列出目錄
- glob <pattern>: 搜尋檔案
- bash <command>: 執行指令 (受白名單限制)
- task <description>: 啟動子任務

## 限制
- 禁止修改 .env、敏感設定檔
- 禁止執行危險指令（rm -rf, shutdown, reboot, git push main 等）
- bash 指令需通過白名單驗證
- 修復後必須用 `systemctl is-active {service}` 驗證服務啟動

## 輸出格式（任務完成時必須包含）
任務完成：
- 根本原因: <一句話>
- 修復檔案: <檔案路徑列表，逗號分隔>
- 修復摘要: <做了什麼>
- 驗證結果: systemctl is-active {service} -> active/inactive
"""

    def _parse_repair_result(self, reply: str, service: str) -> dict:
        """解析 agent 回覆，提取結構化結果"""
        result = {
            "success": False,
            "root_cause": "",
            "fixes_applied": [],
            "verification": "",
            "raw_reply": reply[:3000],
            "progress_log": self.progress_log.copy(),
        }

        if "任務完成" in reply:
            result["success"] = True
            lines = reply.split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith("根本原因:") or line.startswith("- 根本原因:"):
                    result["root_cause"] = line.split(":", 1)[1].strip().lstrip("- ")
                elif line.startswith("修復檔案:") or line.startswith("- 修復檔案:"):
                    files_str = line.split(":", 1)[1].strip()
                    result["fixes_applied"] = [f.strip() for f in files_str.split(",") if f.strip()]
                elif line.startswith("驗證結果:") or line.startswith("- 驗證結果:"):
                    result["verification"] = line.split(":", 1)[1].strip()
                elif line.startswith("修復摘要:") or line.startswith("- 修復摘要:"):
                    result["fix_summary"] = line.split(":", 1)[1].strip()

        return result


# ─── 修復執行器 ──────────────────────────────────────────────


class FixExecutor:
    """執行修復操作（備份 → 修復 → 驗證 → 回滾）"""

    def __init__(self):
        self.fix_history = []

    def apply_fix(self, fix_data: dict, error_info: dict) -> bool:
        """執行修復"""
        fix_type = fix_data.get("fix_type", "")
        fix_target = fix_data.get("fix_target", "")
        fix_code = fix_data.get("fix_code", "")
        fix_command = fix_data.get("fix_command", "")

        _log(f"🔧 執行修復: type={fix_type}, target={fix_target}", "INFO")

        # 備份
        if fix_type == "modify_file" and fix_target:
            backup_path = backup_file(fix_target)
            if not backup_path:
                _log("⚠️ 備份失敗，仍嘗試修復", "WARN")

        success = False
        action_taken = ""

        try:
            if fix_type == "modify_file" and fix_target and fix_code:
                success = self._apply_code_fix(fix_target, fix_code)
                action_taken = f"修改檔案 {fix_target}"

            elif fix_type == "install_package" and fix_command:
                success = self._run_command(fix_command)
                action_taken = f"執行命令: {fix_command}"

            elif fix_type == "restart_service":
                service = error_info.get("service", "bot.service")
                success = self._restart_service(service)
                action_taken = f"重啟服務 {service}"

            elif fix_type == "other" and fix_command:
                success = self._run_command(fix_command)
                action_taken = f"執行命令: {fix_command}"

            else:
                _log(f"❌ 未知的修復類型: {fix_type}", "ERROR")
                success = False
                action_taken = f"未知修復類型: {fix_type}"

        except Exception as e:
            _log(f"❌ 修復執行異常: {e}", "ERROR")
            success = False

        # 記錄修復歷史
        record = {
            "timestamp": datetime.now().isoformat(),
            "error": error_info.get("message", ""),
            "service": error_info.get("service", ""),
            "fix_type": fix_type,
            "action": action_taken,
            "success": success,
            "fix_data": fix_data,
        }
        self.fix_history.append(record)

        # 儲存到狀態
        state = _load_state()
        state.setdefault("fix_history", []).append(record)
        _save_state(state)

        return success

    def _apply_code_fix(self, target_path: str, fix_code: str) -> bool:
        """套用代碼修復（含完整檔案 AST 校驗：AI 給片段會被拒並還原）"""
        import ast as _ast

        abs_path = Path(target_path)
        if not abs_path.is_absolute():
            abs_path = PROJECT_ROOT / target_path

        if not abs_path.exists():
            _log(f"❌ 目標檔案不存在: {abs_path}", "ERROR")
            return False

        # 讀原檔：校驗基準 + 還原來源
        try:
            original = abs_path.read_text(encoding="utf-8")
        except Exception as e:
            _log(f"❌ 無法讀取原檔 {abs_path}: {e}", "ERROR")
            return False

        def _top_level_defs(src: str) -> int:
            try:
                return sum(
                    1
                    for n in _ast.parse(src).body
                    if isinstance(
                        n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)
                    )
                )
            except SyntaxError:
                return -1

        # 先驗證 fix_code 是否為合法 Python 代碼（在寫入之前）
        try:
            parsed_fix = _ast.parse(fix_code)
            after = _top_level_defs(fix_code)
            if after < 0:
                _log(
                    "❌ 修復代碼無法 ast.parse（AI 回應可能為片段），拒絕寫入", "ERROR"
                )
                return False
        except SyntaxError as e:
            _log(f"❌ 修復代碼語法錯誤: {e}", "ERROR")
            return False

        # 再驗證不會導致頂層定義數顯著減少（防止 AI 只回傳片段）
        before = _top_level_defs(original)
        if before >= 0 and after < max(1, before // 2):
            _log(f"❌ 頂層定義數 {before}->{after} 驟減（疑似片段），拒絕寫入", "ERROR")
            return False

        # 所有驗證通過，才寫入檔案
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(fix_code)
        except Exception as e:
            _log(f"❌ 寫入檔案失敗: {e}", "ERROR")
            return False

        _log(f"✅ 已寫入並通過 AST 校驗: {abs_path} (定義 {before}->{after})", "INFO")
        return True

    def _run_command(self, command: str) -> bool:
        """執行「受白名單限制」的命令；不在白名單者一律拒絕（降級人工/L3），絕不跑任意 shell。

        白名單：
          - pip install <已知套件>
          - sudo systemctl restart {bot,shopbot,uibot,kkgroup-api}.service
        """
        import shlex

        try:
            tokens = shlex.split(command)
        except ValueError as e:
            _log(f"❌ 命令剖析失敗: {e}", "ERROR")
            return False
        if not tokens:
            _log("❌ 空命令", "ERROR")
            return False

        ALLOWED_PKGS = {
            "discord.py",
            "aiohttp",
            "requests",
            "python-dotenv",
            "pytz",
            "google-cloud-compute",
            "gitpython",
        }
        ALLOWED_SERVICES = {
            "bot.service",
            "shopbot.service",
            "uibot.service",
            "kkgroup-api.service",
        }

        # 白名單 1：pip / pip3 install <pkg>
        if tokens[0] in ("pip", "pip3") and len(tokens) >= 3 and tokens[1] == "install":
            pkg = tokens[2].split("[", 1)[0].split("==")[0].split(">=", 1)[0].lower()
            if pkg not in ALLOWED_PKGS:
                _log(f"❌ pip install 拒絕非白名單套件: {pkg}（降級人工處理）", "WARN")
                return False
            return self._exec_tokens(tokens)

        # 白名單 2：sudo systemctl restart <service>
        if (
            len(tokens) == 4
            and tokens[0] == "sudo"
            and tokens[1] == "systemctl"
            and tokens[2] == "restart"
            and tokens[3] in ALLOWED_SERVICES
        ):
            return self._exec_tokens(tokens)

        _log(f"❌ 命令不在白名單，拒絕執行（降級人工處理）: {command}", "WARN")
        return False

    def _exec_tokens(self, tokens: list) -> bool:
        """以 list 形式執行白名單命令（shell=False）"""
        try:
            result = subprocess.run(
                tokens,
                shell=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                _log(f"✅ 命令執行成功: {' '.join(tokens)}", "INFO")
                if result.stdout:
                    _log(f"輸出: {result.stdout[:500]}", "INFO")
                return True
            _log(
                f"❌ 命令執行失敗 (code={result.returncode}): {result.stderr[:500]}",
                "ERROR",
            )
            return False
        except subprocess.TimeoutExpired:
            _log(f"❌ 命令逾時: {' '.join(tokens)}", "ERROR")
            return False
        except Exception as e:
            _log(f"❌ 命令執行異常: {e}", "ERROR")
            return False

    def _restart_service(self, service: str) -> bool:
        """重啟 systemd 服務"""
        _log(f"🔄 重啟服務: {service}", "INFO")
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                _log(f"✅ 服務 {service} 重啟成功", "INFO")
                return True
            else:
                _log(f"❌ 服務重啟失敗: {result.stderr[:300]}", "ERROR")
                return False
        except Exception as e:
            _log(f"❌ 重啟異常: {e}", "ERROR")
            return False

    def verify_fix(self, service: str, wait_seconds: int = 10) -> bool:
        """驗證修復後服務是否正常"""
        _log(f"🔍 驗證修復: 等待 {wait_seconds} 秒後檢查 {service}", "INFO")
        time.sleep(wait_seconds)

        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=10,
            )
            is_active = result.stdout.strip() == "active"
            _log(
                f"{'✅' if is_active else '❌'} 服務狀態: {result.stdout.strip()}",
                "INFO",
            )
            return is_active
        except Exception as e:
            _log(f"❌ 驗證異常: {e}", "ERROR")
            return False

    def rollback(self, error_info: dict) -> bool:
        """回滾最近的修復"""
        if not self.fix_history:
            _log("⚠️ 沒有修復歷史可回滾", "WARN")
            return False

        last_fix = self.fix_history[-1]
        fix_target = last_fix.get("fix_data", {}).get("fix_target", "")

        if not fix_target:
            _log("⚠️ 沒有修復目標可回滾", "WARN")
            return False

        # 找最新的備份
        backups = list_backups(fix_target, max_results=1)
        if not backups:
            _log(f"⚠️ 找不到 {fix_target} 的備份", "WARN")
            return False

        _log(f"🔄 回滾: {backups[0]} → {fix_target}", "INFO")
        success = restore_backup(backups[0], fix_target)

        if success:
            # 重啟服務
            service = error_info.get("service", "bot.service")
            self._restart_service(service)

        return success

    # -----------------------------------------------------------------
    # Helper wrappers that the agent can call directly (whitelisted)
    # -----------------------------------------------------------------
    async def restart_service(self, service: str) -> bool:
        """Thin wrapper around _restart_service for the agent."""
        return self._restart_service(service)

    async def run_command(self, command: str) -> bool:
        """Thin wrapper around _run_command for the agent (whitelisted inside)."""
        return self._run_command(command)


# ─── Git 整合 ────────────────────────────────────────────────


class GitManager:
    """Git 持久化（安全版）。

    嚴守兩條紅線（對應已批准計畫）：
      1. 嚴禁 `git add -A` —— 只 stage 「被修的那一個檔」，否則會把
         data/*.json 等 runtime 狀態一起塞進 AI commit。
      2. 嚴禁 push main —— 部署鏈對任何 main push 做 git reset --hard +
         systemctl restart，AI 改碼會秒上活人；改走 auto-self-heal 分支 +
         開 PR（人 review 才 merge）。

    治癒本身（讓 bot 當下恢復）靠 FixExecutor 就地寫檔 + restart + verify
    完成，與此持久化步驟獨立。此處只決定「修復要不要落進 git 歷史」。
    """

    HEAL_BRANCH = "auto-self-heal"

    def __init__(self):
        self.repo_path = PROJECT_ROOT
        # 獨立 PR worktree（避免在 live main 工作樹上切分支，干擾 bot 運行與 webhook 部署）。
        # 未設定時：保留就地修復（治癒仍有效），略過 PR；不會退而 push main。
        self.pr_worktree = os.getenv("SELF_HEAL_PR_WORKTREE", "").strip() or None

    def commit_and_push(self, message: str, file_path: Optional[str] = None) -> bool:
        """把單一修復檔提交到 auto-self-heal 分支並開 PR。"""
        if not file_path:
            _log("ℹ️ 未提供修復檔路徑，保留就地修復，不提交 git", "INFO")
            return False
        if not self.pr_worktree:
            _log("ℹ️ 未設定 SELF_HEAL_PR_WORKTREE，保留就地修復，略過 PR 建立", "INFO")
            return False

        wt = Path(self.pr_worktree)
        if not wt.is_dir():
            _log(f"⚠️ PR worktree 不存在: {wt}（保留就地修復，略過 PR）", "WARN")
            return False

        # 把修好的檔複製到 PR worktree（live main 工作樹完全不動）
        src = Path(file_path)
        if not src.is_absolute():
            src = PROJECT_ROOT / file_path
        if not src.exists():
            _log(f"❌ 來源檔不存在: {src}", "ERROR")
            return False
        try:
            rel = src.relative_to(PROJECT_ROOT)
        except ValueError:
            _log(f"❌ 修復檔不在專案內: {src}（拒絕提交）", "ERROR")
            return False
        dst = wt / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as e:
            _log(f"❌ 複製修復檔到 worktree 失敗: {e}", "ERROR")
            return False
        rel_posix = rel.as_posix()

        try:

            def _g(*args, timeout=30):
                return subprocess.run(
                    ["git", "-C", str(wt), *args],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

            subprocess.run(
                ["git", "config", "user.name", "KKGroup Self-Heal Bot"],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "config", "user.email", "self-heal@kkgroup.local"],
                capture_timeout=True,
                timeout=10,
            )

            _g("checkout", "-B", self.HEAL_BRANCH, "origin/main")
            _g("add", "--", rel_posix)  # 只 stage 這一個檔

            if _g("diff", "--cached", "--quiet").returncode == 0:
                _log(
                    "ℹ️ worktree 內無實際差異（修復與 origin/main 一致），略過 commit",
                    "INFO",
                )
                return True

            c = _g("commit", "-m", message)
            if c.returncode != 0:
                _log(f"❌ commit 失敗: {c.stderr[:300]}", "ERROR")
                return False

            p = _g("push", "-u", "origin", self.HEAL_BRANCH, "--force-with-lease")
            if p.returncode != 0:
                _log(f"❌ push {self.HEAL_BRANCH} 失敗: {p.stderr[:300]}", "ERROR")
                return False
            _log(f"✅ 已推送到分支 {self.HEAL_BRANCH}", "INFO")

            # 開 PR；gh 不可用時只留分支（人可手動開）
            pr = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    self.HEAL_BRANCH,
                    "--title",
                    message.splitlines()[0][:120],
                    "--body",
                    "🤖 由 auto_self_heal 從報錯自動產生，已於 VM 就地驗證通過。請 review 後再 merge。",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if pr.returncode == 0:
                _log(f"✅ PR 已建立: {pr.stdout.strip()[:200]}", "INFO")
            else:
                _log(
                    f"⚠️ gh pr create 未成功（分支已推，可手動開 PR）: {pr.stderr[:200]}",
                    "WARN",
                )
            return True

        except subprocess.TimeoutExpired:
            _log("❌ Git 操作逾時", "ERROR")
            return False
        except Exception as e:
            _log(f"❌ Git 操作異常: {e}", "ERROR")
            return False


# ─── Discord 通知 ────────────────────────────────────────────


class DiscordNotifier:
    """發送 Discord 通知"""

    def __init__(self):
        self.webhook_url = (
            os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK") or ""
        )

    async def send_notification(
        self, title: str, description: str, color: int = 0x00FF00, fields: list = None
    ) -> bool:
        """發送 Discord Embed 通知"""
        if not self.webhook_url:
            return False

        try:
            import aiohttp

            embed = {
                "title": title,
                "description": description[:2000],
                "color": color,
                "timestamp": datetime.now().isoformat(),
            }

            if fields:
                embed["fields"] = fields

            payload = {
                "content": None,
                "embeds": [embed],
            }

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status in (200, 204):
                        _log("✅ Discord 通知已發送", "INFO")
                        return True
                    else:
                        _log(f"❌ Discord 通知失敗: {resp.status}", "WARN")
                        return False

        except Exception as e:
            _log(f"❌ Discord 通知異常: {e}", "WARN")
            return False

    async def notify_l3_error(self, error_info: dict):
        """通知 L3 錯誤需要人工介入"""
        await self.send_notification(
            title="🚨 L3 錯誤需要人工介入",
            description=f"**服務**: {error_info.get('service', '未知')}\n"
            f"**錯誤**: {error_info.get('message', '')[:500]}",
            color=0xFF0000,
            fields=[
                {
                    "name": "時間",
                    "value": error_info.get("timestamp", ""),
                    "inline": True,
                },
                {
                    "name": "建議操作",
                    "value": "請 SSH 進 VM 檢查並手動修復",
                    "inline": False,
                },
            ],
        )

    async def notify_fix_result(
        self, error_info: dict, success: bool, level: str, details: str = ""
    ):
        """通知修復結果"""
        if success:
            await self.send_notification(
                title=f"✅ {level} 修復成功",
                description=f"**服務**: {error_info.get('service', '未知')}\n"
                f"**錯誤**: {error_info.get('message', '')[:300]}\n"
                f"**處理**: {details[:500]}",
                color=0x00FF00,
            )
        else:
            await self.send_notification(
                title=f"❌ {level} 修復失敗",
                description=f"**服務**: {error_info.get('service', '未知')}\n"
                f"**錯誤**: {error_info.get('message', '')[:300]}\n"
                f"**原因**: {details[:500]}",
                color=0xFFA500,
                fields=[
                    {"name": "建議", "value": "請檢查日誌並手動處理", "inline": False},
                ],
            )


# ─── 主流程 ──────────────────────────────────────────────────


class SelfHealDaemon:
    """VM 自我修復守護程式主類別"""

    def __init__(self):
        _load_env()
        self.services = ["bot.service", "shopbot.service", "uibot.service"]
        self.fix_executor = FixExecutor()
        self.git_manager = GitManager()
        self.notifier = DiscordNotifier()
        self.state = _load_state()
        self.incident_cooldown = {}  # {(service, error_type): last_time}

        # Agent 修復引擎 (取代 L1/L2)
        self.agent_engine = AgentFixEngine(self.fix_executor, self.notifier)

        # 防呆：啟動時檢查服務狀態，若正常則記錄為穩定 commit
        self._check_and_record_stable_commit()

    def _check_and_record_stable_commit(self):
        """啟動時檢查所有服務是否正常，若正常則記錄當前 commit 為穩定點"""
        try:
            all_active = True
            for svc in self.services:
                result = subprocess.run(
                    ["systemctl", "is-active", svc],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.stdout.strip() != "active":
                    all_active = False
                    break

            if all_active:
                # 所有服務正常，記錄穩定 commit
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=PROJECT_ROOT,
                )
                if result.returncode == 0:
                    save_stable_commit(result.stdout.strip())
                    _log("✅ 啟動檢查: 所有服務正常，已記錄穩定 commit", "INFO")
            else:
                _log("⚠️ 啟動檢查: 部分服務異常，不更新穩定 commit", "WARN")

        except Exception as e:
            _log(f"⚠️ 啟動檢查異常: {e}", "WARN")

    def _check_cooldown(self, service: str, error_type: str, minutes: int = 30) -> bool:
        """檢查冷卻時間"""
        key = (service, error_type)
        last_time = self.incident_cooldown.get(key)
        if last_time:
            if (datetime.now() - last_time).total_seconds() < minutes * 60:
                return False
        self.incident_cooldown[key] = datetime.now()
        return True

    async def run_once(self):
        """執行一次自我修復檢查"""
        _log("=" * 50, "INFO")
        _log("🔍 開始自我修復檢查", "INFO")

        # 1. 收集錯誤
        errors = collect_errors(self.services, since_minutes=10)
        if not errors:
            _log("✅ 沒有發現新的錯誤", "INFO")
            return

        _log(f"📊 發現 {len(errors)} 個錯誤", "INFO")

        # 2. 分類並處理每個錯誤
        for error in errors:
            await self._handle_error(error)

    async def _handle_error(self, error: dict):
        """處理單一錯誤 - 統一使用 Agent 修復引擎"""
        error_text = error.get("message", "")
        service = error.get("service", "")

        # 提取檔案路徑
        file_path = _extract_file_path_from_traceback([error_text])
        if not file_path:
            file_path = "unknown"

        _log(f"📋 錯誤處理: {service} -> {file_path}", "INFO")
        _log(f"   訊息: {error_text[:200]}", "INFO")

        # 冷卻檢查
        error_type = "agent_fix"  # 統一錯誤類型用於冷卻
        if not self._check_cooldown(service, error_type):
            _log(f"⏳ 冷卻中，跳過 ({service})", "INFO")
            return

        # 檢查 Agent 是否可用
        if not self.agent_engine.is_available():
            _log("⚠️ Agent 不可用，降級為 L3 人工介入", "WARN")
            await self._handle_l3(error)
            return

        # 執行 Agent 修復
        result = await self.agent_engine.diagnose_and_fix(error, error_text, file_path, service)

        if result.get("success"):
            _log(f"✅ Agent 修復成功: {result.get('root_cause', '未知')}", "INFO")

            # 驗證服務
            verified = self.fix_executor.verify_fix(service)

            if verified:
                _log("✅ 修復驗證通過", "INFO")

                # 重置失敗計數，記錄穩定 commit
                reset_agent_failures()

                # Git commit + push (若有修復檔案)
                for fix_file in result.get("fixes_applied", []):
                    if fix_file and fix_file != "unknown":
                        commit_msg = f"fix: Agent 自動修復 - {result.get('root_cause', '未知')[:80]}"
                        self.git_manager.commit_and_push(commit_msg, file_path=fix_file)

                await self.notifier.notify_fix_result(
                    error,
                    success=True,
                    level="Agent",
                    details=f"根因: {result.get('root_cause', '')}\n修復: {', '.join(result.get('fixes_applied', []))}\n驗證: {result.get('verification', '')}",
                )
            else:
                _log("❌ Agent 修復後驗證失敗，記錄失敗並嘗試回滾", "ERROR")
                failures = record_agent_failure()
                _log(f"📊 連續失敗次數: {failures}/{MAX_AGENT_RETRIES}", "WARN")

                if failures >= MAX_AGENT_RETRIES:
                    await self._trigger_rollback_and_alert(service, error, result)
                else:
                    # 回滾到最近備份
                    self.fix_executor.rollback(error)
                    await self.notifier.notify_fix_result(
                        error,
                        success=False,
                        level="Agent",
                        details=f"修復後服務異常，已回滾備份 (失敗 {failures}/{MAX_AGENT_RETRIES})",
                    )
        else:
            _log(f"❌ Agent 無法完成修復: {result.get('reason', '未知原因')}", "ERROR")
            failures = record_agent_failure()
            _log(f"📊 連續失敗次數: {failures}/{MAX_AGENT_RETRIES}", "WARN")

            if failures >= MAX_AGENT_RETRIES:
                await self._trigger_rollback_and_alert(service, error, result)
            else:
                await self.notifier.send_notification(
                    title="⚠️ Agent 修復失敗",
                    description=f"服務: {service}\n錯誤: {error_text[:300]}\n原因: {result.get('reason', '未知')}\n進度: {result.get('progress_log', [])[-3:] if result.get('progress_log') else '無'}\n失敗計數: {failures}/{MAX_AGENT_RETRIES}",
                    color=0xFFA500,
                )

    async def _trigger_rollback_and_alert(self, service: str, error: dict, result: dict):
        """觸發防呆回滾並通知人工"""
        _log(f"🚨 連續 {MAX_AGENT_RETRIES} 次失敗，觸發防呆回滾到穩定 commit", "ERROR")

        # 執行硬性回滾
        rollback_ok = rollback_to_stable_commit(service)

        # 重置失敗計數（已回滾到穩定點）
        state = _load_state()
        state["agent_failures"] = 0
        _save_state(state)

        if rollback_ok:
            _log("✅ 防呆回滾成功，服務恢復穩定", "INFO")
            alert_msg = f"✅ **自動回滾成功**\n服務已恢復至穩定 commit 運行\n請人工檢查根因並手動修復後再部署"
            color = 0x00FF00
        else:
            _log("❌ 防呆回滾失敗，服務可能仍異常", "ERROR")
            alert_msg = f"❌ **自動回滾失敗**\n服務可能仍處於異常狀態\n**請立即 SSH 進 VM 人工介入**"
            color = 0xFF0000

        # 發送緊急通知
        await self.notifier.send_notification(
            title="🚨 防呆機制觸發：自動回滾",
            description=f"**服務**: {service}\n**原始錯誤**: {error.get('message', '')[:500]}\n**Agent 失敗詳情**: {result.get('reason', '未知')}\n**進度**: {result.get('progress_log', [])[-5:] if result.get('progress_log') else '無'}\n\n{alert_msg}",
            color=color,
            fields=[
                {"name": "建議操作", "value": "SSH 進 VM 檢查日誌，手動修復後 git push 部署", "inline": False},
                {"name": "穩定 Commit", "value": get_stable_commit()[:8] if get_stable_commit() else "未知", "inline": True},
                {"name": "當前 Commit", "value": self._get_current_commit()[:8], "inline": True},
            ],
        )

        # 同時記錄到 L3 事件
        state = _load_state()
        state.setdefault("incidents", []).append({
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "message": error.get("message", ""),
            "level": "L3_ROLLBACK",
            "rollback": rollback_ok,
            "failures": MAX_AGENT_RETRIES,
        })
        _save_state(state)

    def _get_current_commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=PROJECT_ROOT,
            )
            return result.stdout.strip() if result.returncode == 0 else "未知"
        except Exception:
            return "未知"

    async def _handle_l3(self, error: dict):
        """處理 L3 錯誤 - 通知人工"""
        _log("🚨 L3 錯誤，通知人工介入", "WARN")

        # 儲存到狀態
        state = _load_state()
        state.setdefault("incidents", []).append(
            {
                "timestamp": datetime.now().isoformat(),
                "service": error.get("service", ""),
                "message": error.get("message", ""),
                "level": "L3",
            }
        )
        _save_state(state)

        # Discord 通知
        await self.notifier.notify_l3_error(error)

    async def run_watch(self, interval: int = 300):
        """持續監控模式"""
        _log(f"👀 啟動持續監控模式 (間隔: {interval}秒)", "INFO")
        _log(f"   監控服務: {', '.join(self.services)}", "INFO")

        while True:
            try:
                await self.run_once()
            except KeyboardInterrupt:
                _log("👋 收到中斷訊號，結束監控", "INFO")
                break
            except Exception as e:
                _log(f"❌ 監控循環異常: {e}", "ERROR")
                _log(traceback.format_exc(), "DEBUG")

            _log(f"⏳ 等待 {interval} 秒後再次檢查...", "INFO")
            await asyncio.sleep(interval)


# ─── 命令列介面 ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="VM 自我修復守護程式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 scripts/auto_self_heal.py              # 單次執行
  python3 scripts/auto_self_heal.py --watch      # 持續監控
  python3 scripts/auto_self_heal.py --watch --interval 600  # 每10分鐘檢查
  python3 scripts/auto_self_heal.py --test       # 測試模式（不實際修復）
        """,
    )
    parser.add_argument("--watch", action="store_true", help="持續監控模式")
    parser.add_argument(
        "--interval", type=int, default=300, help="監控間隔（秒），預設300"
    )
    parser.add_argument("--test", action="store_true", help="測試模式（不實際修復）")
    parser.add_argument(
        "--services",
        nargs="+",
        default=["bot.service", "shopbot.service", "uibot.service"],
        help="要監控的服務列表",
    )

    args = parser.parse_args()

    if args.test:
        _log("🧪 測試模式", "INFO")
        _log(f"   服務: {', '.join(args.services)}", "INFO")
        _log(f"   間隔: {args.interval}秒", "INFO")
        _log(f"   監控: {'是' if args.watch else '否（單次）'}", "INFO")

        # 測試：收集錯誤
        errors = collect_errors(args.services, since_minutes=60)
        _log(f"   找到 {len(errors)} 個錯誤", "INFO")
        for e in errors[:5]:
            level, etype, desc = classify_error(e["message"])
            _log(f"   [{level}/{etype}] {e['service']}: {e['message'][:100]}", "INFO")

        _log("🧪 測試完成", "INFO")
        return

    daemon = SelfHealDaemon()

    if args.watch:
        asyncio.run(daemon.run_watch(interval=args.interval))
    else:
        asyncio.run(daemon.run_once())


if __name__ == "__main__":
    main()
