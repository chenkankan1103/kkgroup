#!/usr/bin/env python3
import re

# 读取文件
with open('status_dashboard.py', 'r') as f:
    content = f.read()

# 修复callback访问问题
content = re.sub(r'if item\.callback\.__name__ == ([^:]+):', r'if getattr(item.callback, "__name__", None) == \1:', content)

# 写入文件
with open('status_dashboard.py', 'w') as f:
    f.write(content)

print('修复完成')