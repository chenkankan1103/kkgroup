"""Discord 功能使用量追蹤。"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FEATURE_USAGE_DB_PATH = DATA_DIR / "feature_usage.db"

_HEXISH_RE = re.compile(r"^[0-9a-f]{8,}$", re.IGNORECASE)
_UUIDISH_RE = re.compile(r"^[0-9a-f]{6,}-[0-9a-f-]{6,}$", re.IGNORECASE)


def ensure_feature_usage_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(FEATURE_USAGE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feature_usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            feature_key TEXT NOT NULL,
            raw_name TEXT NOT NULL,
            source_name TEXT,
            bot_name TEXT,
            component_type TEXT,
            user_id TEXT,
            guild_id TEXT,
            channel_id TEXT,
            metadata_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_feature_usage_feature_time ON feature_usage_events(feature_key, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_feature_usage_event_time ON feature_usage_events(event_type, created_at)"
    )
    conn.commit()
    conn.close()


@dataclass
class InteractionEvent:
    event_type: str
    feature_key: str
    raw_name: str
    source_name: str
    bot_name: str
    component_type: str
    user_id: str
    guild_id: str
    channel_id: str
    metadata: Dict[str, Any]


def _normalize_token(token: str) -> str:
    if not token:
        return token
    if token.isdigit() and len(token) >= 2:
        return "{id}"
    if _HEXISH_RE.match(token) or _UUIDISH_RE.match(token):
        return "{id}"
    return token


def normalize_feature_name(raw_name: str, event_type: str) -> str:
    name = (raw_name or "").strip()
    if not name:
        return f"{event_type}:unknown"

    if event_type == "slash_command":
        return f"slash:{name}"

    if ":" in name:
        parts = [_normalize_token(part) for part in name.split(":")]
        return f"component:{':'.join(parts[:4])}"

    normalized = re.sub(r"\d{2,}", "{id}", name)
    tokens = normalized.split("_")
    if len(tokens) > 4:
        tokens = tokens[:4]
    return f"component:{'_'.join(_normalize_token(token) for token in tokens)}"


def _component_type_name(component_type: Any) -> str:
    if component_type is None:
        return "unknown"
    try:
        return component_type.name.lower()
    except AttributeError:
        return str(component_type).lower()


def extract_interaction_event(
    interaction: discord.Interaction, bot_name: str
) -> Optional[InteractionEvent]:
    data = interaction.data or {}

    if interaction.type == discord.InteractionType.application_command:
        raw_name = (
            getattr(interaction.command, "qualified_name", None)
            or data.get("name")
            or "unknown"
        )
        event_type = "slash_command"
        feature_key = normalize_feature_name(raw_name, event_type)
        source_name = getattr(interaction.command, "cog_name", None) or "unknown"
        component_type = "application_command"
    elif interaction.type == discord.InteractionType.component:
        raw_name = data.get("custom_id") or "unknown"
        event_type = "component"
        feature_key = normalize_feature_name(raw_name, event_type)
        source_name = (
            interaction.message.author.name
            if interaction.message and interaction.message.author
            else "unknown"
        )
        component_type = _component_type_name(data.get("component_type"))
    else:
        return None

    metadata = {
        "message_id": str(interaction.message.id) if interaction.message else "",
        "command_name": (
            getattr(interaction.command, "qualified_name", "")
            if getattr(interaction, "command", None)
            else ""
        ),
    }

    return InteractionEvent(
        event_type=event_type,
        feature_key=feature_key,
        raw_name=raw_name,
        source_name=source_name,
        bot_name=bot_name,
        component_type=component_type,
        user_id=str(interaction.user.id) if interaction.user else "",
        guild_id=str(interaction.guild_id or ""),
        channel_id=str(interaction.channel_id or ""),
        metadata=metadata,
    )


def record_feature_usage(event: InteractionEvent) -> None:
    try:
        ensure_feature_usage_db()
        conn = sqlite3.connect(FEATURE_USAGE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO feature_usage_events (
                event_type, feature_key, raw_name, source_name, bot_name, component_type,
                user_id, guild_id, channel_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_type,
                event.feature_key,
                event.raw_name,
                event.source_name,
                event.bot_name,
                event.component_type,
                event.user_id,
                event.guild_id,
                event.channel_id,
                json.dumps(event.metadata, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("⚠️ 記錄功能使用量失敗: %s", exc)


async def track_discord_interaction(
    interaction: discord.Interaction, bot_name: str
) -> None:
    event = extract_interaction_event(interaction, bot_name)
    if not event:
        return
    record_feature_usage(event)


def summarize_feature_usage(
    days: int = 30, cold_threshold: int = 2, recent_days: int = 7
) -> Dict[str, Any]:
    ensure_feature_usage_db()
    conn = sqlite3.connect(FEATURE_USAGE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_at = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    recent_start = (datetime.utcnow() - timedelta(days=recent_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute(
        """
        SELECT
            feature_key,
            event_type,
            raw_name,
            bot_name,
            component_type,
            COUNT(*) AS total_uses,
            COUNT(DISTINCT user_id) AS unique_users,
            MAX(created_at) AS last_used_at,
            SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS recent_uses
        FROM feature_usage_events
        WHERE created_at >= ?
        GROUP BY feature_key, event_type, raw_name, bot_name, component_type
        ORDER BY total_uses DESC, last_used_at DESC
        """,
        (recent_start, start_at),
    )
    rows = cursor.fetchall()
    conn.close()

    features: List[Dict[str, Any]] = []
    per_bot: Dict[str, int] = defaultdict(int)
    by_type: Dict[str, int] = defaultdict(int)

    for row in rows:
        feature = {
            "feature_key": row["feature_key"],
            "event_type": row["event_type"],
            "raw_name": row["raw_name"],
            "bot_name": row["bot_name"] or "unknown",
            "component_type": row["component_type"] or "unknown",
            "total_uses": int(row["total_uses"] or 0),
            "unique_users": int(row["unique_users"] or 0),
            "recent_uses": int(row["recent_uses"] or 0),
            "last_used_at": row["last_used_at"] or "",
            "is_cold": int(row["recent_uses"] or 0) <= cold_threshold,
        }
        features.append(feature)
        per_bot[feature["bot_name"]] += feature["total_uses"]
        by_type[feature["event_type"]] += feature["total_uses"]

    cold_features = [feature for feature in features if feature["is_cold"]]

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "window_days": days,
        "recent_days": recent_days,
        "cold_threshold": cold_threshold,
        "total_features": len(features),
        "total_interactions": sum(feature["total_uses"] for feature in features),
        "per_bot": dict(sorted(per_bot.items())),
        "by_type": dict(sorted(by_type.items())),
        "top_features": features[:10],
        "cold_features": cold_features[:15],
        "all_features": features,
    }


def build_usage_markdown(
    days: int = 30, cold_threshold: int = 2, recent_days: int = 7
) -> str:
    summary = summarize_feature_usage(
        days=days, cold_threshold=cold_threshold, recent_days=recent_days
    )

    lines = [
        "# Feature Usage Report",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Window: last {summary['window_days']} days",
        f"- Recent cold check: last {summary['recent_days']} days <= {summary['cold_threshold']} uses",
        f"- Total tracked features: {summary['total_features']}",
        f"- Total interactions: {summary['total_interactions']}",
        "",
        "## Bot Usage Totals",
    ]

    if summary["per_bot"]:
        for bot_name, count in summary["per_bot"].items():
            lines.append(f"- {bot_name}: {count}")
    else:
        lines.append("- No usage data yet")

    lines.extend(["", "## Top Features"])
    if summary["top_features"]:
        for item in summary["top_features"]:
            lines.append(
                f"- {item['feature_key']} | uses={item['total_uses']} | recent={item['recent_uses']} | users={item['unique_users']} | last={item['last_used_at']}"
            )
    else:
        lines.append("- No usage data yet")

    lines.extend(["", "## Cold Features"])
    if summary["cold_features"]:
        for item in summary["cold_features"]:
            lines.append(
                f"- {item['feature_key']} | uses={item['total_uses']} | recent={item['recent_uses']} | users={item['unique_users']} | last={item['last_used_at']}"
            )
    else:
        lines.append("- No cold features in current window")

    lines.extend(
        [
            "",
            "## Notes",
            "- Buttons and selects are tracked through global Discord interactions.",
            "- Dynamic custom_id values are normalized to reduce fragmentation.",
        ]
    )
    return "\n".join(lines) + "\n"
