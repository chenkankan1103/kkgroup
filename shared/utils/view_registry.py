# -*- coding: utf-8 -*-
"""
永久視圖註冊系統
中央管理所有需要註冊的永久視圖（timeout=None）

重要: 
- 視圖是在被發送到 Discord 時自動註冊的
- 需要參數的視圖應該由各自的 cog 在 setup() 時管理
- 這個系統提供調試和監控框架
"""

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



