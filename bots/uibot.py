# -*- coding: utf-8 -*-
import asyncio
import os
import sys

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

from shared.db.async_adapter import close_async_db, init_async_db
from shared.db.feature_usage = track_discord_interaction
from shared.utils.bot_status = build_discord_activity
from shared.utils.mutual_rescue = ensure_mutual_rescue_monitor
from status_dashboard = (initialize_dashboard, load_message_ids,
                              update_dashboard_logs)