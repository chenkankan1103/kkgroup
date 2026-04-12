#!/usr/bin/env python3
import sqlite3

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # 檢查 episode_statistics 表是否存在以及有多少筆數據
        cursor.execute("""
            SELECT animeSn, COUNT(*) as ep_count, SUM(views) as total_views 
            FROM episode_statistics 
            GROUP BY animeSn 
            ORDER BY total_views DESC 
            LIMIT 15
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ episode_statistics 表可能為空或不存在")
        else:
            print("✅ episode_statistics 表數據:")
            print("animeSn | ep_count | total_views")
            print("-" * 40)
            for row in rows:
                print(f"{row[0]:7} | {row[1]:8} | {row[2] or 0}")
            
            # 再檢查有 >= 2 集的動畫
            cursor.execute("""
                SELECT animeSn, COUNT(*) as ep_count, SUM(views) as total_views 
                FROM episode_statistics 
                GROUP BY animeSn
                HAVING COUNT(*) >= 2
                ORDER BY total_views DESC 
                LIMIT 15
            """)
            
            rows2 = cursor.fetchall()
            print("\n✅ 有 >= 2 集的動畫:")
            if not rows2:
                print("❌ 沒有動畫有 >= 2 集的數據")
            else:
                for row in rows2:
                    print(f"animeSn: {row[0]}, episodes: {row[1]}, total_views: {row[2] or 0}")
                    
except Exception as e:
    print(f"❌ 錯誤: {e}")
