#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""診斷新用戶的紙娃娃數據"""

import sqlite3
from cogs.ui.utils.paperdoll_manager import build_api_url, validate

user_id = "1430046213012590592"

try:
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    
    # 查詢用戶
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"❌ 用戶 {user_id} 不存在於數據庫中")
        conn.close()
        exit(1)
    
    # 取得欄位名
    columns = [desc[0] for desc in cursor.description]
    user_data = dict(zip(columns, result))
    
    print(f"✅ 找到用戶 {user_id}\n")
    
    # 顯示紙娃娃相關欄位
    paperdoll_fields = ['face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'gender', 'is_stunned']
    print("📋 紙娃娃數據：")
    for field in paperdoll_fields:
        value = user_data.get(field, "❌ 缺失")
        print(f"  {field}: {value}")
    
    # 驗證數據完整性
    print(f"\n🔍 數據完整性檢查：")
    is_valid = validate(user_data)
    print(f"  有效: {is_valid}")
    
    # 嘗試生成 URL
    print(f"\n🌐 API URL 生成：")
    try:
        url = build_api_url(user_data)
        if url:
            print(f"  ✅ URL 生成成功")
            print(f"  URL: {url[:80]}...")
        else:
            print(f"  ❌ URL 生成失敗（返回 None）")
    except Exception as e:
        print(f"  ❌ URL 生成出錯: {e}")
    
    conn.close()
    
except Exception as e:
    import traceback
    print(f"❌ 診斷失敗: {e}")
    traceback.print_exc()
