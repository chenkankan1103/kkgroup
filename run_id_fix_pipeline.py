#!/usr/bin/env python3
"""
Discord ID 完整修正流程

執行順序：
1. diagnose_user_ids.py - 診斷ID問題
2. fix_user_ids.py - 自動修正问题
"""

import subprocess
import sys
import os

def run_script(script_name):
    """執行Python腳本"""
    print(f"\n{'=' * 80}")
    print(f"📌 執行: {script_name}")
    print(f"{'=' * 80}\n")
    
    try:
        result = subprocess.run([sys.executable, script_name], cwd=os.getcwd())
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        return False

def main():
    print("""
╔════════════════════════════════════════════════════════════════════════════════╗
║                    Discord ID 完整修正流程                                      ║
║                                                                                ║
║  此流程會執行以下步驟：                                                         ║
║  1. diagnose_user_ids.py - 掃描並診斷所有ID問題                               ║
║  2. fix_user_ids.py - 自動修正檢測到的所有問題                                 ║
║                                                                                ║
║  預期操作：                                                                     ║
║  - 修正可疑ID配對 (±500 範圍內)                                                ║
║  - 補充缺失的昵稱                                                              ║
║  - 刪除測試ID                                                                 ║
║  - 新增缺失的Discord成員                                                      ║
║                                                                                ║
║  ⚠️ 警告：此程序將修改資料庫，請確保已備份！                                   ║
╚════════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # 確認開始
    response = input("\n✋ 確認開始修正流程？(yes/no): ").strip().lower()
    if response != 'yes':
        print("❌ 已取消")
        return
    
    # 步驟1：診斷
    if not run_script('diagnose_user_ids.py'):
        print("❌ 診斷失敗，中止")
        return
    
    # 步驟2：修正
    response = input("\n✋ 確認執行修正？(yes/no): ").strip().lower()
    if response != 'yes':
        print("❌ 已取消修正")
        return
    
    if not run_script('fix_user_ids.py'):
        print("❌ 修正失敗")
        return
    
    print("\n" + "=" * 80)
    print("✅ 完整修正流程已完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
