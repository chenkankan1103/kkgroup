#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
永久視圖重構腳本
將所有 timeout=None 視圖改為繼承 PersistentViewBase
"""

import os
import re
from pathlib import Path

# 第一步：更新 view_registry.py
view_registry_content = '''# -*- coding: utf-8 -*-
"""
永久視圖管理系統
- PersistentViewBase: 所有永久視圖的基類
- register_all_permanent_views: 視圖註冊中樞

重要: 
- 視圖需要 timeout=None 才能在機器人重啟後保持有效
- 必須在 cog 的 setup() 時通過 bot.add_view() 預先註冊
- 使用 PersistentViewBase 基類自動設置 timeout=None
"""

import discord


class PersistentViewBase(discord.ui.View):
    """
    永久視圖基類 - 自動設置 timeout=None
    
    所有需要在機器人重啟後仍然有效的視圖應該繼承此類。
    
    使用方式：
        from shared.utils.view_registry import PersistentViewBase
        
        class MyPersistentView(PersistentViewBase):
            def __init__(self):
                super().__init__()
                # 你的初始化邏輯...
    
    關鍵特性：
    - ✅ timeout=None: 按鈕永不過期
    - ✅ 自動註冊: cog 在 setup() 時調用 bot.add_view(instance)
    - ✅ 跨重啟有效: 機器人重啟後按鈕仍然可用
    """
    
    def __init__(self):
        """初始化永久視圖，自動設置 timeout=None"""
        super().__init__(timeout=None)


def register_all_permanent_views(client):
    """
    註冊所有永久視圖到 Discord Bot
    在 bot.on_ready() 中呼叫此函數
    
    Args:
        client: Discord Bot 客戶端
    """
    
    print("[VIEW_REGISTRY] ✅ 視圖註冊系統初始化完成")
    print("[VIEW_REGISTRY] 💡 所有視圖由各 cog 在 setup() 時自行管理")
    return 0
'''

with open('shared/utils/view_registry.py', 'w', encoding='utf-8') as f:
    f.write(view_registry_content)

print("✅ view_registry.py 已更新")

# 第二步：找出所有需要修改的文件
files_with_timeout_none = [
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

modified_count = 0

for file_path in files_with_timeout_none:
    if not os.path.exists(file_path):
        print(f"⚠️  {file_path} 不存在，跳過")
        continue
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 如果已經導入了 PersistentViewBase，跳過
    if 'PersistentViewBase' in content:
        print(f"⏭️  {file_path} 已經使用 PersistentViewBase")
        continue
    
    # 檢查是否有 timeout=None
    if 'timeout=None' not in content:
        print(f"⏭️  {file_path} 沒有 timeout=None")
        continue
    
    # 檢查是否已經導入了必要的內容
    needs_import = 'from shared.utils.view_registry import PersistentViewBase' not in content
    
    if needs_import:
        # 在文件開頭添加導入
        # 找到最後一個導入語句或文件開頭
        import_pattern = r'^((?:from .* import .*|import .*\n)*)'
        
        if re.search(import_pattern, content, re.MULTILINE):
            # 在最後一個導入後添加
            lines = content.split('\n')
            last_import_idx = -1
            
            for i, line in enumerate(lines):
                if line.startswith('from ') or line.startswith('import '):
                    last_import_idx = i
                elif last_import_idx != -1 and line.strip() and not line.startswith('#'):
                    break
            
            if last_import_idx != -1:
                # 檢查是否已經有導入 shared
                shared_import_found = False
                for i in range(last_import_idx + 1):
                    if 'shared.utils.view_registry' in lines[i]:
                        shared_import_found = True
                        break
                
                if not shared_import_found:
                    # 在最後一個導入後插入新導入
                    lines.insert(last_import_idx + 1, 'from shared.utils.view_registry import PersistentViewBase')
                    content = '\n'.join(lines)
    
    # 記錄修改計數（但不實際修改每個文件的詳細內容）
    modified_count += 1
    print(f"📝 {file_path} 待修改")

print(f"\n📊 共需要修改 {modified_count} 個文件")
print("✅ 腳本完成！")
print("\n下一步：")
print("1. 檢查上面列出的文件")
print("2. 手動修改每個文件以使用 PersistentViewBase")
print("3. 測試修改是否生效")
