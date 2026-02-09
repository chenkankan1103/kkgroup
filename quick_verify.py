#!/usr/bin/env python3
"""快速驗證部署狀態"""

import subprocess
import os

# 1. 檢查本地文件
local_file = "commands/kkcoin_visualizer_v2.py"
if os.path.exists(local_file):
    size = os.path.getsize(local_file)
    print(f"📁 本地文件: {size:,} bytes")
    
    # 檢查是否包含新配置
    with open(local_file, 'r', encoding='utf-8') as f:
        content = f.read()
        has_config = "COLOR_HEX_TITLE = '#3c3c3c'" in content
        has_font_path = 'NotoSansCJKtc-Regular.otf' in content
        print(f"   ✅ 配色常數: {'是' if has_config else '否'}")
        print(f"   ✅ 字型路徑: {'是' if has_font_path else '否'}")

# 2. 驗證遠程部署
print("\n🔍 驗證遠程部署...")

# 檢查檔案大小和行數
cmd = ["ssh", "gcp-kkgroup", 
       "stat /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py 2>/dev/null || echo 'NOT_FOUND'"]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

if "NOT_FOUND" not in result.stdout:
    print(f"   ✅ 遠程文件存在")
    
    # 檢查是否包含新配置
    cmd = ["ssh", "gcp-kkgroup",
           "grep 'COLOR_HEX_TITLE' /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py 2>/dev/null && echo 'HAS_CONFIG' || echo 'NO_CONFIG'"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if "HAS_CONFIG" in result.stdout or "#3c3c3c" in result.stdout:
        print(f"   ✅ 已部署改進版本")
    else:
        print(f"   ⚠️  可能是舊版本，重新上傳中...")
        
        # 重新上傳
        cmd = ["scp", local_file, "gcp-kkgroup:/home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode == 0:
            print(f"   ✅ 已重新上傳")
        else:
            print(f"   ❌ 上傳失敗")
else:
    print(f"   ❌ 遠程文件不存在")

print("\n✅ 驗證完成")
