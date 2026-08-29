#!/usr/bin/env python3
"""
KK群組 - Agent 定時日誌掃描監控
==================================
定期掃描 systemd journal，發現異常模式時：
1. 記錄到資料庫
2. 發送 Discord 通知給管理員
3. （可選）自動提交修復任務到 Agent Server

排程：每 5 分鐘執行一次 (systemd timer / cron)
"""

import asyncio
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# ─── 環境設定 ─────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")
os.environ.setdefault("AGENT_TASK_DB", "/home/e193752468/kkgroup/shared/db/data/agent_tasks.db")

# ─── 導入 ─────────────────────────────────────────────────────────
from shared.agent.tools import create_tool_impl
from shared.agent.memory import get_task_store
from shared.utils.structured_log import get_structured_logger

# ─── 設定 ─────────────────────────────────────────────────────────
SCAN_INTERVAL_MINUTES = 5
ERROR_THRESHOLD = 3  # 同一錯誤指紋 5 分鐘內出現次數
SERVICES = ["bot", "shopbot", "uibot", "kkgroup-api", "cloudflared"]
KNOWN_HARMLESS_PATTERNS = [
    "rate limit",
    "429",
    "websocket closed",
    "heartbeat",
    "shard",
    "gateway",
    "reconnect",
    "resumed session",
]

log = get_structured_logger("agent_log_monitor")


# ─── 核心邏輯 ─────────────────────────────────────────────────────
async def scan_journalctl(
    service: str = "all",
    since_minutes: int = SCAN_INTERVAL_MINUTES,
    level: str = "error",
) -> list[dict]:
    """掃描 journalctl，回傳結構化錯誤列表"""
    tool_impl = create_tool_impl(Path(os.getenv("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")))
    result = await tool_impl.scan_journalctl(
        service=service,
        since_minutes=since_minutes,
        level=level,
        limit=200,
    )
    # 解析輸出文字（簡化：實際應直接回傳結構化資料）
    # 這裡簡單處理，完整版應修改 tools.py 回傳 list[dict]
    return []


async def scan_raw_journalctl(
    service: str,
    since_minutes: int,
    level: str,
) -> list[dict]:
    """直接查詢 journalctl 回傳結構化資料"""
    import json

    services_map = {
        "bot": "bot.service",
        "shopbot": "shopbot.service",
        "uibot": "uibot.service",
        "kkgroup-api": "kkgroup-api.service",
        "cloudflared": "cloudflared.service",
    }

    target_services = [services_map[service]] if service != "all" else list(services_map.values())
    since = f"-{since_minutes}min"
    all_entries = []

    for svc in target_services:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", svc, "--since", since, "--no-pager", "-o", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode("utf-8", errors="replace").strip().split("\n")

        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                msg = entry.get("MESSAGE", "")
                pri = entry.get("PRIORITY", "6")

                if level == "error" and pri not in ("0", "1", "2", "3"):
                    continue
                if level == "warning" and pri not in ("0", "1", "2", "3", "4"):
                    continue

                # 過濾已知無害模式
                if any(p in msg.lower() for p in KNOWN_HARMLESS_PATTERNS):
                    continue

                all_entries.append({
                    "service": svc.replace(".service", ""),
                    "priority": pri,
                    "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                    "message": msg,
                    "_raw": entry,
                })
            except json.JSONDecodeError:
                continue

    return all_entries


def extract_fingerprint(message: str) -> str:
    """提取錯誤指紋（用於去重聚類）"""
    import re
    fp = message
    fp = re.sub(r'\b\d+\b', '<NUM>', fp)
    fp = re.sub(r'/[^/\s]+(/\w+)*', '<PATH>', fp)
    fp = re.sub(r'[0-9a-f]{8,}', '<HASH>', fp)
    fp = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<TIME>', fp)
    return fp[:100]


async def analyze_and_alert(entries: list[dict]) -> list[dict]:
    """分析錯誤模式，產生告警"""
    if not entries:
        return []

    # 指紋聚類
    fingerprints = Counter(extract_fingerprint(e["message"]) for e in entries)
    alerts = []

    for fp, count in fingerprints.most_common(10):
        if count >= ERROR_THRESHOLD:
            # 找代表性錯誤
            sample = next(e for e in entries if extract_fingerprint(e["message"]) == fp)
            alerts.append({
                "fingerprint": fp,
                "count": count,
                "sample_message": sample["message"][:500],
                "service": sample["service"],
                "first_seen": sample["timestamp"],
                "severity": "high" if count >= 10 else "medium",
            })

    return alerts


async def send_discord_alert(alerts: list[dict]):
    """發送 Discord Webhook 告警"""
    webhook_url = os.getenv("DISCORD_ALERT_WEBHOOK")
    if not webhook_url:
        log.warning("alert_webhook_missing", message="DISCORD_ALERT_WEBHOOK 未設定")
        return

    import aiohttp

    for alert in alerts:
        embed = {
            "title": f"🚨 Agent Log Monitor: {alert['severity'].upper()} 頻率告警",
            "color": 0xff0000 if alert["severity"] == "high" else 0xffaa00,
            "fields": [
                {"name": "服務", "value": alert["service"], "inline": True},
                {"name": "出現次數", "value": str(alert["count"]), "inline": True},
                {"name": "嚴重度", "value": alert["severity"], "inline": True},
                {"name": "錯誤指紋", "value": f"`{alert['fingerprint']}`", "inline": False},
                {"name": "範例訊息", "value": f"```\n{alert['sample_message']}\n```", "inline": False},
            ],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(webhook_url, json={"embeds": [embed]}, timeout=aiohttp.ClientTimeout(total=10))
            log.info("alert_sent", fingerprint=alert["fingerprint"], count=alert["count"])
        except Exception as e:
            log.error("alert_send_failed", error=str(e))


async def store_alert(alerts: list[dict]):
    """將告警存入資料庫（擴充 agent_tasks 表或新表）"""
    # 簡化：記錄到結構化日誌
    for alert in alerts:
        log.warning("error_pattern_detected",
                    fingerprint=alert["fingerprint"],
                    count=alert["count"],
                    service=alert["service"],
                    severity=alert["severity"])


async def main():
    """主掃描流程"""
    log.info("log_scan_started", interval_minutes=SCAN_INTERVAL_MINUTES)

    all_entries = []
    for svc in SERVICES:
        entries = await scan_raw_journalctl(svc, SCAN_INTERVAL_MINUTES, "error")
        all_entries.extend(entries)

    if not all_entries:
        log.info("log_scan_complete", message="無錯誤日誌")
        return

    # 分析
    alerts = await analyze_and_alert(all_entries)

    if alerts:
        log.warning("alerts_generated", count=len(alerts))
        await send_discord_alert(alerts)
        await store_alert(alerts)
    else:
        log.info("log_scan_complete", total_entries=len(all_entries), message="無達閾值異常模式")


if __name__ == "__main__":
    # 設定日誌格式
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    asyncio.run(main())