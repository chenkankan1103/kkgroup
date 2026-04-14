#!/usr/bin/env python3
"""最終一次性修復所有導入"""

# 修復 selection_views.py
file_path = 'c:/Users/88697/Desktop/kkgroup/cogs/ui/views/selection_views.py'
test_file_path = 'c:/Users/88697/Desktop/kkgroup/docs/uicommands_tests/cogs/locker_event_test.py'

# 修復主文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 計數修復前
before_count = content.count('from shop_commands')

# 執行替換
content = content.replace(
    'from shop_commands.merchant.cannabis_config',
    'from cogs.shop.merchant.cannabis_config'
)
content = content.replace(
    'from uicommands.views.crop_operations',
    'from .crop_operations'
)

# 寫入
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

# 簽查修復後
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

after_count = content.count('from shop_commands')
print(f"selection_views.py: 修復前 {before_count} 個舊導入，修復後 {after_count} 個")

# 修復測試文件
try:
    with open(test_file_path, 'r', encoding='utf-8') as f:
        test_content = f.read()
    
    test_before = test_content.count('from uicommands.events')
    test_content = test_content.replace(
        'from uicommands.events',
        'from cogs.ui.events'
    )
    
    with open(test_file_path, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print(f"locker_event_test.py: 修復 {test_before} 個舊導入")
except FileNotFoundError:
    print("locker_event_test.py: 文件不存在（可忽略）")

print("\n✅ 所有修復完成！")
