# -*- coding: utf-8 -*-
"""
針對特定用戶更新置物櫃的快速修復腳本
用法: python3 refresh_user_locker.py <user_id> [force_recreate]
"""

import sqlite3
import sys
from pathlib import Path

# 添加根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent))

from cogs.ui.utils.paperdoll_manager import build_api_url, validate
from cogs.ui.utils.locker_cache import locker_cache


def get_user_data(user_id: str):
    """從數據庫獲取用戶數據"""
    db_path = Path(__file__).parent / "user_data.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_user_locker(user_id: str, force_recreate: bool = False):
    """更新指定用戶的置物櫃"""
    print(f"\n🔄 開始更新用戶 {user_id} 的置物櫃...\n")
    
    # 1. 獲取用戶數據
    user_data = get_user_data(user_id)
    if not user_data:
        print(f"❌ 找不到用戶 {user_id}")
        return False
    
    print(f"✅ 用戶已找到")
    print(f"   - 暈倒狀態: {'是' if user_data.get('is_stunned') else '否'}")
    print(f"   - 置物櫃 ID: {user_data.get('locker_message_id', 'N/A')}")
    print(f"   - 置物櫃線程: {user_data.get('thread_id', 'N/A')}")
    
    # 2. 驗證紙娃娃數據
    if not validate(user_data):
        print(f"❌ 用戶紙娃娃數據不完整")
        return False
    
    print(f"✅ 紙娃娃數據完整")
    
    # 3. 生成 API URL
    try:
        pose = 'stand1'
        url = build_api_url(user_data, pose=pose)
        print(f"✅ API URL 已生成")
        print(f"   - Pose: {pose}")
        if user_data.get('is_stunned') == 1:
            print(f"   ⚠️  自動轉換為 prone 姿勢（暈倒狀態）")
    except Exception as e:
        print(f"❌ 生成 API URL 失敗: {e}")
        return False
    
    # 4. 清除緩存
    try:
        # 計算該用戶的 paperdoll hash 並清除
        paperdoll_hash = locker_cache.build_paperdoll_hash(user_data)
        locker_cache.invalidate_hash(paperdoll_hash)
        print(f"✅ 紙娃娃緩存已清除 (hash: {paperdoll_hash[:16]}...)")
    except Exception as e:
        print(f"⚠️  緩存清除失敗 (非致命): {e}")
    
    # 5. 檢查置物櫃狀態
    locker_msg_id = user_data.get('locker_message_id')
    thread_id = user_data.get('thread_id')
    
    if not locker_msg_id or not thread_id:
        print(f"\n⚠️  置物櫃尚未建立")
        print(f"   使用者需要在 Discord 中：")
        print(f"   1. 打開置物櫃頻道")
        print(f"   2. 點擊「🔄 更新面板」按鈕")
        print(f"   系統會自動建立置物櫃並顯示紙娃娃")
    else:
        print(f"\n✅ 置物櫃已建立")
        print(f"   - 訊息 ID: {locker_msg_id}")
        print(f"   - 線程 ID: {thread_id}")
        print(f"   - 需要手動在 Discord 中按「🔄 更新面板」按鈕以刷新顯示")
    
    print(f"\n✅ 更新完成！")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 refresh_user_locker.py <user_id> [force_recreate]")
        print("範例: python3 refresh_user_locker.py 1430046213012590592")
        sys.exit(1)
    
    user_id = sys.argv[1]
    force_recreate = len(sys.argv) > 2 and sys.argv[2].lower() in ('true', '1', 'yes')
    
    success = update_user_locker(user_id, force_recreate)
    sys.exit(0 if success else 1)
