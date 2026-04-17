#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
永久視圖完整重構腳本
自動將所有文件中的 timeout=None 視圖改為繼承 PersistentViewBase
"""

import os
import re
from pathlib import Path
from typing import Tuple, Optional

def add_import_if_needed(content: str) -> str:
    """在文件開頭添加 PersistentViewBase 導入"""
    if 'from shared.utils.view_registry import PersistentViewBase' in content:
        return content
    
    lines = content.split('\n')
    insert_idx = 0
    
    # 找到最後一個導入語句的位置
    for i, line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            insert_idx = i + 1
    
    # 如果沒有找到導入，在文件開頭插入（跳過編碼和文檔字符串）
    if insert_idx == 0:
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_idx = i
                break
            if i > 5:  # 最多檢查前5行
                break
    
    # 確保不會重複導入
    if insert_idx > 0:
        for i in range(max(0, insert_idx - 5), insert_idx):
            if 'PersistentViewBase' in lines[i]:
                return content
    
    lines.insert(insert_idx, 'from shared.utils.view_registry import PersistentViewBase')
    return '\n'.join(lines)

def refactor_view_class(content: str, view_name: str) -> Tuple[str, bool]:
    """
    將單個視圖類改為繼承 PersistentViewBase
    
    返回 (修改後內容, 是否進行了修改)
    """
    
    # 檢查是否已經使用 PersistentViewBase
    if f'class {view_name}(PersistentViewBase)' in content:
        return content, False
    
    # 檢查原始模式：class ViewName(View): ... super().__init__(timeout=None)
    pattern1 = rf'(class {view_name}\(View\):.*?def __init__\(self.*?\):.*?super\(\)\.__init__\(timeout=None\))'
    
    # 檢查是否匹配
    if not re.search(pattern1, content, re.DOTALL):
        return content, False
    
    # 替換 1：class 聲明
    content = re.sub(
        rf'class {view_name}\(View\):',
        f'class {view_name}(PersistentViewBase):',
        content
    )
    
    # 替換 2：super().__init__(timeout=None) 改為 super().__init__()
    content = re.sub(
        rf'(class {view_name}.*?def __init__\(self[^)]*\):.*?)super\(\)\.__init__\(timeout=None\)',
        r'\1super().__init__()',
        content,
        flags=re.DOTALL
    )
    
    return content, True

def process_file(file_path: str) -> Optional[str]:
    """
    處理單個文件，返回修改統計
    """
    
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"❌ 讀取失敗: {e}"
    
    # 如果已經完全使用新系統，跳過
    if 'from shared.utils.view_registry import PersistentViewBase' in content and 'timeout=None' not in content:
        return "⏭️  已完全重構"
    
    modified = False
    original_content = content
    
    # 找出所有 View 類
    view_pattern = r'class (\w+)\((?:View|discord\.ui\.View|PersistentViewBase)\):'
    views_found = re.findall(view_pattern, content)
    
    if not views_found:
        return "⏭️  沒有找到視圖類"
    
    # 檢查是否有 timeout=None
    if 'timeout=None' not in content:
        return "⏭️  沒有 timeout=None"
    
    # 添加導入
    content = add_import_if_needed(content)
    modified = True
    
    # 修改每個視圖類
    for view_name in views_found:
        new_content, view_modified = refactor_view_class(content, view_name)
        if view_modified:
            content = new_content
            modified = True
    
    if not modified:
        return "⏭️  無需修改"
    
    # 保存文件
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ 已修改"
    except Exception as e:
        return f"❌ 保存失敗: {e}"

# 要修改的文件列表
files_to_process = [
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
    'cogs/common/fraud_voice.py',
    'cogs/common/work_function/work_cog.py',
]

print("🔄 開始批量重構永久視圖...\n")

success_count = 0
skip_count = 0
error_count = 0

for file_path in files_to_process:
    result = process_file(file_path)
    
    if result is None:
        print(f"⚠️  {file_path}: 文件不存在")
        error_count += 1
    elif "✅" in result:
        print(f"✅ {file_path}: {result}")
        success_count += 1
    elif "⏭️" in result:
        print(f"⏭️  {file_path}: {result}")
        skip_count += 1
    else:
        print(f"❌ {file_path}: {result}")
        error_count += 1

print(f"\n📊 統計:")
print(f"  ✅ 成功修改: {success_count}")
print(f"  ⏭️  跳過: {skip_count}")
print(f"  ❌ 失敗/不存在: {error_count}")
print(f"\n✅ 批量重構完成！")
