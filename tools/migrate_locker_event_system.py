"""
DB Migration: Add locker event-driven system columns
新增置物櫃事件驅動系統所需的欄位
"""
import sqlite3
import os
from pathlib import Path


def migrate_locker_event_columns():
    """
    新增欄位：
    - embed_version: embed 版本號，用於檢測是否需要更新
    - paperdoll_hash: 紙娃娃配置 hash，用於快取判斷
    - last_embed_update: 最後一次 embed 更新時間戳
    - last_image_fetch: 最後一次 API 圖片請求時間戳
    - cached_paperdoll_url: 快取的紙娃娃圖片 URL
    """
    db_path = './user_data.db'
    
    if not os.path.exists(db_path):
        print(f"❌ 找不到 DB: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 檢查欄位是否已存在
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        new_columns = [
            ('embed_version', 'INTEGER DEFAULT 1'),
            ('paperdoll_hash', 'TEXT DEFAULT NULL'),
            ('last_embed_update', 'INTEGER DEFAULT 0'),
            ('last_image_fetch', 'INTEGER DEFAULT 0'),
            ('cached_paperdoll_url', 'TEXT DEFAULT NULL'),
        ]
        
        for col_name, col_def in new_columns:
            if col_name not in columns:
                print(f"✏️  新增欄位: {col_name}")
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            else:
                print(f"⏭️  欄位已存在: {col_name}")
        
        conn.commit()
        conn.close()
        
        print("✅ DB migration 已完成")
        return True
    
    except Exception as e:
        print(f"❌ Migration 失敗: {e}")
        return False


if __name__ == '__main__':
    migrate_locker_event_columns()
