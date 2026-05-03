#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查anime_tracker是否能导入"""

import sys
import os

os.chdir('/home/e193752468/kkgroup')
sys.path.insert(0, '/home/e193752468/kkgroup')

try:
    print('[1] 尝试导入 cogs.ui.anime_tracker...')
    from cogs.ui.anime_tracker import AnimeTracker, setup
    print('[SUCCESS] AnimeTracker cog 导入成功')
    print(f'[INFO] AnimeTracker class: {AnimeTracker}')
    print(f'[INFO] setup function exists: {callable(setup)}')
    
    # 检查AnimeTracker中的关键方法
    print(f'[INFO] check_new_anime method: {hasattr(AnimeTracker, "check_new_anime")}')
    print(f'[INFO] send_weekly_stats method: {hasattr(AnimeTracker, "send_weekly_stats")}')
    
except ImportError as e:
    print(f'[ERROR] AnimeTracker 导入失败 (ImportError): {e}')
    import traceback
    traceback.print_exc()
except SyntaxError as e:
    print(f'[ERROR] AnimeTracker 语法错误: {e}')
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f'[ERROR] 其他错误: {e}')
    import traceback
    traceback.print_exc()
