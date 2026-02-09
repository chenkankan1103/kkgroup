#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自動修復Python文件中的未閉合字符串"""

import re
import sys

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 修復所有未閉合的字符串（簡單版本）
    # Pattern: 找到以引號開始但跨越行邊界的字符串
    lines = content.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        # 移除行尾的換行符
        line = line.rstrip('\n')
        
        # 如果改行以字符串結尾但沒有閉合引號
        if line.rstrip().endswith(',') and '"' in line and line.count('"') % 2 == 1:
            # 添加結尾引號（在逗號前）
            line = line.rstrip() 
            if line.endswith(','):
                line = line[:-1] + '",'
            else:
                line = line + '"'
        
        fixed_lines.append(line)
    
    new_content = '\n'.join(fixed_lines)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✓ 已修復 {filepath}")
    
    # 驗證
    try:
        compile(new_content, filepath, 'exec')
        print(f"✓ 語法檢查通過")
        return True
    except SyntaxError as e:
        print(f"✗ 還有語法錯誤: {e.msg} (line {e.lineno})")
        return False

if __name__ == '__main__':
    if len(sys.argv) > 1:
        for f in sys.argv[1:]:
            fix_file(f)
    else:
        print("使用: python fix_file.py file1.py [file2.py ...]")
