#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix remaining imports by directly modifying specific lines
"""

import sys

file_path = r"c:\Users\88697\Desktop\kkgroup\cogs\ui\views\selection_views.py"

# Read all lines
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines to fix (0-indexed, so subtract 1 from grep output)
# grep showed line 324 and 558
target_lines = {
    323: "                    from cogs.shop.merchant.cannabis_config import CANNABIS_SHOP\n",  # Line 324 (324-1)
    557: "                    from cogs.shop.merchant.cannabis_config import CANNABIS_SHOP\n",  # Line 558 (558-1)
}

fixed_count = 0

# Check and fix
print("Checking target lines...")
for line_num, new_content in target_lines.items():
    if line_num < len(lines):
        old_line = lines[line_num]
        print(f"Line {line_num + 1} before: {old_line.rstrip()}")
        
        # Check if it contains the old import
        if "from shop_commands.merchant.cannabis_config" in old_line:
            lines[line_num] = new_content
            fixed_count += 1
            print(f"Line {line_num + 1} after:  {lines[line_num].rstrip()}")
            print("  ✅ Fixed")
        else:
            print("  ⚠️ Line doesn't contain expected import")
    else:
        print(f"Line {line_num + 1} out of range (file has {len(lines)} lines)")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"\n✅ Fixed {fixed_count} imports!")
