#!/usr/bin/env python3
"""
最終驗證部署狀態
"""

import subprocess
import time

print("=" * 70)
print("🔍 最終驗證部署狀態")
print("=" * 70)

checks = [
    ("📁 文件驗證", "ls -lh /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"),
    ("🔢 文件行數", "wc -l /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"),
    ("🔌 Bot 進程", "ps aux | grep -E '[b]ot.py' | wc -l"),
    ("🆔 Bot PID", "ps aux | grep -E '[b]ot.py' | awk '{print $2}' | head -1"),
]

for check_name, cmd in checks:
    try:
        result = subprocess.run(
            ["ssh", "gcp-kkgroup", cmd],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = result.stdout.strip()
        if output:
            # 根據檢查項目格式化輸出
            if "wc -l" in cmd or "process" in cmd.lower():
                lines = output.split('\n')
                summary = lines[-1] if lines else output
                print(f"{check_name:20} ✅ {summary}")
            elif "PID" in check_name:
                print(f"{check_name:20} ✅ PID {output}")
            else:
                print(f"{check_name:20} ✅ {output}")
        else:
            print(f"{check_name:20} ⚠️ 無結果")
            
    except subprocess.TimeoutExpired:
        print(f"{check_name:20} ⏱️ 超時")
    except Exception as e:
        print(f"{check_name:20} ❌ {str(e)[:50]}")

print("\n" + "=" * 70)
print("✅ 驗證完成！")
print("=" * 70)

print("""
📝 下一步驟:

1️⃣ 在 Discord 中測試升級版排行榜:
   輸入: /kkcoin_v2

2️⃣ 預期結果:
   ✨ 立即看到 3 張改進的圖表
   ① 排行榜 - 前 15 名 (金銀銅特效)
   ② 長條圖 - 漸變色長條
   ③ 饼圖 + 周統計 - 豐富配色

3️⃣ 如需自動更新功能:
   💡 請讓用戶知道可以執行:
   /kkcoin_v2_setup #頻道名稱

⚠️ 注意:
   • 首次執行可能需要 30-60 秒來生成圖表
   • matplotlib 在 Server 上運行較慢
   • 自動更新功能需要額外實施代碼
""")
