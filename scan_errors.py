#!/usr/bin/env python3
# -*- coding: utf-8 -*-

with open('work_cog_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("=== work_cog_fixed.py 引號掃描 ===\n")
errors = []
for i, line in enumerate(lines, 1):
    quote_count = line.count('"') - line.count('\\"')
    if quote_count % 2 == 1 and not line.strip().startswith('#'):
        errors.append((i, line.rstrip()))

print(f"找到 {len(errors)} 行可能有引號問題:\n")
for line_no, line_content in errors[:50]:
    print(f"Line {line_no}: {line_content[:100]}")
