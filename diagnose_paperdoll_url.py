# -*- coding: utf-8 -*-
"""
診斷紙娃娃 API URL 是否可以訪問
檢查：
1. URL 是否有效
2. API 是否能返回圖片
3. Discord embed 是否能加載該圖片
"""

import sqlite3
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cogs.ui.utils.paperdoll_manager import build_api_url, validate


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
    
    # 3. 生成 URL（stand1）
    print(f"\n📍 測試 stand1 姿勢：")
    url_stand1 = build_api_url(user_data, pose='stand1')
    if url_stand1:
        print(f"   URL: {url_stand1[:120]}...")
    else:
        print(f"❌ 無法生成 URL")
        return False
    
    # 4. 生成 URL（prone - 暈倒）
    print(f"\n📍 測試 prone 姿勢（暈倒）：")
    url_prone = build_api_url(user_data, pose='prone')
    if url_prone:
        print(f"   URL: {url_prone[:120]}...")
    else:
        print(f"❌ 無法生成 prone URL")
        return False
    
    # 5. 測試 API 連接
    print(f"\n🌐 測試 API 連接...")
    for pose_name, url in [("stand1", url_stand1), ("prone", url_prone)]:
        try:
            print(f"\n   【{pose_name}】")
            response = requests.head(url, timeout=10, allow_redirects=True)
            
            if response.status_code == 200:
                print(f"   ✅ API 連接成功 (HTTP {response.status_code})")
                print(f"      Content-Type: {response.headers.get('Content-Type', 'N/A')}")
                print(f"      Content-Length: {response.headers.get('Content-Length', 'N/A')}")
            else:
                print(f"   ⚠️  API 返回 HTTP {response.status_code}")
                if response.status_code == 404:
                    print(f"      ❌ 圖片不存在 (404)")
                elif response.status_code >= 500:
                    print(f"      ⚠️  伺服器錯誤")
        except requests.Timeout:
            print(f"   ❌ 超時 - API 無反應")
        except requests.RequestException as e:
            print(f"   ❌ 連接失敗: {e}")
    
    # 6. 檢查是否被 Discord 支持
    print(f"\n📦 Discord Embed 支持檢查：")
    if "maplestory.io" in url_stand1.lower():
        print(f"   ✅ URL 來自 maplestory.io （Discord 應支持）")
    else:
        print(f"   ⚠️  URL 不來自 maplestory.io")
    
    # 7. 用戶狀態檢查
    print(f"\n👤 用戶狀態：")
    print(f"   - Face: {user_data.get('face')}")
    print(f"   - Hair: {user_data.get('hair')}")
    print(f"   - Skin: {user_data.get('skin')}")
    print(f"   - 暈倒: {'是' if user_data.get('is_stunned') == 1 else '否'}")
    print(f"   - 性別: {user_data.get('gender')}")
    
    print(f"\n✅ 診斷完成！")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 diagnose_paperdoll_url.py <user_id>")
        sys.exit(1)
    
    user_id = sys.argv[1]
    success = diagnose_paperdoll_url(user_id)
    sys.exit(0 if success else 1)
