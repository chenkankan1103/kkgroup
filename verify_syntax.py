#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""驗證所有修改的文件語法"""

import subprocess
import sys

files = [
    'shared/utils/view_registry.py',
    'cogs/shop/feedback_cog.py',
    'cogs/shop/HospitalMerchant.py',
    'cogs/ui/anime_tracker.py',
    'cogs/ui/welcome_message.py',
    'cogs/ui/views/locker_panel.py',
    'cogs/ui/views/work_card.py',
    'cogs/ui/views/update_panel.py',
    'cogs/ui/views/selection_views.py',
    'cogs/ui/views/personal_locker.py',
    'cogs/ui/views/crop_operations.py',
    'cogs/ui/personal_items.py',
    'cogs/ui/new_year_red_envelope.py',
    'cogs/shop/stock_market.py',
    'cogs/shop/merchant/cannabis_merchant_view.py',
    'cogs/shop/merchant/views.py',
    'cogs/shop/merchant/cannabis_merchant_view_v2.py',
    'cogs/common/announcement.py',
    'cogs/common/work_function/work_cog.py',
]

print("🔍 驗證所有修改文件的語法...\n")

errors = []
for file in files:
    try:
        result = subprocess.run(['python', '-m', 'py_compile', file], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ {file}")
        else:
            print(f"❌ {file}")
            errors.append((file, result.stderr))
    except Exception as e:
        print(f"⚠️  {file}: {e}")
        errors.append((file, str(e)))

print(f"\n📊 統計:")
print(f"  ✅ 成功: {len(files) - len(errors)}/{len(files)}")

if errors:
    print(f"  ❌ 錯誤: {len(errors)}")
    print("\n🔴 錯誤詳情:")
    for file, error in errors:
        print(f"\n{file}:")
        print(error[:200])
    sys.exit(1)
else:
    print(f"  ❌ 錯誤: 0")
    print("\n✅ 所有文件語法正確！")
    sys.exit(0)
