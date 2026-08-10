import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import requests

_GITHUB_REPO = os.getenv("GITHUB_REPO", "chenkankan1103/kkgroup")
_SERVICE_BY_BOT_TYPE = {
    "bot": "bot.service",
    "shopbot": "shopbot.service",
    "uibot": "uibot.service",
}
_HEALTHY_STATUSES = {"active", "activating", "reloading"}
_MUTUAL_RESCUE_INTERVAL_SEC = int(os.getenv("MUTUAL_RESCUE_INTERVAL_SEC", "60"))
_MUTUAL_RESCUE_COOLDOWN_SEC = int(os.getenv("MUTUAL_RESCUE_COOLDOWN_SEC", "300"))
_MUTUAL_RESCUE_LOG_LINES = int(os.getenv("MUTUAL_RESCUE_LOG_LINES", "20"))
_MUTUAL_RESCUE_JOURNAL_SINCE = os.getenv(
    "MUTUAL_RESCUE_JOURNAL_SINCE", "10 minutes ago"
)
_SYSTEMCTL_BIN = shutil.which("systemctl") or "/usr/bin/systemctl"
_JOURNALCTL_BIN = shutil.which("journalctl") or "/usr/bin/journalctl"
_SUDO_BIN = shutil.which("sudo") or "/usr/bin/sudo"
_FATAL_LOG_PATTERNS = (
    r"traceback",
    r"syntaxerror",
    r"indentationerror",
    r"importerror",
    r"modulenotfounderror",
    r"nameerror",
    r"attributeerror",
    r"typeerror",
    r"keyerror",
    r"valueerror",
    r"critical",
    r"fatal",
    r"unhandled exception",
    r"main process exited",
    r"failed with result",
    r"result=exit-code",
)
_GENERIC_LOG_PATTERNS = (
    r"\berror\b",
    r"\bexception\b",
    r"connection refused",
    r"connection reset",
    r"timed out",
    r"websocket closed",
    r"shard .* disconnect",
    r"429",
    r"rate limit",
)
_CODE_BUG_PATTERNS = (
    r"syntaxerror",
    r"indentationerror",
    r"importerror",
    r"modulenotfounderror",
    r"nameerror",
    r"attributeerror",
    r"typeerror",
    r"keyerror",
    r"valueerror",
)
_LOCAL_HEAL_PATTERNS = (
    r"main process exited",
    r"failed with result",
    r"result=exit-code",
    r"connection refused",
    r"connection reset",
    r"timed out",
    r"websocket closed",
    r"shard .* disconnect",
    r"429",
    r"rate limit",
)
_SELF_NOISE_PATTERNS = (
    r"\[MutualRescue\]",
    r"watchdog / reporter=",
    r"已派送互救修復請求",
    r"本地重啟 .* 成功",
    r"本地重啟 .* 失敗",
    r"互救修復請求",
    r"正在檢查同伴服務狀態",
    r"auto_error_detector",
    r"auto-debug",
)
_EXTERNAL_BENIGN_PATTERNS = (
    r"google_quota_exhausted",
    r"quota exceeded",
    r"learn more about gemini api quotas",
    r"generatecontentinputtokenspermodelperminute-freetier",
    r"generaterequestsper.*freetier",
    r"nvidia api .*403",
    r"authorization failed",
    r"Unknown interaction",
    r"error code:\s*10062",
    r"429|rate limit",
    r"connection refused",
    r"connection reset",
    r"timed out",
    r"websocket closed",
    r"shard .* disconnect",
    # Gemini quota（中文/英文混雜 log 格式）
    r"google api 錯誤\s*429",
    r"google api error\s*429",
    r"quota exceeded.*gemini",
    r"generativelanguage\.googleapis\.com.*429",
    r"generatecontent.*free.?tier.*limit",
    # Discord gateway（自定義 log 格式）
    r"\[discord\]\s*gateway\s+disconnected",
    r"\[discord\]\s*session\s+resumed",
    r"on_disconnect\s+called",
    r"on_resumed\s+called",
    # Tunnel 相關
    r"無法獲取隧道 url",
    r"tunnel url.*失敗",
)


def _artifact_key_from_signature(signature: str) -> str:
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]


def _normalize_snapshot(text: str) -> str:
    normalized = (text or "").lower()
    normalized = " ".join(normalized.split())
    return normalized[:240]


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _systemctl_restart_command(service: str) -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return [_SYSTEMCTL_BIN, "restart", service]
    if _SUDO_BIN:
        return [_SUDO_BIN, "-n", _SYSTEMCTL_BIN, "restart", service]
    return [_SYSTEMCTL_BIN, "restart", service]


