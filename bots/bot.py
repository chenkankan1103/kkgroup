# -*- coding: utf-8 -*-
import asyncio
import os
import sys

# Bootstrap environment setup
from shared.bootstrap import setup_environment
setup_utf8_logging = setup_environment()

import logging
from datetime import datetime

import discord
import requests
from discord.ext import commands, tasks
from discord.ext.commands import ExtensionError
from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler

from shared.db.async_adapter import close_async_db, init_async_db
from shared.db.feature_usage import track_discord_interaction
from shared.utils.bot_status import build_discord_activity
from shared.utils.mutual_rescue import ensure_mutual_rescue_monitor