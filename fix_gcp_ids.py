#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修復GCP上的gcp_fix_ids.py"""

import sys

# 修復第49行的f-string問題
file_path = '/home/e193752468/kkgroup/gcp_fix_ids.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到並修復有f-string問題的行
for i in range(len(lines)):
    if i == 48:  # Line 49
        # 原始: log(f'{'ID':>20} | {'昵稱':<30}')
        # 修復: log(f"{'ID':>20} | {'昵稱':<30}")
        lines[i] = 'log(f"{\'ID\':>20} | {\'昵稱\':<30}")\n'

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✓ gcp_fix_ids.py 已修復")

# 驗證語法
import subprocess
result = subprocess.run(['python3', '-m', 'py_compile', file_path], capture_output=True, text=True)
if result.returncode == 0:
    print("✓ 語法檢查通過")
else:
    print("✗ 還有語法錯誤:")
    print(result.stderr)
