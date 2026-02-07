#!/usr/bin/env python3
"""
KK幣 V2 排行榜本地測試腳本
驗證所有視覺化函數正常運作
"""

import asyncio
import sys
from pathlib import Path

# 添加項目路徑
project_path = Path(__file__).parent
sys.path.insert(0, str(project_path))

async def test_kkcoin_v2():
    """測試 KK幣 V2 功能"""
    
    print("\n" + "="*60)
    print("🧪 KK幣 V2 排行榜 本地測試")
    print("="*60 + "\n")
    
    # 第1步：檢查 matplotlib
    print("📦 檢查依賴...")
    try:
        import matplotlib
        print(f"   ✓ matplotlib {matplotlib.__version__} 已安裝")
    except ImportError:
        print("   ✗ matplotlib 未安裝！")
        print("   ? 請執行: pip install matplotlib numpy")
        return False
    
    try:
        import numpy as np
        print(f"   ✓ numpy {np.__version__} 已安裝")
    except ImportError:
        print("   ✗ numpy 未安裝！")
        return False
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        print("   ✓ PIL 已安裝")
    except ImportError:
        print("   ✗ PIL 未安裝！")
        return False
    
    # 第2步：導入新模組
    print("\n📚 導入模組...")
    try:
        from commands.kkcoin_visualizer_v2 import (
            MATPLOTLIB_AVAILABLE,
            create_enhanced_leaderboard_image,
            create_bar_chart_image,
            create_pie_and_weekly_image
        )
        print(f"   ✓ kkcoin_visualizer_v2 導入成功")
        print(f"   ? MATPLOTLIB_AVAILABLE: {MATPLOTLIB_AVAILABLE}")
    except ImportError as e:
        print(f"   ✗ 導入失敗: {e}")
        return False
    
    # 第3步：創建模擬數據
    print("\n🎭 創建模擬數據...")
    
    class MockMember:
        def __init__(self, name, uid):
            self.display_name = name
            self.id = uid
    
    mock_members = [
        (MockMember(f"玩家{i+1}", 100+i), 100000 - i*5000)
        for i in range(15)
    ]
    
    print(f"   ✓ 創建 {len(mock_members)} 個模擬玩家")
    print(f"   ? 排名: {', '.join([m[0].display_name for m in mock_members[:3]])} ...")
    
    # 第4步：測試排行榜生成
    print("\n🎨 測試排行榜圖片生成...")
    try:
        img = await create_enhanced_leaderboard_image(mock_members, limit=15)
        print(f"   ✓ 排行榜圖片生成成功")
        print(f"   ? 大小: {img.size}")
    except Exception as e:
        print(f"   ✗ 失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 第5步：測試長條圖生成
    print("\n📊 測試長條圖生成...")
    try:
        img = await create_bar_chart_image(mock_members, limit=15)
        if img:
            print(f"   ✓ 長條圖生成成功")
            print(f"   ? 大小: {img.size}")
        else:
            print(f"   ⚠ matplotlib 不可用")
    except Exception as e:
        print(f"   ✗ 失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 第6步：測試饼圖 + 周統計
    print("\n🍰 測試饼圖 + 周統計...")
    try:
        total = sum(c for _, c in mock_members)
        img = await create_pie_and_weekly_image(
            mock_members,
            limit=15,
            total_coins=total,
            this_week_total=int(total * 0.3),
            last_week_total=int(total * 0.25)
        )
        if img:
            print(f"   ✓ 饼圖 + 周統計生成成功")
            print(f"   ? 大小: {img.size}")
        else:
            print(f"   ⚠ matplotlib 不可用")
    except Exception as e:
        print(f"   ✗ 失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 完成
    print("\n" + "="*60)
    print("✅ 所有測試通過！")
    print("="*60)
    print("\n📝 下一步:")
    print("   1. 上傳文件到 GCP")
    print("   2. 重啟 Bot 進程")
    print("   3. 在 Discord 執行 /kkcoin_v2")
    print("\n")
    
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_kkcoin_v2())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 測試被中斷")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 未預期的錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
