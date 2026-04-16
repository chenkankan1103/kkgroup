# -*- coding: utf-8 -*-
"""
永久視圖註冊系統
中央管理所有需要註冊的永久視圖（timeout=None）
"""

def register_all_permanent_views(client):
    """
    註冊所有永久視圖到 Discord Bot
    在 bot.on_ready() 中呼叫此函數
    
    Args:
        client: Discord Bot 客戶端
    
    Example:
        @client.event
        async def on_ready():
            register_all_permanent_views(client)
    """
    
    print("[VIEW_REGISTRY] 開始註冊永久視圖...")
    
    views_to_register = []
    registered_count = 0
    
    try:
        # ============================================================
        # Shop 視圖 - 這些是最重要的
        # ============================================================
        print("[VIEW_REGISTRY] 正在導入 Shop 視圖...")
        
        try:
            from cogs.shop.feedback_cog import FeedbackView
            views_to_register.append(("FeedbackView", FeedbackView))
            print("[VIEW_REGISTRY] ✅ FeedbackView 導入成功")
        except ImportError as e:
            print(f"[VIEW_REGISTRY] ⚠️  FeedbackView 導入失敗: {e}")
        
        try:
            from cogs.shop.HospitalMerchant import HospitalMerchantView
            views_to_register.append(("HospitalMerchantView", HospitalMerchantView))
            print("[VIEW_REGISTRY] ✅ HospitalMerchantView 導入成功")
        except ImportError as e:
            print(f"[VIEW_REGISTRY] ⚠️  HospitalMerchantView 導入失敗: {e}")
        
        # ============================================================
        # 註冊所有收集到的視圖
        # ============================================================
        print(f"[VIEW_REGISTRY] 開始註冊 {len(views_to_register)} 個視圖...")
        
        for view_name, view_class in views_to_register:
            try:
                view_instance = view_class()
                client.add_view(view_instance)
                registered_count += 1
                print(f"[VIEW_REGISTRY] ✅ 已註冊: {view_name}")
            except TypeError as e:
                print(f"[VIEW_REGISTRY] ⚠️  {view_name} 需要參數，跳過: {str(e)[:50]}")
            except Exception as e:
                print(f"[VIEW_REGISTRY] ❌ {view_name} 註冊失敗: {str(e)[:80]}")
        
        print(f"[VIEW_REGISTRY] 📊 已成功註冊 {registered_count} 個永久視圖")
        print("[VIEW_REGISTRY] 💡 其他視圖由各 cog 在 setup() 時自行註冊")
        
        return registered_count
        
    except Exception as e:
        print(f"[VIEW_REGISTRY] ❌ 視圖註冊系統異常: {e}")
        import traceback
        traceback.print_exc()
        return 0

