# -*- coding: utf-8 -*-
import asyncio
import os
import sys

# Fix sys.path for proper imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Bootstrap environment setup
from shared.bootstrap import setup_environment
setup_utf8_logging = setup_environment()

import logging
import syslog
from datetime import datetime

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler

from shared.bot_integrations import (
    close_async_db,
    init_async_db,
    track_discord_interaction,
    build_discord_activity,
    ensure_mutual_rescue_monitor,
)
from status_dashboard import (initialize_dashboard, load_message_ids,
                              update_dashboard_logs)