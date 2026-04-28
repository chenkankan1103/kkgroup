# -*- coding: utf-8 -*-
"""
簡化診斷：直接檢查新用戶置物櫃 embed 是否有圖片
"""

import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from db_adapter import get_user

user_id = '1430046213012590592'
print(f"\n=== 診斷新用戶置物櫃圖片問題 ===\n")

# 1. 查詢用戶數據
user_data = get_user(int(user_id))
if not user_data:
    print(f"❌ 找不到用戶 {user_id}")
    sys.exit(1)

print(f"✅ 用戶已找到")
print(f"   Face: {user_data.get('face')} (type: {type(user_data.get('face')).__name__})")
print(f"   Hair: {user_data.get('hair')} (type: {type(user_data.get('hair')).__name__})")
print(f"   Skin: {user_data.get('skin')} (type: {type(user_data.get('skin')).__name__})")
print(f"   Top: {user_data.get('top')} (type: {type(user_data.get('top')).__name__})")
print(f"   Bottom: {user_data.get('bottom')} (type: {type(user_data.get('bottom')).__name__})")
print(f"   Shoes: {user_data.get('shoes')} (type: {type(user_data.get('shoes')).__name__})")
print(f"   Is_stunned: {user_data.get('is_stunned')} (type: {type(user_data.get('is_stunned')).__name__})")

# 2. 測試 build_api_url
from cogs.ui.utils import paperdoll_manager

try:
    url = paperdoll_manager.build_api_url(user_data)
    if url:
        print(f"\n✅ API URL 已生成")
        print(f"   長度: {len(url)}")
        print(f"   前 100 字: {url[:100]}...")
    else:
        print(f"\n❌ build_api_url 返回 None")
except Exception as e:
    print(f"\n❌ build_api_url 錯誤: {e}")
    import traceback
    traceback.print_exc()

# 3. 檢查 thread_id 和 locker_message_id
locker_msg_id = user_data.get('locker_message_id')
thread_id = user_data.get('thread_id')
print(f"\n置物櫃狀態：")
print(f"   locker_message_id: {locker_msg_id}")
print(f"   thread_id: {thread_id}")

if locker_msg_id and thread_id:
    print(f"   ✅ 置物櫃已建立")
else:
    print(f"   ❌ 置物櫃尚未完全建立")

print(f"\n=== 診斷完成 ===\n")
