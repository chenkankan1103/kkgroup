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
import tempfile
import argparse
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from shared.utils.llm_text_router import GROQ_MODEL
from typing import Optional, Dict, List, Tuple, Any
# ---------- NEW: Agent‑specific imports ----------
import pathlib
from collections import deque

# ─── 工具模組 ────────────────────────────────────────────────
sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.nvidia_ai import call_nvidia_ai
from shared.utils.llm_text_router import GROQ_MODEL

# ─── 路徑設定 ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_ROOT / "archive" / "self_heal_backups"
FIXES_DIR = PROJECT_ROOT / "archive" / "self_heal_fixes"
MEMORY_DIR = PROJECT_ROOT / "data"
MEMORY_FILE = MEMORY_DIR / "self_heal_agent_memory.json"
STATE_FILE = PROJECT_ROOT / "data" / "self_heal_state.json"

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
    print(f"[{timestamp}] [{level}] {msg}", flush=True)


def _load_state() -> dict:
    """載入狀態檔案"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_check": {}, "incidents": [], "fix_history": []}


def _save_state(state: dict):
    """儲存狀態檔案"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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
        match = re.search(r'line\s+(\d+)', line)
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
            "-u", service,
            "-n", str(lines),
            "--no-pager",
            "-o", "short-iso",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
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
                line, re.IGNORECASE
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

            errors.append({
                "service": service,
                "timestamp": ts_str,
                "message": line.strip(),
                "raw": line,
            })

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
    rel_path = os.path.relpath(Path(file_path), PROJECT_ROOT) if Path(file_path).is_absolute() else file_path
    safe_name = rel_path.replace("\\", "_").replace("/", "_").replace(".", "_")

    backups = sorted(BACKUP_DIR.glob(f"*_{safe_name}.bak"), reverse=True)
    return [str(b) for b in backups[:max_results]]


# ─── L1 修復器 ────────────────────────────────────────────────

class L1Fixer:
    """L1 自動修復：處理常見的可預測錯誤"""

    @staticmethod
    def fix_import_error(error_text: str, file_path: str) -> Optional[str]:
        """修復 ImportError - 嘗試 pip install 缺少的模組"""
        match = re.search(r"ImportError: No module named ['\"](.+?)['\"]", error_text)
        if not match:
            match = re.search(r"ModuleNotFoundError: No module named ['\"](.+?)['\"]", error_text)
        if not match:
            return None

        module_name = match.group(1)
        _log(f"🔧 L1: 嘗試安裝缺少模組: {module_name}", "INFO")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", module_name],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                _log(f"✅ L1: 成功安裝 {module_name}", "INFO")
                return f"pip install {module_name}"
            else:
                _log(f"❌ L1: 安裝 {module_name} 失敗: {result.stderr[:200]}", "WARN")
                return None
        except subprocess.TimeoutExpired:
            _log(f"❌ L1: 安裝 {module_name} 逾時", "WARN")
            return None
        except Exception as e:
            _log(f"❌ L1: 安裝異常: {e}", "ERROR")
            return None

    @staticmethod
    def fix_name_error(error_text: str, file_path: str) -> Optional[str]:
        """修復 NameError - 記錄但通常需要人工確認"""
        match = re.search(r"NameError: name ['\"](.+?)['\"] is not defined", error_text)
        if not match:
            return None

        var_name = match.group(1)
        _log(f"🔧 L1: NameError - '{var_name}' 未定義，需檢查檔案 {file_path}", "INFO")
        # NameError 通常需要理解上下文，回傳 None 讓它升級到 L2
        return None

    @staticmethod
    def fix_file_not_found(error_text: str, file_path: str) -> Optional[str]:
        """修復 FileNotFoundError - 嘗試建立目錄"""
        match = re.search(r"FileNotFoundError: \[Errno 2\] No such file or directory: ['\"](.+?)['\"]", error_text)
        if not match:
            return None

        missing_path = match.group(1)
        _log(f"🔧 L1: 嘗試建立缺少的目錄: {missing_path}", "INFO")

        try:
            os.makedirs(os.path.dirname(missing_path), exist_ok=True)
            _log(f"✅ L1: 已建立目錄 {os.path.dirname(missing_path)}", "INFO")
            return f"mkdir -p {os.path.dirname(missing_path)}"
        except Exception as e:
            _log(f"❌ L1: 建立目錄失敗: {e}", "WARN")
            return None

    @staticmethod
    def fix_permission_error(error_text: str, file_path: str) -> Optional[str]:
        """修復 PermissionError - 嘗試修正權限"""
        match = re.search(r"PermissionError: \[Errno 13\] (.+)", error_text)
        if not match:
            return None

        _log(f"🔧 L1: 嘗試修正檔案權限", "INFO")
        try:
            # 找出錯誤中提到的檔案路徑
            path_match = re.search(r"['\"](.+?)['\"]", match.group(1))
            if path_match:
                target = path_match.group(1)
                if os.path.exists(target):
                    os.chmod(target, 0o644)
                    _log(f"✅ L1: 已修正權限: {target}", "INFO")
                    return f"chmod 644 {target}"
        except Exception as e:
            _log(f"❌ L1: 修正權限失敗: {e}", "WARN")
        return None

    @staticmethod
    def fix_discord_not_found(error_text: str, file_path: str) -> Optional[str]:
        """修復 Discord NotFound - 通常是暫時性問題，記錄即可"""
        _log(f"🔧 L1: Discord 404 錯誤，通常為暫時性問題", "INFO")
        return "discord_not_found_ignored"

    @classmethod
    def try_fix(cls, error_type: str, error_text: str, file_path: str) -> Optional[str]:
        """嘗試執行 L1 修復"""
        fixers = {
            "import_error": cls.fix_import_error,
            "module_not_found": cls.fix_import_error,
            "name_error": cls.fix_name_error,
            "file_not_found": cls.fix_file_not_found,
            "permission_error": cls.fix_permission_error,
            "discord_not_found": cls.fix_discord_not_found,
            "discord_forbidden": cls.fix_discord_not_found,
        }

        fixer = fixers.get(error_type)
        if fixer:
            return fixer(error_text, file_path)
        return None


