#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
為 episode_statistics 表添加測試數據，確保 anime_ranking 命令能顯示多線圖
"""
import sqlite3
import os
from pathlib import Path

# 使用與 anime_tracker.py 相同的數據庫路徑
DB_PATH = Path(__file__).resolve().parent / "uibot_anime.db"

EPISODE_STATS_TABLE = "episode_statistics"

def add_test_data():
    """添加測試數據"""
    if not DB_PATH.exists():
        print(f"❌ 數據庫不存在: {DB_PATH}")
        print(f"   將嘗試創建...")
    
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            
            # 確保表存在
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {EPISODE_STATS_TABLE} (
                    videoSn INTEGER PRIMARY KEY,
                    animeSn INTEGER NOT NULL,
                    episode_num TEXT,
                    views INTEGER,
                    score REAL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 檢查現有數據
            cursor.execute(f"SELECT COUNT(*) FROM {EPISODE_STATS_TABLE}")
            count = cursor.fetchone()[0]
            
            if count > 0:
                print(f"✅ 表中已有 {count} 條數據")
                return True
            
            # 添加測試數據 - 3 部動畫，每部 3-5 集
            test_data = [
                # 動畫 1 (animeSn=1)
                (1001, 1, "EP1", 100),
                (1002, 1, "EP2", 150),
                (1003, 1, "EP3", 200),
                (1004, 1, "EP4", 250),
                # 動畫 2 (animeSn=2)
                (2001, 2, "EP1", 80),
                (2002, 2, "EP2", 120),
                (2003, 2, "EP3", 160),
                # 動畫 3 (animeSn=3)
                (3001, 3, "EP1", 90),
                (3002, 3, "EP2", 135),
                (3003, 3, "EP3", 180),
                (3004, 3, "EP4", 225),
                (3005, 3, "EP5", 270),
            ]
            
            cursor.executemany(f"""
                INSERT OR IGNORE INTO {EPISODE_STATS_TABLE} 
                (videoSn, animeSn, episode_num, views) 
                VALUES (?, ?, ?, ?)
            """, test_data)
            
            conn.commit()
            
            cursor.execute(f"SELECT COUNT(*) FROM {EPISODE_STATS_TABLE}")
            new_count = cursor.fetchone()[0]
            
            print(f"✅ 添加了 {new_count - count} 條測試數據")
            print(f"   現在共有 {new_count} 條數據")
            return True
            
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

if __name__ == "__main__":
    print("🔨 為 episode_statistics 表添加測試數據...")
    add_test_data()
