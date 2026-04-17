# -*- coding: utf-8 -*-
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
