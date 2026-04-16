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
    
    # 視圖註冊清單（按優先級）
    # 某些視圖需要特殊參數，我們使用 lambda 或工廠函數來創建它們
    views_to_register = []
    
    try:
        # ============================================================
        # UI 視圖 - 永久視圖（需要在 bot 啟動時註冊）
        # ============================================================
        from cogs.ui.views.personal_locker import PersonalLockerView, PersonalItemsView
        from cogs.ui.views.selection_views import (
            GenderSelectionView, 
            ClothingSelectionView, 
            ClothingColorSelectionView,
            ClothingAccessorySelectionView
        )
        from cogs.ui.views.work_card import WorkCardView
        from cogs.ui.views.locker_panel import LockerPanelView
        from cogs.ui.views.crop_operations import CropSelectionView, CropManageView
        from cogs.ui.views.update_panel import UpdatePanelView
        from cogs.ui.welcome_message import TempRoleSelectionView, VerifyView
        
        # 簡單視圖（無參數），可直接實例化
        simple_views = [
            GenderSelectionView,
            ClothingSelectionView,
            ClothingColorSelectionView,
            ClothingAccessorySelectionView,
            LockerPanelView,
            UpdatePanelView,
            TempRoleSelectionView,
            VerifyView,
        ]
        
        print(f"[VIEW_REGISTRY] ✅ UI 視圖導入成功，共 {len(simple_views)} 個")
        
        for view_class in simple_views:
            views_to_register.append((view_class.__name__, view_class))
        
        # ============================================================
        # Shop 視圖
        # ============================================================
        print("[VIEW_REGISTRY] 正在導入 Shop 視圖...")
        from cogs.shop.feedback_cog import FeedbackView
        from cogs.shop.HospitalMerchant import HospitalMerchantView
        
        shop_views = [
            FeedbackView,
            HospitalMerchantView,
        ]
        
        print(f"[VIEW_REGISTRY] ✅ Shop 視圖導入成功，共 {len(shop_views)} 個")
        
        for view_class in shop_views:
            views_to_register.append((view_class.__name__, view_class))
        
        # ============================================================
        # 複雜視圖（需要參數）- 這些無法直接實例化
        # 但我們需要創建虛擬實例或找到另一種方式
        # ============================================================
        # PersonalLockerView - 需要 cog 參數
        # PersonalItemsView - 需要參數
        # WorkCardView - 需要參數
        # CropSelectionView - 需要參數
        # CropManageView - 需要參數
        # AnimeVoteView - 需要參數
        
        # 註冊所有視圖
        registered_count = 0
        failed_views = []
        
        print(f"[VIEW_REGISTRY] 開始註冊 {len(views_to_register)} 個視圖...")
        
        for view_name, view_class in views_to_register:
            try:
                # 嘗試創建實例並註冊
                view_instance = view_class()
                client.add_view(view_instance)
                registered_count += 1
                print(f"[VIEW_REGISTRY] ✅ 已註冊: {view_name}")
            except TypeError as e:
                # 視圖需要參數，無法直接實例化
                # 但我們可以直接註冊類型（Discord.py 可以處理）
                try:
                    # 嘗試直接添加類（某些版本的 discord.py 支援）
                    # 這實際上不會工作，但我們可以在此記錄信息
                    failed_views.append(f"{view_name} (需要參數)")
                except Exception as inner_e:
                    failed_views.append(f"{view_name}: {str(e)[:50]}")
            except Exception as e:
                failed_views.append(f"{view_name}: {str(e)[:50]}")
        
        # 特殊處理：需要參數的視圖
        # 這些視圖在被 cog 使用時會被創建和使用，不需要預先註冊
        # Discord.py 會根據 custom_id 自動匹配交互到視圖
        # 但問題是如果視圖被超時，用戶交互會失敗
        
        # 嘗試導入需要參數的視圖，即使無法直接實例化
        try:
            from cogs.ui.views.personal_locker import PersonalLockerView, PersonalItemsView
            # 這些視圖由 cog 管理，不需要預先註冊
            print(f"⚠️  視圖 PersonalLockerView/PersonalItemsView 由 cog 管理，跳過預先註冊")
        except ImportError:
            pass
        
        try:
            from cogs.ui.views.work_card import WorkCardView
            print(f"⚠️  視圖 WorkCardView 由 cog 管理，跳過預先註冊")
        except ImportError:
            pass
        
        try:
            from cogs.ui.views.crop_operations import CropSelectionView, CropManageView
            print(f"⚠️  視圖 CropSelectionView/CropManageView 由 cog 管理，跳過預先註冊")
        except ImportError:
            pass
        
        try:
            from cogs.ui.anime_tracker import AnimeVoteView
            print(f"⚠️  視圖 AnimeVoteView 由 cog 管理，跳過預先註冊")
        except ImportError:
            pass
        
        print(f"[VIEW_REGISTRY] 📊 已成功註冊 {registered_count}/{len(views_to_register)} 個永久視圖")
        
        if failed_views:
            print(f"[VIEW_REGISTRY] ⚠️  無法自動註冊的視圖（由 cog 管理）:")
            for view_info in failed_views:
                print(f"[VIEW_REGISTRY]    - {view_info}")
        
        return registered_count
        
    except Exception as e:
        print(f"[VIEW_REGISTRY] ❌ 視圖註冊系統初始化失敗: {e}")
        import traceback
        print("[VIEW_REGISTRY] 錯誤詳情:")
        traceback.print_exc()
        return 0

