#!/usr/bin/env python3
"""檢查數據庫中的 thread_id 情況"""

from db_adapter import get_all_users
import json

all_users = get_all_users()

print(f"📊 總用戶數：{len(all_users)}\n")

thread_ids = []
no_thread = 0

for user_data in all_users:
    user_id = user_data.get('user_id')
    thread_id = user_data.get('thread_id', 0)
    username = user_data.get('username', 'Unknown')
    
    if thread_id and thread_id > 0:
        thread_ids.append((user_id, thread_id, username))
        print(f"✅ {username} (ID: {user_id}) -> thread_id: {thread_id}")
    else:
        no_thread += 1

print(f"\n{'='*50}")
print(f"✅ 有 thread_id 的用戶：{len(thread_ids)}")
print(f"❌ 沒有 thread_id 的用戶：{no_thread}")
print(f"{'='*50}")

# 如果有 thread_id，顯示清理指令
if thread_ids:
    print(f"\n🎯 找到 {len(thread_ids)} 個線程，可以進行清理")
    print("\n線程 ID 列表：")
    for user_id, thread_id, username in thread_ids:
        print(f"  - {thread_id} ({username})")
else:
    print("\n⚠️ 沒有找到任何 thread_id")
    print("可能需要先運行置物櫃初始化來創建線程")
