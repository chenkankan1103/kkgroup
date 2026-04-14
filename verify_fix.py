#!/usr/bin/env python3
"""修復 selection_views.py 中的所有舊導入"""

file_path = r'c:\Users\88697\Desktop\kkgroup\cogs\ui\views\selection_views.py'

# 讀取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 打印修復前的統計
old_count = content.count('from shop_commands.merchant.cannabis_config')
new_count = content.count('from cogs.shop.merchant.cannabis_config')
print(f"修復前：舊導入 {old_count} 個，新導入 {new_count} 個")

# 執行雙重替換來確保
content = content.replace('from shop_commands.merchant.cannabis_config', 'from cogs.shop.merchant.cannabis_config')
content = content.replace('from uicommands.views.crop_operations', 'from .crop_operations')

# 寫入文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

# 驗證修復
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_count_after = content.count('from shop_commands.merchant.cannabis_config')
new_count_after = content.count('from cogs.shop.merchant.cannabis_config')
uicommands_count = content.count('from uicommands.views.crop_operations')
print(f"修復後：舊導入 {old_count_after} 個，新導入 {new_count_after} 個，uicommands crop_operations {uicommands_count} 個")

if old_count_after == 0 and uicommands_count == 0:
    print("✅ selection_views.py 已完全修復！")
else:
    print("⚠️  仍然存在未修復的導入")
