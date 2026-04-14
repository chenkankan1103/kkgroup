#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

file_path = r"c:\Users\88697\Desktop\kkgroup\cogs\ui\views\selection_views.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check for old imports before
old_count_1 = content.count("from shop_commands.merchant.cannabis_config")
old_count_2 = content.count("from uicommands.views.crop_operations")

print(f"Before: shop_commands={old_count_1}, uicommands={old_count_2}", file=sys.stderr)

# Fix both patterns
content = content.replace(
    "from shop_commands.merchant.cannabis_config",
    "from cogs.shop.merchant.cannabis_config"
)
content = content.replace(
    "from uicommands.views.crop_operations",
    "from .crop_operations"
)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(file_path, 'r', encoding='utf-8') as f:
    content_check = f.read()

new_count_1 = content_check.count("from shop_commands.merchant.cannabis_config")
new_count_2 = content_check.count("from uicommands.views.crop_operations")

print(f"After: shop_commands={new_count_1}, uicommands={new_count_2}", file=sys.stderr)
print("DONE", file=sys.stderr)
