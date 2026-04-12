#!/usr/bin/env python3
import sqlite3
import sys

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # 先檢查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='episode_statistics'")
        exists = cursor.fetchone()
        
        if exists:
            print("✅ episode_statistics 表已存在")
            
            # 檢查表中有多少記錄
            cursor.execute("SELECT COUNT(*) FROM episode_statistics")
            count = cursor.fetchone()[0]
            print(f"📊 表中有 {count} 筆記錄")
            
            # 檢查有多少部動畫有集數數據
            cursor.execute("SELECT COUNT(DISTINCT animeSn) FROM episode_statistics")
            anime_count = cursor.fetchone()[0]
            print(f"🎬 有 {anime_count} 部動畫的集數數據")
            
            # 列出前 5 部
            if anime_count > 0:
                cursor.execute("""
                    SELECT animeSn, COUNT(*) as ep_count, SUM(views) as total_views 
                    FROM episode_statistics 
                    GROUP BY animeSn 
                    ORDER BY total_views DESC 
                    LIMIT 5
                """)
                print("\n前 5 部動畫:")
                for row in cursor.fetchall():
                    print(f"  animeSn={row[0]}: {row[1]} 集, {row[2] or 0} 次觀看")
        else:
            print("❌ episode_statistics 表不存在")
            print("✅ 但代碼現在會在使用時自動創建它")
            
except Exception as e:
    print(f"❌ 錯誤: {e}")
    sys.exit(1)
