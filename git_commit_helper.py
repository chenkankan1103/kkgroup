#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git commit helper script - 提交修改並推送到 GitHub
"""

import subprocess
import os

def run_cmd(cmd):
    """執行命令並返回輸出"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=r'c:\Users\88697\Desktop\kkgroup')
    return result.returncode, result.stdout, result.stderr

def main():
    print("=" * 70)
    print("🔧 Git 提交助手 - 修復 COMMANDS_DIR 配置")
    print("=" * 70)
    
    # 檢查狀態
    print("\n📋 檢查 Git 狀態...")
    rc, out, err = run_cmd("git status")
    print(f"Git status output:\n{out}")
    
    # 添加文件
    print("\n📝 添加修改的文件...")
    files_to_add = [
        "bots/bot.py",
        "bots/shopbot.py", 
        "bots/uibot.py",
        "fix_commands_dir.py"
    ]
    
    for f in files_to_add:
        rc, out, err = run_cmd(f"git add {f}")
        if rc == 0:
            print(f"✅ {f} 已添加")
        else:
            print(f"❌ {f} 添加失敗: {err}")
    
    # 檢查 staged 文件
    print("\n📦 檢查 staged 文件...")
    rc, out, err = run_cmd("git diff --cached --name-only")
    print(f"Staged files:\n{out}")
    
    # 提交
    print("\n💾 提交修改...")
    commit_msg = "fix: Update COMMANDS_DIR to cogs structure paths (cogs/common, cogs/shop, cogs/ui)"
    rc, out, err = run_cmd(f'git commit -m "{commit_msg}"')
    if rc == 0:
        print(f"✅ 提交成功: {commit_msg}")
        print(f"Output: {out}")
    else:
        print(f"❌ 提交失敗: {err}")
        return
    
    # 查看新的 HEAD
    print("\n🔍 檢查新 commit...")
    rc, out, err = run_cmd("git log --oneline -3")
    print(f"Latest commits:\n{out}")
    
    # 推送
    print("\n🚀 推送到 GitHub...")
    rc, out, err = run_cmd("git push origin restructure-project-20260414")
    if rc == 0:
        print(f"✅ 推送成功!")
        print(f"Output: {out}")
    else:
        print(f"❌ 推送失敗: {err}")
        return
    
    print("\n" + "=" * 70)
    print("✅ 所有操作完成！代碼已上傳到 GitHub")
    print("=" * 70)

if __name__ == '__main__':
    main()
