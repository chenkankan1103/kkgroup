#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

files = [
    'cogs/common/google_sheets_sync.py',
    'cogs/common/trends_lottery.py',
    'cogs/common/memory_manager.py'
]

for f in files:
    print(f'\n📄 {f}')
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
            cmds = re.findall(r'@app_commands\.command\(name=["\']([^"\']+)["\']', content)
            if cmds:
                for cmd in cmds:
                    print(f'   - {cmd}')
            else:
                print('   (no commands found)')
    except Exception as e:
        print(f'   ERROR: {e}')
