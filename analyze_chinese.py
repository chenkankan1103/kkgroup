#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

chinese_count = len(re.findall(r'[\u4e00-\u9fff]', content))
print(f'Found {chinese_count} Chinese characters in bot.py')

lines_with_chinese = []
for i, line in enumerate(content.split('\n'), 1):
    if re.search(r'[\u4e00-\u9fff]', line):
        lines_with_chinese.append((i, line.strip()[:90]))

print(f'\nLines with Chinese (first 15):')
for line_no, line_content in lines_with_chinese[:15]:
    print(f'Line {line_no}: {line_content}')

if len(lines_with_chinese) > 15:
    print(f'... and {len(lines_with_chinese) - 15} more lines')
