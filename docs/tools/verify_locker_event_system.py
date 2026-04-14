#!/usr/bin/env python3
"""
置物櫃事件驅動系統 - 快速驗證工具
驗證事件系統是否正常初始化並可運作
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

def verify_event_system():
    """驗證事件系統的各個元件"""
    print("=" * 60)
    print("🔍 置物櫃事件驅動系統驗證")
    print("=" * 60)
    
    # 1. 驗證事件定義
    print("\n[1/5] 驗證事件類定義...")
    try:
        from uicommands.events import (
            EquipmentChangedEvent,
            CurrencyChangedEvent,
            HealthChangedEvent,
            InventoryChangedEvent,
            FullRefreshEvent,
            SyncRequestedEvent,
        )
        print("✅ 所有事件類已成功載入")
        
        # 測試建立事件實例
        event = CurrencyChangedEvent(
            user_id=123456,
            changed_fields={'kkcoin', 'xp'}
        )
        print(f"✅ 事件實例建立成功: {event}")
    except Exception as e:
        print(f"❌ 事件類載入失敗: {e}")
        return False
    
    # 2. 驗證快取系統
    print("\n[2/5] 驗證快取系統...")
    try:
        from uicommands.utils.locker_cache import locker_cache, LockerCache
        print(f"✅ 快取系統已載入")
        print(f"   快取大小: {len(locker_cache.paperdoll_cache)}")
        
        # 測試 hash 生成
        test_user_data = {
            'face': 12345,
            'hair': 67890,
            'skin': 1,
            'equip_0': 100,
        }
        hash_val = LockerCache.build_paperdoll_hash(test_user_data)
        print(f"✅ Hash 生成成功: {hash_val[:16]}...")
    except Exception as e:
        print(f"❌ 快取系統驗證失敗: {e}")
        return False
    
    # 3. 驗證事件監聽器 Cog
    print("\n[3/5] 驗證事件監聽器 Cog...")
    try:
        from uicommands.cogs.locker_event_listener import LockerEventListenerCog
        print(f"✅ LockerEventListenerCog 已成功載入")
        
        # 檢查監聽器方法
        expected_methods = [
            'on_equipment_changed',
            'on_currency_changed',
            'on_health_changed',
            'on_full_refresh',
        ]
        
        for method_name in expected_methods:
            if hasattr(LockerEventListenerCog, method_name):
                print(f"   ✅ 監聽器方法存在: {method_name}")
            else:
                print(f"   ⚠️  監聽器方法缺失: {method_name}")
    except Exception as e:
        print(f"❌ 事件監聽器驗證失敗: {e}")
        return False
    
    # 4. 驗證測試 Cog
    print("\n[4/5] 驗證測試 Cog...")
    try:
        from uicommands.cogs.locker_event_test import LockerEventTestCog
        print(f"✅ LockerEventTestCog 已成功載入")
    except Exception as e:
        print(f"❌ 測試 Cog 驗證失敗: {e}")
        return False
    
    # 5. 驗證 DB Migration
    print("\n[5/5] 驗證 DB Migration...")
    try:
        from tools.migrate_locker_event_system import migrate_locker_event_columns
        print(f"✅ Migration 腳本已正確位置")
        print(f"   可使用: python tools/migrate_locker_event_system.py 執行")
    except Exception as e:
        print(f"❌ Migration 驗證失敗: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有驗證通過！事件系統已準備就緒")
    print("=" * 60)
    print("\n📚 後續步驟:")
    print("1. 執行 migration: python tools/migrate_locker_event_system.py")
    print("2. 啟動 bot: python bot.py")
    print("3. 在 Discord 使用 /test_locker_* 命令測試事件系統")
    print("4. 檢查日誌輸出確認事件監聽器正常工作")
    
    return True


if __name__ == '__main__':
    success = verify_event_system()
    sys.exit(0 if success else 1)
