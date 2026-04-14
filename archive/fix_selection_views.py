#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix remaining import paths in selection_views.py
"""

file_path = r"c:\Users\88697\Desktop\kkgroup\cogs\ui\views\selection_views.py"

# Read the file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Track replacements
replacements = [
    ("from shop_commands.merchant.cannabis_config import CANNABIS_SHOP", 
     "from cogs.shop.merchant.cannabis_config import CANNABIS_SHOP"),
    ("from uicommands.views.crop_operations import CropOperationView", 
     "from .crop_operations import CropOperationView"),
]

print("Before fixes:")
for old, new in replacements:
    count = content.count(old)
    print(f"  '{old}': {count} occurrences")

# Apply replacements
for old, new in replacements:
    content = content.replace(old, new)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\nAfter fixes:")
for old, new in replacements:
    count = content.count(old)
    print(f"  '{old}': {count} occurrences")

print("\n✅ All imports fixed!")
