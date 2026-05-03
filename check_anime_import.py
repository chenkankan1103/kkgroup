#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查Bot中加载的所有cogs"""
import subprocess
import sys

# 运行 Discord bot 状态检查
cmd = """
import sys
import discord
from discord.ext import commands

# 创建虚拟bot检查加载的cog
class DummyBot(commands.Bot):
    async def setup_hook(self):
        pass

# 检查 cogs/ui/anime_tracker.py 是否能导入
try:
    from cogs.ui.anime_tracker import AnimeTracker, setup
    print('[SUCCESS] AnimeTracker cog 可以导入')
    print(f'[INFO] AnimeTracker class: {AnimeTracker}')
    print(f'[INFO] setup function: {setup}')
except ImportError as e:
    print(f'[ERROR] AnimeTracker 导入失败: {e}')
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f'[ERROR] 其他错误: {e}')
    import traceback
    traceback.print_exc()
"""

result = subprocess.run([sys.executable, "-c", cmd], capture_output=True, text=True, cwd="/home/e193752468/kkgroup")
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
print("Return code:", result.returncode)