def _read_service_snapshot(service: str) -> dict[str, str]:
    status_proc = _run_command([_SYSTEMCTL_BIN, "is-active", service])
    detail_proc = _run_command(
        [
            _SYSTEMCTL_BIN,
            "show",
            service,
            "--property=ActiveState,SubState,Result,ExecMainCode,ExecMainStatus",
        ]
    )
    log_proc = _run_command(
        [
            _JOURNALCTL_BIN,
            "-u",
            service,
            "--since",
            _MUTUAL_RESCUE_JOURNAL_SINCE,
            "-n",
            str(_MUTUAL_RESCUE_LOG_LINES),
            "--no-pager",
        ]
    )

    status = (
        (status_proc.stdout or status_proc.stderr or "unknown").strip().splitlines()
    )
    status_text = status[-1].strip() if status else "unknown"
    details = (detail_proc.stdout or detail_proc.stderr or "").strip()
    logs = (log_proc.stdout or log_proc.stderr or "").strip()
    summary = f"{service} status={status_text}\n{details}\n{logs[-1500:]}"
    return {
        "service": service,
        "status": status_text,
        "summary": summary[:2000],
        "logs": logs[-1500:],
    }


def _filtered_snapshot_text(snapshot: dict[str, str]) -> str:
    summary = snapshot.get("summary", "")
    logs = snapshot.get("logs", "")
    filtered_lines = []
    for raw_line in f"{summary}\n{logs}".splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(
            re.search(pattern, line, re.IGNORECASE) for pattern in _SELF_NOISE_PATTERNS
        ):
            continue
        if any(
            re.search(pattern, line, re.IGNORECASE)
            for pattern in _EXTERNAL_BENIGN_PATTERNS
        ):
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines).lower()


def _snapshot_requires_repair(snapshot: dict[str, str]) -> tuple[bool, str]:
    status = (snapshot.get("status") or "unknown").strip().lower()
    combined_text = _filtered_snapshot_text(snapshot)

    if status not in _HEALTHY_STATUSES:
        return True, f"狀態異常: {status}"

    if not combined_text.strip():
        return False, "服務狀態正常，且近期只有互救/配額類噪音"

    for pattern in _FATAL_LOG_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return True, f"偵測到高風險錯誤訊號: {pattern}"

    generic_hits = sum(
        1
        for pattern in _GENERIC_LOG_PATTERNS
        if re.search(pattern, combined_text, re.IGNORECASE)
    )
    if generic_hits >= 2:
        return True, f"近期日誌累積 {generic_hits} 個異常訊號"

    return False, "服務狀態與近期日誌皆正常"


def _decide_repair_action(snapshot: dict[str, str]) -> tuple[str, str]:
    should_repair, reason = _snapshot_requires_repair(snapshot)
    if not should_repair:
        return "healthy", reason

    status = (snapshot.get("status") or "unknown").strip().lower()

    if status not in _HEALTHY_STATUSES:
        # 服務真的 inactive/failed（不在 healthy 集合）才重啟。
        # 重啟失敗才 escalate（_check_peers_once 會接著 dispatch GitHub）。
        return "local-heal", f"{reason} / 服務異常({status})，先嘗試本地重啟"

    # 服務 active 但近期日誌有訊號（traceback / 程式碼缺陷 / 營運異常等）：
    # 交由 auto-self-heal daemon（同時 watch bot/shopbot/uibot）做 L1/L2/L3 修復碼，
    # mutual_rescue 不重啟、不 dispatch，避免反覆重啟 active 服務與 self-heal 搶修重疊
    # （即原「active 但有 traceback，直接升級 → 已派送互救修復請求」7/4·7/5·7/6 死循環。
    return (
        "healthy",
        f"{reason} / 服務運行中，交由 self-heal daemon 處理，mutual_rescue 不介入",
    )


def _attempt_local_service_heal(service: str) -> dict[str, str | bool]:
    before_snapshot = _read_service_snapshot(service)
    restart_proc = _run_command(_systemctl_restart_command(service))
    after_snapshot = _read_service_snapshot(service)
    after_action, after_reason = _decide_repair_action(after_snapshot)

    status_before = before_snapshot.get("status", "unknown")
    status_after = after_snapshot.get("status", "unknown")
    restart_error = (restart_proc.stderr or restart_proc.stdout or "").strip()
    success = restart_proc.returncode == 0 and after_action == "healthy"

    summary = (
        f"本地重啟 {service} 成功，狀態 {status_before} -> {status_after}"
        if success
        else f"本地重啟 {service} 失敗，狀態 {status_before} -> {status_after}"
    )
    if restart_error:
        summary += f" / {restart_error[:160]}"
    if not success:
        summary += f" / {after_reason}"

    return {
        "attempted": True,
        "success": success,
        "summary": summary,
        "status_before": status_before,
        "status_after": status_after,
        "snapshot": after_snapshot,
    }


_TARGET_FILE_RE = re.compile(r'File\s+"([^"]+\.py)"')


