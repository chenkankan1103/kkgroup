#!/usr/bin/env python3
"""最終修復所有導入的腳本"""

# 修復 selection_views.py
selection_file = r'c:\Users\88697\Desktop\kkgroup\cogs\ui\views\selection_views.py'

with open(selection_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 替換所有出現
content = content.replace('from shop_commands.merchant.cannabis_config', 'from cogs.shop.merchant.cannabis_config')
content = content.replace('from uicommands.views.crop_operations', 'from .crop_operations')

with open(selection_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ selection_views.py 已修復")

# 修復 docs 中的測試文件
test_file = r'c:\Users\88697\Desktop\kkgroup\docs\uicommands_tests\cogs\locker_event_test.py'

try:
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('from uicommands.events', 'from cogs.ui.events')
    
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ docs/uicommands_tests/cogs/locker_event_test.py 已修復")
except FileNotFoundError:
    print(f"⚠️  {test_file} 不存在（可能是測試文件，可忽略）")

print("\n✅ 所有導入修復完成！")
