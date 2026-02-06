#!/usr/bin/env python3
"""生成事件系統替換指令"""

import re

# 讀取文件
with open('uicommands/ScamParkEvents.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找所有的事件方法和 thread.send() 調用
# 模式：方法名 -> thread.send(embed=embed) 後面跟著 save_event_time 和其他操作

pattern = r'async def (event_\w+)\(self,.*?\):\s*"""([^"]*?)"""'
methods = re.findall(pattern, content)

print(f"找到 {len(methods)} 個事件方法:")
for method_name, description in methods:
    # 簡化描述
    desc = description.split('\n')[0] if description else "未知"
    print(f"  - {method_name}: {desc}")

# 現在查找所有的 thread.send(embed=embed) 調用
send_pattern = r'message = await thread\.send\(embed=embed\)'
sends = re.findall(send_pattern, content)
print(f"\n找到 {len(sends)} 個 thread.send(embed=embed) 調用")

# 生成替換清單
print("\n生成替換清單...")

# 查找每個事件後的 save_event_time 調用
replacements = []

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'async def event_' in line:
        # 提取方法名
        match = re.search(r'async def (event_\w+)\(', line)
        if match:
            method_name = match.group(1)
            # 查找這個方法中的 send 調用
            for j in range(i, min(i + 100, len(lines))):
                if 'message = await thread.send(embed=embed)' in lines[j]:
                    # 檢查下一行是否有 save_event_time
                    if j + 1 < len(lines) and 'self.save_event_time' in lines[j + 1]:
                        # 提取 save_event_time 行
                        save_line = lines[j + 1].strip()
                        # 提取事件類型
                        event_type_match = re.search(r'"([^"]+)".*?$', save_line)
                        if event_type_match:
                            event_type = event_type_match.group(1)
                            print(f"  方法: {method_name}, 事件類型: {event_type}")
                            replacements.append((method_name, event_type))
                        else:
                            print(f"  方法: {method_name}, 未能提取事件類型")
                    break

print(f"\n共 {len(replacements)} 個替換")