def _extract_target_file(snapshot: dict[str, str]) -> Optional[str]:
    """從快照日誌的 traceback 抽出出錯的專案檔案路徑（repo-relative）。

    優先取最後一個（最深的 frame）屬於專案 <root>/kkgroup/ 的 .py，
    退化成絕對路徑；供 L3 AI 修復使用「真實檔案路徑」而非讓 AI 猜測。
    """
    text = f"{snapshot.get('summary', '')}\n{snapshot.get('logs', '')}"
    candidate = None
    for match in _TARGET_FILE_RE.finditer(text):
        path = match.group(1).replace("\\", "/")
        idx = path.find("/kkgroup/")
        if idx != -1:
            candidate = path[idx + len("/kkgroup/") :]
        elif candidate is None:
            candidate = path
    return candidate


def _dispatch_repair_request(
    reporter_bot_type: str,
    reporter_service: str,
    target_service: str,
    snapshot: dict[str, str],
) -> tuple[bool, str]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return False, "GITHUB_TOKEN 未設定，無法派送互救修復"

    signature = f"高|mutual-rescue|{target_service}|{_normalize_snapshot(snapshot.get('summary', ''))}"
    payload = {
        "event_type": "error_analysis",
        "client_payload": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "log_text": snapshot.get("summary", ""),
            "severity": "高",
            "source": f"mutual_rescue_watchdog:{reporter_bot_type}",
            "service_hint": target_service,
            "reported_by_bot": reporter_bot_type,
            "reported_by_service": reporter_service,
            "requested_action": "restart_service",
            # traceback 抽出的真實檔案路徑；L3 AI 修復優先拿這個，不再讓 AI 猜 file_path
            "target_file": _extract_target_file(snapshot) or "",
            "incident_signature": signature,
            "incident_key": _artifact_key_from_signature(signature),
        },
    }

    response = requests.post(
        f"https://api.github.com/repos/{_GITHUB_REPO}/dispatches",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    if response.status_code == 204:
        return True, f"已派送互救修復請求 -> {target_service}"
    return False, f"派送失敗 HTTP {response.status_code}: {response.text[:160]}"


class MutualRescueMonitor:
    def __init__(
        self,
        bot_client,
        bot_type: str,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        self.bot = bot_client
        self.bot_type = bot_type
        self.log_func = log_func or print
        self.own_service = _SERVICE_BY_BOT_TYPE.get(bot_type)
        self.peer_services = [
            service
            for service in _SERVICE_BY_BOT_TYPE.values()
            if service != self.own_service
        ]
        self._task = None
        self._last_action_at: dict[str, float] = {}

    def _log(self, message: str):
        try:
            self.log_func(message)
        except Exception:
            print(message)

    def start(self):
        if self._task and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self._run())
        return self._task

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run(self):
        await self.bot.wait_until_ready()
        self._log(
            f"[MutualRescue] 啟動互救 watchdog / reporter={self.bot_type} / peers={self.peer_services}"
        )
        while not self.bot.is_closed():
            try:
                await self._check_peers_once()
            except Exception as exc:
                self._log(f"[MutualRescue] 檢查同伴服務失敗: {exc}")
            await asyncio.sleep(_MUTUAL_RESCUE_INTERVAL_SEC)

    async def _check_peers_once(self):
        now = time.time()
        for service in self.peer_services:
            snapshot = await asyncio.to_thread(_read_service_snapshot, service)
            action, reason = _decide_repair_action(snapshot)
            status = snapshot.get("status", "unknown")
            if action == "healthy":
                continue

            last_action_at = self._last_action_at.get(service, 0.0)
            if now - last_action_at < _MUTUAL_RESCUE_COOLDOWN_SEC:
                continue

            if action == "local-heal":
                heal_result = await asyncio.to_thread(
                    _attempt_local_service_heal, service
                )
                self._last_action_at[service] = now
                self._log(
                    f"[MutualRescue] 偵測到 {service} 狀態={status} / 原因={reason} / {heal_result['summary']}"
                )
                if heal_result["success"]:
                    continue

                snapshot = dict(heal_result["snapshot"])
                snapshot["summary"] = (
                    f"{snapshot.get('summary', '')}\n[local-heal] {heal_result['summary']}"
                )[:2000]
                snapshot["logs"] = (
                    f"{snapshot.get('logs', '')}\n[local-heal] {heal_result['summary']}"
                )[-1500:]
                reason = f"{reason} / 本地重啟失敗，升級 GitHub"

            ok, detail = await asyncio.to_thread(
                _dispatch_repair_request,
                self.bot_type,
                self.own_service or "unknown",
                service,
                snapshot,
            )
            self._last_action_at[service] = now
            self._log(
                f"[MutualRescue] 偵測到 {service} 狀態={status} / 原因={reason} / {detail}"
            )


def ensure_mutual_rescue_monitor(
    bot_client, bot_type: str, log_func: Optional[Callable[[str], None]] = None
):
    monitor = getattr(bot_client, "_mutual_rescue_monitor", None)
    if monitor is None:
        monitor = MutualRescueMonitor(bot_client, bot_type, log_func=log_func)
        setattr(bot_client, "_mutual_rescue_monitor", monitor)
    monitor.start()
    return monitor