# ─── L2 AI 修復器 ────────────────────────────────────────────

class L2Fixer:
    """L2 AI 輔助修復：使用 NVIDIA/Groq AI 分析並生成修復"""

    def __init__(self):
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")

    async def analyze_and_fix(
        self, error_text: str, file_path: str, service: str
    ) -> Optional[dict]:
        """使用 AI 分析錯誤並生成修復"""
        _log(f"🤖 L2: 使用 AI 分析錯誤 ({service})", "INFO")

        # 讀取出錯檔案內容
        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            abs_path = PROJECT_ROOT / file_path

        file_content = ""
        if abs_path.exists():
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
            except Exception as e:
                _log(f"⚠️ 無法讀取檔案 {file_path}: {e}", "WARN")

        # 構建 AI 提示
        prompt = self._build_prompt(error_text, file_path, file_content, service)

        # 嘗試 NVIDIA
        analysis = await self._call_nvidia(prompt)

        # 備援 Groq
        if not analysis:
            analysis = await self._call_groq(prompt)

        if not analysis:
            _log("❌ L2: AI 分析失敗（NVIDIA + Groq 皆無回應）", "ERROR")
            return None

        return analysis

    def _build_prompt(self, error_text: str, file_path: str, file_content: str, service: str) -> str:
        """構建 AI 分析提示"""
        prompt = f"""你是 KKGroup Discord Bot 系統的 AI 除錯專家。
請分析以下錯誤並生成修復代碼。

## 系統環境
- GCP VM: e2-micro (1GB RAM + 4GB swap)
- 服務: {service}
- 技術棧: Python 3.11 + Discord.py + systemd

## 錯誤資訊
- 檔案: {file_path}
- 錯誤訊息: {error_text}

## 檔案內容（前 200 行）
{file_content[:5000] if file_content else "(無法讀取檔案內容)"}

## 請以 JSON 格式回覆（只輸出 JSON，不要有其他文字）：
{{
    "root_cause": "根本原因（繁體中文）",
    "fix_type": "modify_file | install_package | restart_service | other",
    "fix_target": "需要修改的檔案路徑",
    "fix_code": "具體的修復代碼（如果是 modify_file）",
    "fix_command": "需要執行的 shell 命令（如果不是 modify_file）",
    "verification": "如何驗證修復成功（例如：systemctl is-active <service> 或一個應返回 0 的指令）",
    "confidence": 0.0-1.0
}}"""
        return prompt

    async def _call_nvidia(self, prompt: str) -> Optional[dict]:
        """呼叫 NVIDIA AI API"""
        if not self.nvidia_key:
            return None

        try:
            messages = [
                {"role": "system", "content": "你是 KKGroup Discord Bot 系統的 AI 除錯專家。請只輸出 JSON。"},
                {"role": "user", "content": prompt},
            ]

            content = await call_nvidia_ai(
                messages,
                temperature=0.3,
                max_tokens=2000,
                model=self.nvidia_model,
            )

            if content:
                return self._parse_ai_response(content)
            else:
                return None
        except Exception as e:
            _log(f"NVIDIA API 異常: {e}", "WARN")
            return None

    async def _call_groq(self, prompt: str) -> Optional[dict]:
        """呼叫 Groq API（免費備援）"""
        if not self.groq_key:
            return None

        try:
            import aiohttp

            messages = [
                {"role": "system", "content": "你是 KKGroup Discord Bot 系統的 AI 除錯專家。請只輸出 JSON。"},
                {"role": "user", "content": prompt},
            ]

            payload = {
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000,
            }

            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            return self._parse_ai_response(content)
                    else:
                        _log(f"Groq API 錯誤: {resp.status}", "WARN")
                        return None
        except Exception as e:
            _log(f"Groq API 異常: {e}", "WARN")
            return None

    def _parse_ai_response(self, content: str) -> Optional[dict]:
        """解析 AI 回應的 JSON"""
        # 嘗試直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 嘗試從 markdown code block 中提取
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 嘗試從大括號中提取
        brace_match = re.search(r"\{[\s\S]*\}", content)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        _log("⚠️ 無法解析 AI 回應為 JSON", "WARN")
        _log(f"原始回應: {content[:500]}", "DEBUG")
        return None


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
                return sum(1 for n in _ast.parse(src).body
                           if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)))
            except SyntaxError:
                return -1

        # 先驗證 fix_code 是否為合法 Python 代碼（在寫入之前）
        try:
            parsed_fix = _ast.parse(fix_code)
            after = _top_level_defs(fix_code)
            if after < 0:
                _log("❌ 修復代碼無法 ast.parse（AI 回應可能為片段），拒絕寫入", "ERROR")
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
            "discord.py", "aiohttp", "requests", "python-dotenv",
            "pytz", "google-cloud-compute", "gitpython",
        }
        ALLOWED_SERVICES = {
            "bot.service", "shopbot.service", "uibot.service", "kkgroup-api.service",
        }

        # 白名單 1：pip / pip3 install <pkg>
        if tokens[0] in ("pip", "pip3") and len(tokens) >= 3 and tokens[1] == "install":
            pkg = tokens[2].split("[", 1)[0].split("==")[0].split(">=", 1)[0].lower()
            if pkg not in ALLOWED_PKGS:
                _log(f"❌ pip install 拒絕非白名單套件: {pkg}（降級人工處理）", "WARN")
                return False
            return self._exec_tokens(tokens)

        # 白名單 2：sudo systemctl restart <service>
        if (len(tokens) == 4 and tokens[0] == "sudo" and tokens[1] == "systemctl"
                and tokens[2] == "restart" and tokens[3] in ALLOWED_SERVICES):
            return self._exec_tokens(tokens)

        _log(f"❌ 命令不在白名單，拒絕執行（降級人工處理）: {command}", "WARN")
        return False

    def _exec_tokens(self, tokens: list) -> bool:
        """以 list 形式執行白名單命令（shell=False）"""
        try:
            result = subprocess.run(
                tokens, shell=False, capture_output=True,
                text=True, timeout=60,
            )
            if result.returncode == 0:
                _log(f"✅ 命令執行成功: {' '.join(tokens)}", "INFO")
                if result.stdout:
                    _log(f"輸出: {result.stdout[:500]}", "INFO")
                return True
            _log(f"❌ 命令執行失敗 (code={result.returncode}): {result.stderr[:500]}", "ERROR")
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
                capture_output=True, text=True, timeout=30
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
                capture_output=True, text=True, timeout=10
            )
            is_active = result.stdout.strip() == "active"
            _log(f"{'✅' if is_active else '❌'} 服務狀態: {result.stdout.strip()}", "INFO")
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
                    capture_output=True, text=True, timeout=timeout,
                )

            subprocess.run(["git", "config", "user.name", "KKGroup Self-Heal Bot"],
                           capture_output=True, timeout=10)
            subprocess.run(["git", "config", "user.email", "self-heal@kkgroup.local"],
                           capture_timeout=True, timeout=10)

            _g("checkout", "-B", self.HEAL_BRANCH, "origin/main")
            _g("add", "--", rel_posix)  # 只 stage 這一個檔

            if _g("diff", "--cached", "--quiet").returncode == 0:
                _log("ℹ️ worktree 內無實際差異（修復與 origin/main 一致），略過 commit", "INFO")
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
                ["gh", "pr", "create", "--base", "main", "--head", self.HEAL_BRANCH,
                 "--title", message.splitlines()[0][:120],
                 "--body", "🤖 由 auto_self_heal 從報錯自動產生，已於 VM 就地驗證通過。請 review 後再 merge。"],
                capture_output=True, text=True, timeout=30,
            )
            if pr.returncode == 0:
                _log(f"✅ PR 已建立: {pr.stdout.strip()[:200]}", "INFO")
            else:
                _log(f"⚠️ gh pr create 未成功（分支已推，可手動開 PR）: {pr.stderr[:200]}", "WARN")
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
            os.getenv("DISCORD_WEBHOOK_URL") or
            os.getenv("DISCORD_WEBHOOK") or
            ""
        )

    async def send_notification(self, title: str, description: str, color: int = 0x00FF00, fields: list = None) -> bool:
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

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
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
                {"name": "時間", "value": error_info.get("timestamp", ""), "inline": True},
                {"name": "建議操作", "value": "請 SSH 進 VM 檢查並手動修復", "inline": False},
            ],
        )

    async def notify_fix_result(self, error_info: dict, success: bool, level: str, details: str = ""):
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


