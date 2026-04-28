# -*- coding: utf-8 -*-
"""
簡化版診斷 - 只使用標準庫，無需 requests
"""

import sqlite3
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cogs.ui.utils.paperdoll_manager import build_api_url, validate


def test_url(url: str) -> bool:
    """測試 URL 是否可訪問"""
    try:
        # 加上 User-Agent 防止被阻擋
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            if status == 200:
                content_type = response.headers.get('Content-Type', 'N/A')
                print(f"   ✅ 成功 (HTTP {status})")
                print(f"      Content-Type: {content_type}")
                return True
            else:
                print(f"   ⚠️  HTTP {status}")
                return False
    except urllib.error.HTTPError as e:
        print(f"   ❌ HTTP {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"   ❌ URL 錯誤: {e.reason}")
        return False
    except Exception as e:
        print(f"   ❌ 錯誤: {e}")
        return False


def diagnose_paperdoll_url(user_id: str):
    """診斷用戶的紙娃娃 URL"""
    print(f"\n🔍 診斷用戶 {user_id} 的紙娃娃 URL...\n")
    
    # 1. 從資料庫取得用戶數據
    db_path = Path(__file__).parent / "user_data.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        user_data = dict(row) if row else None
    finally:
        conn.close()
    
    if not user_data:
        print(f"❌ 找不到用戶 {user_id}")
        return False
    
    print(f"✅ 用戶已找到")
    
    # 2. 驗證數據
    if not validate(user_data):
        print(f"❌ 紙娃娃數據不完整")
        return False
    
    print(f"✅ 紙娃娃數據完整")
    
    # 3. 生成 URL
    print(f"\n📍 生成 API URL：")
    url = build_api_url(user_data, pose='stand1')
    if url:
        print(f"✅ URL 已生成")
        print(f"   長度: {len(url)} 字元")
        print(f"   前 150 字: {url[:150]}...")
    else:
        print(f"❌ 無法生成 URL")
        return False
    
    # 4. 測試 URL 可訪問性
    print(f"\n🌐 測試 URL 可訪問性...")
    test_url(url)
    
    # 5. 檢查 URL 格式
    print(f"\n📋 URL 格式檢查:")
    if "maplestory.io" in url:
        print(f"   ✅ 來源正確 (maplestory.io)")
    else:
        print(f"   ❌ 來源不正確")
    
    if "/animated" in url:
        print(f"   ✅ 格式正確 (animated)")
    else:
        print(f"   ❌ 格式錯誤")
    
    # 6. 用戶狀態
    print(f"\n👤 用戶配置:")
    print(f"   - Face: {user_data.get('face')}")
    print(f"   - Hair: {user_data.get('hair')}")
    print(f"   - Skin: {user_data.get('skin')}")
    print(f"   - Top: {user_data.get('top')}")
    print(f"   - Bottom: {user_data.get('bottom')}")
    print(f"   - Shoes: {user_data.get('shoes')}")
    print(f"   - 暈倒: {'是' if user_data.get('is_stunned') == 1 else '否'}")
    
    print(f"\n✅ 診斷完成！")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 diagnose_paperdoll_url.py <user_id>")
        sys.exit(1)
    
    user_id = sys.argv[1]
    success = diagnose_paperdoll_url(user_id)
    sys.exit(0 if success else 1)
