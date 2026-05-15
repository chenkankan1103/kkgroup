#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日更新 knowledge wiki 與 VM 掃描結果到 AI 知識庫。"""

from __future__ import annotations

import asyncio
import json
import os
import re
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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.llm_text_router import complete_text_with_fallback
from shared.db.knowledge_vector_index import KnowledgeVectorIndex

LOCK_FILE = PROJECT_ROOT / ".knowledge_refresh.lock"
STATE_FILE = PROJECT_ROOT / ".knowledge_refresh_state.json"
STATUS_FILE = PROJECT_ROOT / "status" / "knowledge_refresh_status.json"
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


def truncate_field(value: str, limit: int = 1000) -> str:
    value = (value or "").strip()
    if not value:
        return "未提供"
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def parse_analysis_sections(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"\[SUMMARY\](.*?)\[RISKS\](.*?)\[ACTIONS\](.*?)\[PRIORITY\](.*)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return {
            "summary": text.strip(),
            "risks": "模型未按區塊格式輸出。",
            "actions": "請檢查 AI prompt 或 fallback 模型輸出格式。",
            "priority": "1. 修正輸出格式",
        }
    return {
        "summary": match.group(1).strip(),
        "risks": match.group(2).strip(),
        "actions": match.group(3).strip(),
        "priority": match.group(4).strip(),
    }


def write_status(status: str, outputs: list[str], steps: int, error_message: str = "") -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    analysis_text = next((chunk[len("AI_ANALYSIS:\n"):] for chunk in outputs if chunk.startswith("AI_ANALYSIS:\n")), "")
    analysis_provider = next((chunk.split(":", 1)[1] for chunk in outputs if chunk.startswith("AI_PROVIDER:")), "")
    payload = {
        "status": status,
        "updated_at": get_taipei_timestamp(),
        "hostname": os.getenv("HOSTNAME", "vm"),
        "steps": steps,
        "provider": analysis_provider,
        "error": error_message,
        "outputs": [chunk[:2000] for chunk in outputs if chunk],
        "analysis": parse_analysis_sections(analysis_text) if analysis_text else {},
    }
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def send_webhook(status: str, outputs: list[str], error_message: str = "") -> None:
    webhook_url = get_webhook_url()
    if not webhook_url:
        return

    color = 0x57F287 if status == "success" else 0xED4245
    title = "AI 知識庫每日更新完成" if status == "success" else "AI 知識庫每日更新失敗"
    description = "每日 VM 掃描與知識匯入已完成。" if status == "success" else error_message[:1500]
    details = "\n".join(chunk for chunk in outputs if chunk).strip() or "(無額外輸出)"

    payload = {
        "content": "🤖 KK 中控室日報",
        "embeds": [
            {
                "title": "KK 中控室日報" if status == "success" else title,
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
                        "name": "刷新結果",
                        "value": f"```json\n{details[:1000]}\n```",
                    },
                ],
            }
        ],
    }

    if status == "success":
        analysis_text = next((chunk[len("AI_ANALYSIS:\n"):] for chunk in outputs if chunk.startswith("AI_ANALYSIS:\n")), "")
        analysis_provider = next((chunk.split(":", 1)[1] for chunk in outputs if chunk.startswith("AI_PROVIDER:")), "")
        if analysis_text:
            sections = parse_analysis_sections(analysis_text)
            payload["embeds"][0]["fields"].append(
                {
                    "name": "分析模型",
                    "value": analysis_provider or "unknown",
                    "inline": True,
                }
            )
            payload["embeds"][0]["fields"].append(
                {
                    "name": "系統摘要",
                    "value": truncate_field(sections.get("summary", analysis_text)),
                }
            )
            payload["embeds"][0]["fields"].append(
                {
                    "name": "風險與異常",
                    "value": truncate_field(sections.get("risks", "未提供")),
                }
            )
            payload["embeds"][0]["fields"].append(
                {
                    "name": "可執行建議",
                    "value": truncate_field(sections.get("actions", "未提供")),
                }
            )
            payload["embeds"][0]["fields"].append(
                {
                    "name": "優先順序",
                    "value": truncate_field(sections.get("priority", "未提供")),
                }
            )

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
        indexed = KnowledgeVectorIndex().rebuild_from_database()
        outputs.append(json.dumps({"semantic_indexed": indexed}, ensure_ascii=False))
    except Exception as exc:
        write_status("failure", outputs, len(steps), str(exc))
        send_webhook("failure", outputs, str(exc))
        raise
    finally:
        release_lock()

    summary = json.dumps({"status": "ok", "steps": len(steps)}, ensure_ascii=False)
    print(summary)
    outputs.append(summary)

    scan_report_path = PROJECT_ROOT / "knowledge" / "_wiki" / "Inbox" / "vm-scan-latest.md"
    if scan_report_path.exists():
        scan_report = scan_report_path.read_text(encoding="utf-8")
        analysis_messages = [
            {
                "role": "system",
                "content": (
                    "你是 KK 園區中控 AI 分析官。請根據 VM 掃描報告與刷新結果，"
                    "輸出繁體中文建議，內容務必基於輸入，不要虛構不存在的異常。"
                    "輸出必須嚴格遵守以下區塊格式："
                    "[SUMMARY]、[RISKS]、[ACTIONS]、[PRIORITY]。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "請整理以下資訊。\n"
                    "輸出必須完全符合這個格式，不要加入其他標題或前言：\n"
                    "[SUMMARY]\n- 今日系統狀態摘要\n"
                    "[RISKS]\n- 需要關注的風險或異常（若無則明說）\n"
                    "[ACTIONS]\n- 2 到 3 個可執行的功能或維運建議\n"
                    "[PRIORITY]\n1. 建議優先順序\n\n"
                    "[VM 掃描報告]\n"
                    f"{scan_report[:5000]}\n\n"
                    "[本次刷新輸出]\n"
                    f"{' '.join(outputs)[:1200]}"
                ),
            },
        ]
        analysis_text, provider = asyncio.run(complete_text_with_fallback(analysis_messages, max_tokens=700))
        if analysis_text:
            print(f"AI_PROVIDER:{provider}")
            print("AI_ANALYSIS:\n" + analysis_text)
            outputs.append(f"AI_PROVIDER:{provider}")
            outputs.append("AI_ANALYSIS:\n" + analysis_text)

    write_status("success", outputs, len(steps))
    send_webhook("success", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())