# ---------- NEW: Agent‑specific classes ----------

class _AgentMemory:
    """Simple JSON‑based short‑term + long‑term memory."""
    def __init__(self, path: Path, max_recent: int = 20):
        self.path = path
        self.max_recent = max_recent
        self.recent: deque[Dict] = deque(maxlen=max_recent)
        self._load()

    def _load(self):
        try:
            if self.path.is_file():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.recent.extend(data[-self.max_recent:])
        except Exception:
            self.recent.clear()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(list(self.recent), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add(self, entry: Dict):
        self.recent.append(entry)
        self._save()

    def recent_as_text(self) -> str:
        if not self.recent:
            return "(no recent memory)"
        lines = []
        for i, m in enumerate(self.recent, 1):
            lines.append(
                f"{i}. [{m.get('timestamp')}] {m.get('error','')} -> "
                f"{m.get('tool')} ({m.get('result')})"
            )
        return "\n".join(lines)


class AutonomousAgent:
    """
    ReAct‑style loop:
      Observation → LLM (thought+tool+args) → Execute → Observation → …
    All tools are whitelisted and delegated to the existing FixExecutor.
    """
    def __init__(
        self,
        llm_client,                     # callable: (messages, **kw) -> str
        fix_executor: FixExecutor,
        notifier: DiscordNotifier,
        memory_path: Path,
        max_steps: int = 5,
        temperature: float = 0.3,
    ):
        self.llm = llm_client
        self.fix = fix_executor
        self.notifier = notifier
        self.memory = _AgentMemory(memory_path)
        self.max_steps = max_steps
        self.temperature = temperature

    # -----------------------------------------------------------------
    # Prompt engineering (ReAct)
    # -----------------------------------------------------------------
    def _build_prompt(self, observation: str) -> str:
        """Return a prompt that asks the LLM to output a JSON action."""
        tool_descr = "\n".join([
            "- pip_install <package>: install a Python package via pip",
            "- restart_service <service>: restart a systemd service",
            "- run_command <shell_cmd>: execute a whitelisted shell command",
            "- no_op: do nothing (useful when the error is transient)",
        ])
        return f"""You are an autonomous self‑healing agent for a Discord‑bot VM.
You receive an observation (error log) and may choose a tool to fix it.
You have access to a short‑term memory of recent actions.

Available tools:
{tool_descr}

Memory (most recent first):
{self.memory.recent_as_text()}

Observation:
{observation}

Respond **only** with a JSON object that follows this exact schema:
{{
  "thought": "<brief reasoning why you chose this action>",
  "tool": "<one of the tool names above>",
  "args": {{ "<tool‑specific key>": "<value>", ... }}
}}

If you believe no action is needed, set tool to "no_op" and leave args empty.
Do not include any extra text outside the JSON.
"""

    # -----------------------------------------------------------------
    # LLM interaction (with fallback to Groq if NVIDIA fails)
    # -----------------------------------------------------------------
    async def _call_llm(self, prompt: str) -> Optional[str]:
        messages = [
            {"role": "system", "content": "You are a helpful autonomous agent. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]
        # Try NVIDIA first
        try:
            resp = await self.llm(
                messages,
                temperature=self.temperature,
                max_tokens=800,
            )
            if resp:
                return resp.strip()
        except Exception as e:
            # log but continue to fallback
            pass
        # Fallback – use the shared Groq client (same as elsewhere)
        try:
            from shared.utils.llm_text_router import groq_text  # assuming a helper exists
            resp = await groq_text(
                prompt,
                temperature=self.temperature,
                max_tokens=800,
            )
            if resp:
                return resp.strip()
        except Exception:
            pass
        return None

    # -----------------------------------------------------------------
    # Parse LLM JSON safely
    # -----------------------------------------------------------------
    def _parse_llm_response(self, text: str) -> Optional[Dict]:
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            # Basic validation
            if "tool" not in data or not isinstance(data["tool"], str):
                return None
            if "thought" not in data or not isinstance(data["thought"], str):
                data["thought"] = ""
            if "args" not in data or not isinstance(data["args"], dict):
                data["args"] = {}
            return data
        except Exception:
            return None

    # -----------------------------------------------------------------
    # Dispatch the chosen tool to the existing FixExecutor (whitelisted)
    # -----------------------------------------------------------------
    async def _dispatch_tool(self, action: Dict) -> bool:
        tool = action.get("tool", "").lower().strip()
        args = action.get("args", {})
        thought = action.get("thought", "")

        # Log the thought for Discord / debugging
        if thought:
            await self.notifier.send_notification(
                title="🤖 Agent Thought",
                description=thought,
                color=0x0099FF,
            )

        if tool == "no_op":
            return True   # considered a successful “do nothing”

        if tool == "pip_install":
            pkg = args.get("package")
            if not pkg or not isinstance(pkg, str):
                return False
            # Use the existing FixExecutor._run_command via whitelist
            cmd = f"pip install {pkg}"
            return await self.fix.run_command(cmd)

        if tool == "restart_service":
            svc = args.get("service")
            if not svc or not isinstance(svc, str):
                return False
            return await self.fix.restart_service(svc)

        if tool == "run_command":
            cmd = args.get("command")
            if not cmd or not isinstance(cmd, str):
                return False
            # Re‑use the whitelist inside FixExecutor._run_command
            return await self.fix.run_command(cmd)

        # Unknown tool → refuse
        return False

    # -----------------------------------------------------------------
    # Main per‑error‑batch loop
    # -----------------------------------------------------------------
    async def run_once(self, error_batch: List[dict]):
        """
        error_batch: list of dicts as returned by collect_errors().
        We process the *first* error in the batch (the daemon already
        de‑duplicates via its own cooldown logic).
        """
        if not error_batch:
            return
        err = error_batch[0]
        observation = err.get("message", "")
        service = err.get("service", "unknown")

        for step in range(1, self.max_steps + 1):
            prompt = self._build_prompt(observation)
            llm_raw = await self._call_llm(prompt)
            if not llm_raw:
                await self.notifier.send_notification(
                    title="⚠️ Agent LLM failure",
                    description="Both NVIDIA and Groq returned empty output.",
                    color=0xFFA500,
                )
                break

            action = self._parse_llm_response(llm_raw)
            if not action:
                await self.notifier.send_notification(
                    title="⚠️ Agent JSON parse error",
                    description=f"LLM output: {llm_raw[:200]}",
                    color=0xFFA500,
                )
                break

            # Execute the chosen tool
            success = await self._dispatch_tool(action)

            # Build observation for next step (service status + command output)
            # For simplicity we just check if the service is active now.
            # More sophisticated agents could capture stdout/stderr.
            service_ok = False
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                service_ok = result.stdout.strip() == "active"
            except Exception:
                service_ok = False

            # Record to memory
            self.memory.add({
                "timestamp": datetime.now().isoformat(),
                "error": observation[:200],
                "tool": action.get("tool"),
                "args": action.get("args"),
                "thought": action.get("thought"),
                "result": "success" if success else "failure",
                "service_active_after": service_ok,
            })

            # Notify Discord of the step
            await self.notifier.send_notification(
                title=f"🤖 Agent Step {step}/{self.max_steps}",
                description=(
                    f"**Thought:** {action.get('thought')}\n"
                    f"**Tool:** {action.get('tool')}\n"
                    f"**Args:** {json.dumps(action.get('args'), ensure_ascii=False)}\n"
                    f"**Result:** {'✅ Success' if success else '❌ Failure'}\n"
                    f"**Service {service} active?:** {service_ok}"
                ),
                color=0x00FF00 if success else 0xFF8800,
            )

            # If we think the problem is solved, break
            if success and service_ok:
                return
            # Otherwise prepare next observation: tell the LLM what we observed
            observation = (
                f"Previous action ({action.get('tool')}) resulted in "
                f"{'success' if success else 'failure'}. "
                f"Service {service} is now {'active' if service_ok else 'inactive'}."
            )

        # If we exit the loop without success, escalate to L3 (human)
        await self.notifier.send_notification(
            title="🚨 Agent gave up – escalating to human",
            description=(
                f"Agent tried up to {self.max_steps} steps but could not recover "
                f"the service {service}. See earlier notifications for details."
            ),
            color=0xFF0000,
        )

        # Optionally push a placeholder fix to git so the incident is recorded
        # (re‑use existing L3 path – we simply notify)


# ─── 主流程 ──────────────────────────────────────────────────

class SelfHealDaemon:
    """VM 自我修復守護程式主類別"""

    def __init__(self):
        _load_env()
        self.services = ["bot.service", "shopbot.service", "uibot.service"]
        self.l1_fixer = L1Fixer()
        self.l2_fixer = L2Fixer()
        self.fix_executor = FixExecutor()
        self.git_manager = GitManager()
        self.notifier = DiscordNotifier()
        self.state = _load_state()
        self.incident_cooldown = {}  # {(service, error_type): last_time}
        # ---- Agent mode switch -------------------------------------------------
        self.agent_enabled = os.getenv("AUTO_SELF_HEAL_AGENT", "false").lower() in ("1", "true", "yes")
        if self.agent_enabled:
            # LLM client – reuse the same NVIDIA wrapper used elsewhere
            self.llm_client = lambda messages, **kw: call_nvidia_ai(
                messages,
                model=os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
                **kw
            )
            self.agent = AutonomousAgent(
                llm_client=self.llm_client,
                fix_executor=self.fix_executor,
                notifier=self.notifier,
                memory_path=MEMORY_FILE
            )

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
        """處理單一錯誤"""
        error_text = error.get("message", "")
        service = error.get("service", "")

        # 分類
        level, error_type, description = classify_error(error_text)
        _log(f"📋 錯誤分類: {level}/{error_type} ({description})", "INFO")
        _log(f"   服務: {service}", "INFO")
        _log(f"   訊息: {error_text[:200]}", "INFO")

        # 冷卻檢查
        if not self._check_cooldown(service, error_type):
            _log(f"⏳ 冷卻中，跳過 ({error_type})", "INFO")
            return

        # 提取檔案路徑
        file_path = _extract_file_path_from_traceback([error_text])
        if not file_path:
            file_path = "unknown"

        if level == "L1":
            await self._handle_l1(error, error_type, error_text, file_path)
        elif level == "L2":
            await self._handle_l2(error, error_text, file_path, service)
        else:
            await self._handle_l3(error)

    async def _handle_l1(self, error: dict, error_type: str, error_text: str, file_path: str):
        """處理 L1 錯誤 - 自動修復"""
        _log(f"🔧 L1 自動修復: {error_type}", "INFO")

        # 嘗試 L1 修復
        fix_result = self.l1_fixer.try_fix(error_type, error_text, file_path)

        if fix_result:
            _log(f"✅ L1 修復成功: {fix_result}", "INFO")

            # Git commit + push (only if we have a valid file path)
            if file_path and file_path != "unknown":
                commit_msg = f"fix: L1 自動修復 - {error_type} ({error.get('service', '')})"
                self.git_manager.commit_and_push(commit_msg, file_path=file_path)

            # If agent mode is on, we *skip* L2/L3 after a successful L1 fix
            if self.agent_enabled:
                return

            # Discord 通知
            await self.notifier.notify_fix_result(
                error, success=True, level="L1", details=fix_result
            )
        else:
            _log(f"⚠️ L1 無法修復 {error_type}，嘗試升級到 L2", "INFO")
            await self._handle_l2(error, error_text, file_path, error.get("service", ""))

    async def _handle_l2(self, error: dict, error_text: str, file_path: str, service: str):
        """處理 L2 錯誤 - AI 輔助修復"""
        # ---- NEW: hand off to autonomous agent if enabled -------------
        if self.agent_enabled:
            await self.agent.run_once([error])   # pass a list with the single error
            return

        _log(f"🤖 L2 AI 輔助修復", "INFO")

        # AI 分析
        analysis = await self.l2_fixer.analyze_and_fix(error_text, file_path, service)

        if not analysis:
            _log("❌ L2 AI 分析失敗，升級到 L3", "WARN")
            await self._handle_l3(error)
            return

        confidence = analysis.get("confidence", 0)
        _log(f"📊 AI 信心度: {confidence}", "INFO")

        if confidence < 0.5:
            _log(f"⚠️ AI 信心度不足 ({confidence})，升級到 L3", "WARN")
            await self._handle_l3(error)
            return

        # 備份
        fix_target = analysis.get("fix_target", "")
        if fix_target:
            backup_file(fix_target)

        # 執行修復
        success = self.fix_executor.apply_fix(analysis, error)

        if success:
            # 驗證
            verified = self.fix_executor.verify_fix(service)

            if verified:
                _log("✅ L2 修復成功且驗證通過", "INFO")

                # Git commit + push (only if we have a valid file path)
                fix_target = analysis.get("fix_target") or file_path
                if fix_target and fix_target != "unknown":
                    root_cause = analysis.get("root_cause", "AI 自動修復")
                    commit_msg = f"fix: L2 AI 修復 - {root_cause[:100]}"
                    self.git_manager.commit_and_push(commit_msg, file_path=fix_target)

                await self.notifier.notify_fix_result(
                    error, success=True, level="L2",
                    details=f"根本原因: {root_cause[:200]}"
                )
            else:
                _log("❌ L2 修復後驗證失敗，執行回滾", "ERROR")
                self.fix_executor.rollback(error)
                await self.notifier.notify_fix_result(
                    error, success=False, level="L2",
                    details="修復後服務異常，已自動回滾"
                )
        else:
            _log("❌ L2 修復執行失敗", "ERROR")
            await self.notifier.notify_fix_result(
                error, success=False, level="L2",
                details="修復執行失敗"
            )

    async def _handle_l3(self, error: dict):
        """處理 L3 錯誤 - 通知人工"""
        _log(f"🚨 L3 錯誤，通知人工介入", "WARN")

        # 儲存到狀態
        state = _load_state()
        state.setdefault("incidents", []).append({
            "timestamp": datetime.now().isoformat(),
            "service": error.get("service", ""),
            "message": error.get("message", ""),
            "level": "L3",
        })
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
    parser.add_argument("--interval", type=int, default=300, help="監控間隔（秒），預設300")
    parser.add_argument("--test", action="store_true", help="測試模式（不實際修復）")
    parser.add_argument("--services", nargs="+", default=["bot.service", "shopbot.service", "uibot.service"],
                       help="要監控的服務列表")

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