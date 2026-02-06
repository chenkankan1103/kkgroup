#!/usr/bin/env python3
"""
驗證所有關鍵依賴是否已正確安裝
"""

import sys

def check_dependency(name, module_name=None):
    """檢查依賴是否已安裝"""
    if module_name is None:
        module_name = name
    
    try:
        mod = __import__(module_name)
        version = getattr(mod, '__version__', 'unknown')
        print(f"✅ {name:20} - {version}")
        return True
    except ImportError as e:
        print(f"❌ {name:20} - 未安裝")
        return False

def main():
    print("=" * 60)
    print("🔍 KK Garden Bot 依賴檢查")
    print("=" * 60)
    
    dependencies = [
        ("Discord.py", "discord"),
        ("aiohttp", "aiohttp"),
        ("Pillow", "PIL"),
        ("matplotlib", "matplotlib"),
        ("numpy", "numpy"),
        ("aiosqlite", "aiosqlite"),
        ("python-dotenv", "dotenv"),
        ("requests", "requests"),
        ("aiofiles", "aiofiles"),
    ]
    
    results = []
    for name, module in dependencies:
        results.append(check_dependency(name, module))
    
    print("=" * 60)
    
    if all(results):
        print("✅ 所有依賴已正確安裝")
        print("\n✨ 系統準備就緒！可以啟動 BOT")
        sys.exit(0)
    else:
        print("❌ 部分依賴缺失")
        print("\n💡 請執行: pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
