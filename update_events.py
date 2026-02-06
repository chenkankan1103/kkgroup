#!/usr/bin/env python3
"""自動化替換事件系統中的 thread.send() 為新的輔助函數"""

import re

# 讀取文件
with open('uicommands/ScamParkEvents.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替換模式：
# 原來：
#     message = await thread.send(embed=embed)
#     self.event_messages[member.id] = message.id
#     self.save_event_time(member.id, message.id, "事件名")
#
# 改為：
#     message = await self.send_or_edit_event_message(thread, embed, member.id, "事件名")

replacements = [
    # 大額沒收
    (r'(async def event_major_confiscation.*?)(        message = await thread\.send\(embed=embed\)\n        self\.event_messages\[member\.id\] = message\.id\n        self\.save_event_time\(member\.id, message\.id, "大額沒收"\))',
     r'\1        message = await self.send_or_edit_event_message(thread, embed, member.id, "大額沒收")'),
    
    # 保護費
    (r'(async def event_protection_fee.*?)(        message = await thread\.send\(embed=embed\)\n        self\.event_messages\[member\.id\] = message\.id\n        self\.save_event_time\(member\.id, message\.id, "保護費"\))',
     r'\1        message = await self.send_or_edit_event_message(thread, embed, member.id, "保護費")'),
    
    # 毆打
    (r'(async def event_beating.*?)(        message = await thread\.send\(embed=embed\)\n        self\.event_messages\[member\.id\] = message\.id\n        self\.save_event_time\(member\.id, message\.id, "毆打"\))',
     r'\1        message = await self.send_or_edit_event_message(thread, embed, member.id, "毆打")'),
]

# 使用更靈活的方法：逐行掃描並替換
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # 檢查是否是 thread.send(embed=embed) 調用
    if 'message = await thread.send(embed=embed)' in line:
        # 檢查下面的行是否有 self.event_messages 和 self.save_event_time
        if (i + 2 < len(lines) and 
            'self.event_messages[member.id] = message.id' in lines[i + 1] and
            'self.save_event_time(member.id, message.id,' in lines[i + 2]):
            
            # 提取事件名稱
            save_line = lines[i + 2]
            match = re.search(r'self\.save_event_time\(member\.id, message\.id, "([^"]+)"\)', save_line)
            if match:
                event_type = match.group(1)
                # 替換為新的輔助函數呼叫
                indent = len(line) - len(line.lstrip())
                new_line = ' ' * indent + f'message = await self.send_or_edit_event_message(thread, embed, member.id, "{event_type}")'
                new_lines.append(new_line)
                i += 3  # 跳過三行
                continue
    
    new_lines.append(line)
    i += 1

# 寫入修改後的內容
with open('uicommands/ScamParkEvents.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print("✅ 事件系統已更新！")
print("替換了所有 thread.send(embed=embed) 調用為 send_or_edit_event_message()")
