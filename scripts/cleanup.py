#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡單的 Discord 指令清理器
直接刪除指令函數
"""

import re
import sys

def remove_command_from_file(filepath, command_name):
    """從文件中移除指令"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 找指令定義
    decorator_line = None
    for i, line in enumerate(lines):
        if f'@app_commands.command(name="{command_name}"' in line or f"@app_commands.command(name='{command_name}'" in line:
            decorator_line = i
            break
    
    if decorator_line is None:
        print(f"❌ 找不到指令: {command_name}")
        return False
    
    # 找函數定義
    func_start = None
    for i in range(decorator_line, min(decorator_line + 20, len(lines))):
        if lines[i].strip().startswith('async def ') or lines[i].strip().startswith('def '):
            func_start = i
            break
    
    if func_start is None:
        print(f"❌ 找不到函數定義: {command_name}")
        return False
    
    # 找函數結束
    base_indent = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = None
    
    for i in range(func_start + 1, len(lines)):
        line = lines[i]
        
        if not line.strip():
            continue
        
        indent = len(line) - len(line.lstrip())
        
        if line.strip() and indent <= base_indent:
            func_end = i
            break
    
    if func_end is None:
        func_end = len(lines)
    
    # 刪除空行（decorator 前面可能有空行）
    start = decorator_line
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    
    # 刪除指令
    del lines[start:func_end]
    
    # 寫回
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ 已刪除: {command_name} (行 {decorator_line+1}-{func_end})")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python cleanup.py <文件路徑> <指令名>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    command = sys.argv[2]
    
    remove_command_from_file(filepath, command)
