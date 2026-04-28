#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord 指令自動刪除工具 v2
更穩健的版本，支持複雜的多行指令定義
"""

import re
import os
from pathlib import Path

def find_command_bounds(content, command_name):
    """
    找到指令的完整邊界（decorator + async def + 函數體）
    返回 (start_idx, end_idx) 或 None
    """
    lines = content.split('\n')
    
    # 1. 找 @app_commands.command 裝飾器
    decorator_idx = None
    for i, line in enumerate(lines):
        if f'@app_commands.command(name="{command_name}"' in line or \
           f"@app_commands.command(name='{command_name}'" in line:
            decorator_idx = i
            break
    
    if decorator_idx is None:
        return None
    
    # 2. 找函數定義所在行
    func_def_idx = None
    for i in range(decorator_idx, min(decorator_idx + 50, len(lines))):
        if re.match(r'\s*(async\s+)?def\s+\w+\s*\(', lines[i]):
            func_def_idx = i
            break
    
    if func_def_idx is None:
        return None
    
    # 3. 計算縮進深度
    func_indent = len(lines[func_def_idx]) - len(lines[func_def_idx].lstrip())
    
    # 4. 找函數結束（下一個同級或更低級的定義）
    func_end_idx = None
    for i in range(func_def_idx + 1, len(lines)):
        line = lines[i]
        
        # 跳過空行
        if not line.strip():
            continue
        
        # 計算這行的縮進
        line_indent = len(line) - len(line.lstrip())
        
        # 如果縮進相同或更小且有內容，就是下一個頂級定義
        if line.strip() and line_indent <= func_indent:
            func_end_idx = i
            break
    
    if func_end_idx is None:
        func_end_idx = len(lines)
    
    # 5. 向前找起點（包含前面的空行和可能的其他裝飾器）
    start_idx = decorator_idx
    while start_idx > 0:
        prev_line = lines[start_idx - 1]
        # 跳過空行或其他 @app_commands 裝飾器
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
            print(f"❌ 找不到指令: {command_name} in {filepath}")
            return False
        
        start_idx, end_idx = bounds
        lines = content.split('\n')
        
        # 計算實際行號（給用戶看）
        actual_start_line = sum(1 for line in lines[:start_idx])
        actual_end_line = sum(1 for line in lines[:end_idx])
        
        # 刪除
        new_lines = lines[:start_idx] + lines[end_idx:]
        new_content = '\n'.join(new_lines)
        
        # 寫回
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✅ 已刪除 '{command_name}' (行 {actual_start_line}-{actual_end_line})")
        return True
    
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

def verify_python_syntax(filepath):
    """驗證 Python 文件語法"""
    try:
        import py_compile
        py_compile.compile(filepath, doraise=True)
        print(f"✅ 語法正確: {filepath}")
        return True
    except Exception as e:
        print(f"❌ 語法錯誤: {e}")
        return False

# COMMON 模組 - 第 1 批
print("=" * 60)
print("第 1 批: COMMON 模組 - kcoin.py")
print("=" * 60)

kcoin_file = "cogs/common/kcoin.py"
kcoin_commands = ["kkcoin", "kkcoin_rank", "reserve_status"]

for cmd in kcoin_commands:
    delete_command(kcoin_file, cmd)

# 驗證語法
if verify_python_syntax(kcoin_file):
    print("\n✨ kcoin.py 清理成功！\n")
else:
    print("\n⚠️  kcoin.py 有語法錯誤，請檢查！\n")
