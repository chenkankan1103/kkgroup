# -*- coding: utf-8 -*-
"""
Aggregated imports for bots to reduce tight coupling with shared modules.
Bots should import from this module instead of importing directly from
submodules to centralize dependencies and provide a clearer interface.
"""

# Database
from shared.db.async_adapter import close_async_db, init_async_db
# Feature usage
from shared.db.feature_usage import track_discord_interaction
# Bot status
from shared.utils.bot_status import build_discord_activity
# Mutual rescue
from shared.utils.mutual_rescue import ensure_mutual_rescue_monitor
# Status dashboard (used by shopbot and uibot)
from status_dashboard import (  # noqa: F401
    initialize_dashboard,
    load_message_ids,
    update_dashboard_logs,
)

__all__ = [
    "close_async_db",
    "init_async_db",
    "track_discord_interaction",
    "build_discord_activity",
    "ensure_mutual_rescue_monitor",
    "initialize_dashboard",
    "load_message_ids",
    "update_dashboard_logs",
]