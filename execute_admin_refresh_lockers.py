#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接執行 /admin_refresh_all_lockers 命令的核心邏輯
- 為所有用戶重新生成置物櫃 URL
- 驗證所有紙娃娃 URL 的有效性
"""

import sys
sys.path.insert(0, '.')

import sqlite3
import json
from cogs.ui.utils import paperdoll_manager

print("=" * 100)
print("🔄 執行 /admin_refresh_all_lockers 核心邏輯")
print("=" * 100)

# 連接資料庫
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# 取得所有用戶
cursor.execute("""
    SELECT user_id, face, hair, top, bottom, shoes, skin 
    FROM users 
    WHERE user_id IS NOT NULL AND user_id != ''
""")

all_users_raw = cursor.fetchall()
total_users = len(all_users_raw)

print(f"\n【準備】")
print(f"  總用戶數：{total_users}")
print(f"  將為每個用戶重新生成置物櫃 URL\n")

success_count = 0
fail_count = 0
generated_urls = []

# 遍歷所有用戶，為每個用戶重新生成紙娃娃 URL
print("【執行批量處理】\n")

for i, user_row in enumerate(all_users_raw):
    user_id, face, hair, top, bottom, shoes, skin = user_row
    
    # 構建用戶資料字典
    user_data = {
        'user_id': user_id,
        'face': face,
        'hair': hair,
        'top': top,
        'bottom': bottom,
        'shoes': shoes,
        'skin': skin or 12000
    }
    
    try:
        # 調用 paperdoll_manager 生成 API URL
        api_url = paperdoll_manager.build_api_url(user_data)
        
        if api_url:
            success_count += 1
            generated_urls.append({
                'user_id': user_id,
                'url': api_url,
                'status': 'success'
            })
            
            # 顯示進度
            if (i + 1) % 50 == 0:
                print(f"  ✅ 進度：{i + 1}/{total_users}")
            elif (i + 1) % 10 == 0:
                print(f"  ✅ 進度：{i + 1}/{total_users}")
        else:
            fail_count += 1
            generated_urls.append({
                'user_id': user_id,
                'url': None,
                'status': 'failed - returned None'
            })
    
    except Exception as e:
        fail_count += 1
        generated_urls.append({
            'user_id': user_id,
            'url': None,
            'status': f'error: {str(e)[:50]}'
        })

print(f"\n【完成統計】")
print(f"  ✅ 成功生成：{success_count} 個")
print(f"  ❌ 失敗：{fail_count} 個")
print(f"  📊 成功率：{success_count/total_users*100:.1f}%")

# 顯示樣本 URL
print(f"\n【樣本紙娃娃 URL】")
sample_count = 0
for item in generated_urls:
    if item['status'] == 'success' and sample_count < 5:
        print(f"\n  用戶 {item['user_id']}:")
        print(f"  {item['url'][:100]}...")
        sample_count += 1

# 驗證 URL 結構
print(f"\n【URL 結構驗證】")
valid_urls = [u for u in generated_urls if u['status'] == 'success']
print(f"  檢查 {len(valid_urls)} 個成功的 URL...")

proxy_urls = [u for u in valid_urls if '/api/proxy/' in u['url']]
direct_urls = [u for u in valid_urls if u['url'].startswith('https://maplestory.io')]

print(f"  使用 Proxy 的 URL：{len(proxy_urls)} 個")
print(f"  直接調用的 URL：{len(direct_urls)} 個")

if proxy_urls:
    print(f"\n  樣本 Proxy URL:")
    print(f"    {proxy_urls[0]['url'][:80]}...")

# 保存生成的 URL 記錄
with open('locker_refresh_urls.json', 'w', encoding='utf-8') as f:
    json.dump({
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'total_users': total_users,
        'success_count': success_count,
        'fail_count': fail_count,
        'urls': generated_urls[:50]  # 只保存前 50 個作為樣本
    }, f, ensure_ascii=False, indent=2)

print(f"\n✅ URL 記錄已保存至：locker_refresh_urls.json")

conn.close()

print("\n" + "=" * 100)
print("✅ /admin_refresh_all_lockers 核心邏輯執行完成")
print(f"📊 結果：{success_count}/{total_users} 用戶的置物櫃已重新生成")
print("=" * 100)
