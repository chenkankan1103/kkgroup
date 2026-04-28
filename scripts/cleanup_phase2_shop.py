#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二階段：刪除 SHOP 模組的過時指令 (5個)
"""

import re
import sys
from pathlib import Path

def find_command_bounds(content, command_name):
    """找到指令的完整邊界"""
    lines = content.split('\n')
    
    decorator_idx = None
    for i, line in enumerate(lines):
        if f'@app_commands.command(name="{command_name}"' in line or \
           f"@app_commands.command(name='{command_name}'" in line:
            decorator_idx = i
            break
    
    if decorator_idx is None:
        return None
    
    func_def_idx = None
    for i in range(decorator_idx, min(decorator_idx + 50, len(lines))):
        if re.match(r'\s*(async\s+)?def\s+\w+\s*\(', lines[i]):
            func_def_idx = i
            break
    
    if func_def_idx is None:
        return None
    
    func_indent = len(lines[func_def_idx]) - len(lines[func_def_idx].lstrip())
    
    func_end_idx = None
    for i in range(func_def_idx + 1, len(lines)):
        line = lines[i]
        
        if not line.strip():
            continue
        
        line_indent = len(line) - len(line.lstrip())
        
        if line.strip() and line_indent <= func_indent:
            func_end_idx = i
            break
    
    if func_end_idx is None:
        func_end_idx = len(lines)
    
    start_idx = decorator_idx
    while start_idx > 0:
        prev_line = lines[start_idx - 1]
        if not prev_line.strip() or prev_line.strip().startswith('@'):
            start_idx -= 1
        else:
            break
    
    return (start_idx, func_end_idx)

def delete_command(filepath, command_name):
    """從文件中刪除指令"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        bounds = find_command_bounds(content, command_name)
        if bounds is None:
            return False, "找不到"
        
        start_idx, end_idx = bounds
        lines = content.split('\n')
        
        new_lines = lines[:start_idx] + lines[end_idx:]
        new_content = '\n'.join(new_lines)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True, "已刪除"
    
    except Exception as e:
        return False, str(e)

def verify_python_syntax(filepath):
    """驗證 Python 文件語法"""
    try:
        import py_compile
        py_compile.compile(filepath, doraise=True)
        return True
    except:
        return False

# SHOP 模組清理清單
SHOP_COMMANDS = {
    "cogs/shop/shop.py": ["paperdoll"],
    "cogs/shop/feedback_cog.py": ["feedback"],
    "cogs/shop/enhanced_role_manager.py": ["grant_temporary_role", "check_my_roles"],
    "cogs/shop/merchant/role_expiry_manager.py": ["check_my_roles"],
}

print("=" * 70)
print("開始刪除 SHOP 模組的過時指令 (5個)")
print("=" * 70)

total = 0
success = 0
failed = 0
files_ok = 0
files_bad = 0

for filepath, commands in SHOP_COMMANDS.items():
    print(f"\n📄 {filepath}")
    
    filepath_ok = True
    for cmd in commands:
        total += 1
        ok, msg = delete_command(filepath, cmd)
        
        if ok:
            print(f"   ✅ {cmd}")
            success += 1
        else:
            print(f"   ❌ {cmd} - {msg}")
            failed += 1
    
    # 驗證語法
    if verify_python_syntax(filepath):
        print(f"   ✨ 語法檢查通過")
        files_ok += 1
    else:
        print(f"   ⚠️  語法檢查失敗！")
        filepath_ok = False
        files_bad += 1

print("\n" + "=" * 70)
print("SHOP 模組清理結果")
print("=" * 70)
print(f"總處理: {total} 個指令")
print(f"  ✅ 成功: {success}")
print(f"  ❌ 失敗: {failed}")
print(f"  ✨ 文件語法檢查: {files_ok} 通過, {files_bad} 失敗")
