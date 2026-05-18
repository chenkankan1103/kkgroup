import asyncio
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import requests

_GITHUB_REPO = os.getenv('GITHUB_REPO', 'chenkankan1103/kkgroup')
_SERVICE_BY_BOT_TYPE = {
    'bot': 'bot.service',
    'shopbot': 'shopbot.service',
    'uibot': 'uibot.service',
}
_HEALTHY_STATUSES = {'active', 'activating', 'reloading'}
_MUTUAL_RESCUE_INTERVAL_SEC = int(os.getenv('MUTUAL_RESCUE_INTERVAL_SEC', '60'))
_MUTUAL_RESCUE_COOLDOWN_SEC = int(os.getenv('MUTUAL_RESCUE_COOLDOWN_SEC', '300'))
_MUTUAL_RESCUE_LOG_LINES = int(os.getenv('MUTUAL_RESCUE_LOG_LINES', '20'))


def _artifact_key_from_signature(signature: str) -> str:
    return hashlib.sha256(signature.encode('utf-8')).hexdigest()[:16]


def _normalize_snapshot(text: str) -> str:
    normalized = (text or '').lower()
    normalized = ' '.join(normalized.split())
    return normalized[:240]


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _read_service_snapshot(service: str) -> dict[str, str]:
    status_proc = _run_command(['systemctl', 'is-active', service])
    detail_proc = _run_command([
        'systemctl', 'show', service,
        '--property=ActiveState,SubState,Result,ExecMainCode,ExecMainStatus',
    ])
    log_proc = _run_command([
        'journalctl', '-u', service, '-n', str(_MUTUAL_RESCUE_LOG_LINES), '--no-pager'
    ])

    status = (status_proc.stdout or status_proc.stderr or 'unknown').strip().splitlines()
    status_text = status[-1].strip() if status else 'unknown'
    details = (detail_proc.stdout or detail_proc.stderr or '').strip()
    logs = (log_proc.stdout or log_proc.stderr or '').strip()
    summary = f'{service} status={status_text}\n{details}\n{logs[-1500:]}'
    return {
        'service': service,
        'status': status_text,
        'summary': summary[:2000],
        'logs': logs[-1500:],
    }


def _dispatch_repair_request(
    reporter_bot_type: str,
    reporter_service: str,
    target_service: str,
    snapshot: dict[str, str],
) -> tuple[bool, str]:
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        return False, 'GITHUB_TOKEN 未設定，無法派送互救修復'

    signature = f"高|mutual-rescue|{target_service}|{_normalize_snapshot(snapshot.get('summary', ''))}"
    payload = {
        'event_type': 'error_analysis',
        'client_payload': {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'log_text': snapshot.get('summary', ''),
            'severity': '高',
            'source': f'mutual_rescue_watchdog:{reporter_bot_type}',
            'service_hint': target_service,
            'reported_by_bot': reporter_bot_type,
            'reported_by_service': reporter_service,
            'requested_action': 'restart_service',
            'incident_signature': signature,
            'incident_key': _artifact_key_from_signature(signature),
        },
    }

    response = requests.post(
        f'https://api.github.com/repos/{_GITHUB_REPO}/dispatches',
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=15,
    )
    if response.status_code == 204:
        return True, f'已派送互救修復請求 -> {target_service}'
    return False, f'派送失敗 HTTP {response.status_code}: {response.text[:160]}'


class MutualRescueMonitor:
    def __init__(self, bot_client, bot_type: str, log_func: Optional[Callable[[str], None]] = None):
        self.bot = bot_client
        self.bot_type = bot_type
        self.log_func = log_func or print
        self.own_service = _SERVICE_BY_BOT_TYPE.get(bot_type)
        self.peer_services = [
            service for service in _SERVICE_BY_BOT_TYPE.values()
            if service != self.own_service
        ]
        self._task = None
        self._last_dispatch_at: dict[str, float] = {}

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
        self._log(f'[MutualRescue] 啟動互救 watchdog / reporter={self.bot_type} / peers={self.peer_services}')
        while not self.bot.is_closed():
            try:
                await self._check_peers_once()
            except Exception as exc:
                self._log(f'[MutualRescue] 檢查同伴服務失敗: {exc}')
            await asyncio.sleep(_MUTUAL_RESCUE_INTERVAL_SEC)

    async def _check_peers_once(self):
        now = time.time()
        for service in self.peer_services:
            snapshot = await asyncio.to_thread(_read_service_snapshot, service)
            status = snapshot.get('status', 'unknown')
            if status in _HEALTHY_STATUSES:
                continue

            last_dispatch_at = self._last_dispatch_at.get(service, 0.0)
            if now - last_dispatch_at < _MUTUAL_RESCUE_COOLDOWN_SEC:
                continue

            ok, detail = await asyncio.to_thread(
                _dispatch_repair_request,
                self.bot_type,
                self.own_service or 'unknown',
                service,
                snapshot,
            )
            self._last_dispatch_at[service] = now
            self._log(
                f'[MutualRescue] 偵測到 {service} 狀態={status} / {detail}'
            )


def ensure_mutual_rescue_monitor(bot_client, bot_type: str, log_func: Optional[Callable[[str], None]] = None):
    monitor = getattr(bot_client, '_mutual_rescue_monitor', None)
    if monitor is None:
        monitor = MutualRescueMonitor(bot_client, bot_type, log_func=log_func)
        setattr(bot_client, '_mutual_rescue_monitor', monitor)
    monitor.start()
    return monitor
