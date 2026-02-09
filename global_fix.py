#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局修復所有Python文件的語法錯誤"""

import os
import subprocess
import re

def scan_and_fix_all_python_files(root_dir='.', exclude_dirs=['venv', '__pycache__', '.git']):
    """掃描並修復所有Python文件"""
    
    fixed_files = []
    error_files = []
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 排除特定目錄
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = os.path.join(dirpath, filename)
                
                # 嘗試編譯
                result = subprocess.run(
                    ['python3', '-m', 'py_compile', filepath],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode != 0 and 'SyntaxError' in result.stderr:
                    print(f"修復中: {filepath}")
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # 嘗試簡單修復：
                        # 1. 修復未閉合的docstring
                        content = re.sub(r'"""([^"]{10,})$', r'"""\1"""', content, flags=re.MULTILINE)
                        
                        # 2. 修復行尾的未閉合引號
                        lines = content.split('\n')
                        for i in range(len(lines)):
                            line = lines[i]
                            # 如果有奇數個引號且以, 或 ) 結尾，可能是未閉合的
                            if line.count('"') % 2 == 1 and (line.rstrip().endswith(',') or line.rstrip().endswith(')')):
                                # 在結尾前插入引號
                                if line.rstrip().endswith(','):
                                    lines[i] = line.rstrip()[:-1] + '",'
                                elif line.rstrip().endswith(')'):
                                    lines[i] = line.rstrip()[:-1] + '")'
                        
                        content = '\n'.join(lines)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        # 再次驗證
                        result = subprocess.run(
                            ['python3', '-m', 'py_compile', filepath],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        
                        if result.returncode == 0:
                            print(f"  ✓ 已修復")
                            fixed_files.append(filepath)
                        else:
                            print(f"  ⚠ 部分修復")
                            error_files.append((filepath, result.stderr.split('\n')[0]))
                    
                    except Exception as e:
                        print(f"  ✗ 修復失敗: {e}")
                        error_files.append((filepath, str(e)))

    print(f"\n=== 修復完成 ===")
    print(f"✓ 已修復: {len(fixed_files)} 個文件")
    print(f"✗ 失敗或部分修復: {len(error_files)} 個文件")
    
    if error_files:
        print(f"\n失敗的文件:")
        for f, e in error_files[:10]:
            print(f"  - {f}")

if __name__ == '__main__':
    import sys
    target_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    scan_and_fix_all_python_files(target_dir)
