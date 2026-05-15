#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日更新 knowledge wiki 與 VM 掃描結果到 AI 知識庫。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import hashlib
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = PROJECT_ROOT / ".knowledge_refresh.lock"
STATE_FILE = PROJECT_ROOT / ".knowledge_refresh_state.json"
WEBHOOK_DEDUP_SECONDS = 300
load_dotenv(PROJECT_ROOT / ".env")

WEBHOOK_ENV_KEYS = [
    "KNOWLEDGE_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
    "DISCORD_WEBHOOK",
    "STARTUP_WEBHOOK_URL",
]


def run_step(command: list[str]) -> str:
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "unknown error")
    if result.stdout.strip():
        print(result.stdout.strip())
    return result.stdout.strip()


def get_webhook_url() -> str:
    for key in WEBHOOK_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def get_taipei_timestamp() -> str:
    if ZoneInfo is None:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S %Z")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def should_skip_webhook(status: str, details: str) -> bool:
    state = load_state()
    signature = hashlib.sha256(f"{status}\n{details}".encode("utf-8")).hexdigest()
    previous_signature = state.get("last_signature", "")
    previous_status = state.get("last_status", "")
    previous_ts = state.get("last_ts", 0)
    now_ts = int(datetime.utcnow().timestamp())

    if signature == previous_signature and status == previous_status and now_ts - int(previous_ts) < WEBHOOK_DEDUP_SECONDS:
        print("SKIP_DUPLICATE_WEBHOOK")
        return True

    save_state({
        "last_signature": signature,
        "last_status": status,
        "last_ts": now_ts,
    })
    return False


def acquire_lock() -> bool:
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return True
    except FileExistsError:
        print("SKIP_ALREADY_RUNNING")
        return False


def release_lock() -> None:
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def send_webhook(status: str, outputs: list[str], error_message: str = "") -> None:
    webhook_url = get_webhook_url()
    if not webhook_url:
        return

    color = 0x57F287 if status == "success" else 0xED4245
    title = "AI 知識庫每日更新完成" if status == "success" else "AI 知識庫每日更新失敗"
    description = "每日 VM 掃描與知識匯入已完成。" if status == "success" else error_message[:1500]
    details = "\n".join(chunk for chunk in outputs if chunk).strip() or "(無額外輸出)"

    payload = {
        "content": "🤖 KK 中控室知識庫排程回報",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "fields": [
                    {
                        "name": "執行時間",
                        "value": get_taipei_timestamp(),
                        "inline": True,
                    },
                    {
                        "name": "主機",
                        "value": os.getenv("HOSTNAME", "vm"),
                        "inline": True,
                    },
                    {
                        "name": "輸出摘要",
                        "value": f"```json\n{details[:1000]}\n```",
                    },
                ],
            }
        ],
    }

    if should_skip_webhook(status, details):
        return

    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        print(f"WEBHOOK_STATUS:{response.status_code}")
    except Exception as exc:
        print(f"WEBHOOK_ERROR:{type(exc).__name__}:{exc}")


def main() -> int:
    if not acquire_lock():
        return 0

    steps = [
        [sys.executable, "scripts/scan_vm_state.py"],
        [sys.executable, "scripts/ingest_knowledge.py"],
    ]

    outputs: list[str] = []

    try:
        for command in steps:
            outputs.append(run_step(command))
    except Exception as exc:
        send_webhook("failure", outputs, str(exc))
        raise
    finally:
        release_lock()

    summary = json.dumps({"status": "ok", "steps": len(steps)}, ensure_ascii=False)
    print(summary)
    outputs.append(summary)
    send_webhook("success", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())