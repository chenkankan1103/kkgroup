#!/usr/bin/env python3
import sys

sys.path.insert(0, 'c:/Users/88697/Desktop/kkgroup')

try:
    import bots.bot as bot_module

    print(f'bots.bot = {bot_module}')
    print(f'bots.bot.client = {bot_module.client}')
    print(f'type = {type(bot_module.client)}')
except Exception as e:
    print(f'Error: {e}')
    import traceback

    traceback.print_exc()
