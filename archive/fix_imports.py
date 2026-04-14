#!/usr/bin/env python3
"""批量修復所有導入路徑的腳本"""
import re
import os
from pathlib import Path

def fix_file(file_path):
    """修復單個文件的導入"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # 替換 shop_commands 導入
        content = re.sub(r'from shop_commands\.merchant\.cannabis_config', 'from cogs.shop.merchant.cannabis_config', content)
        content = re.sub(r'from shop_commands\.merchant\.cannabis_farming', 'from cogs.shop.merchant.cannabis_farming', content)
        content = re.sub(r'from shop_commands\.merchant\.database', 'from cogs.shop.merchant.database', content)
        content = re.sub(r'from shop_commands\.merchant\.cannabis_unified', 'from cogs.shop.merchant.cannabis_unified', content)
        content = re.sub(r'from shop_commands\.merchant\.views', 'from cogs.shop.merchant.views', content)
        content = re.sub(r'from shop_commands\.merchant\.gambling', 'from cogs.shop.merchant.gambling', content)
        content = re.sub(r'from shop_commands\.shop', 'from cogs.shop', content)
        
        # 替換 uicommands 導入（針對 views）
        content = re.sub(r'from uicommands\.views\.crop_operations', 'from .crop_operations', content)
        content = re.sub(r'from uicommands\.views\.work_card', 'from .work_card', content)
        content = re.sub(r'from uicommands\.views', 'from ..views', content)
        
        # 替換 uicommands 導入（針對 utils）
        content = re.sub(r'from uicommands\.utils\.locker_embed_generator', 'from ..utils.locker_embed_generator', content)
        content = re.sub(r'from uicommands\.utils\.image_utils', 'from ..utils.image_utils', content)
        content = re.sub(r'from uicommands\.utils\.locker_cache', 'from ..utils.locker_cache', content)
        content = re.sub(r'from uicommands\.utils\.crop_utils', 'from ..utils.crop_utils', content)
        content = re.sub(r'from uicommands\.utils\.embed_utils', 'from ..utils.embed_utils', content)
        content = re.sub(r'from uicommands\.utils', 'from ..utils', content)
        
        # 替換 uicommands 導入（針對 events）
        content = re.sub(r'from uicommands\.events', 'from ..events', content)
        
        # 替換 uicommands 導入（針對 cogs）
        content = re.sub(r'from uicommands\.cogs\.locker_event_listener', 'from ..cogs.locker_event_listener', content)
        
        # 替換 commands 導入
        content = re.sub(r'from commands\.work_function\.work_system', 'from cogs.common.work_function.work_system', content)
        
        if content != original:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"❌ 錯誤在 {file_path}: {e}")
        return False

# 修復 cogs 目錄下的所有 Python 文件
cogs_dir = Path(r'c:\Users\88697\Desktop\kkgroup\cogs')
if cogs_dir.exists():
    count = 0
    for py_file in cogs_dir.rglob('*.py'):
        if fix_file(str(py_file)):
            print(f"✅ 修復: {py_file.relative_to(cogs_dir.parent)}")
            count += 1
    print(f"\n✅ 總共修復了 {count} 個文件")
else:
    print(f"❌ cogs 目錄不存在：{cogs_dir}")
