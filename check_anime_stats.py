#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 anime_tracker 数据库中的统计数据"""

import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "uibot_anime.db"

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 1. 检查 episode_statistics 表中的数据
    print("=" * 60)
    print("📊 Episode Statistics 总数据")
    print("=" * 60)
    cursor.execute("SELECT COUNT(*) FROM episode_statistics")
    total_episodes = cursor.fetchone()[0]
    print(f"总记录数: {total_episodes}")
    
    if total_episodes > 0:
        # 2. 按动画分组统计
        print("\n" + "=" * 60)
        print("🎬 按动画分组统计（前 10 部）")
        print("=" * 60)
        cursor.execute("""
            SELECT 
                animeSn, 
                COUNT(*) as episodes,
                SUM(views) as total_views,
                AVG(views) as avg_views,
                AVG(score) as avg_score
            FROM episode_statistics
            GROUP BY animeSn
            ORDER BY total_views DESC
            LIMIT 10
        """)
        
        headers = ["animeSn", "Episodes", "Total Views", "Avg Views", "Avg Score"]
        print(f"{headers[0]:<10} {headers[1]:<10} {headers[2]:<15} {headers[3]:<15} {headers[4]:<12}")
        print("-" * 60)
        
        for row in cursor.fetchall():
            anime_sn, episodes, total_views, avg_views, avg_score = row
            print(f"{anime_sn:<10} {episodes:<10} {total_views or 0:<15} {avg_views or 0:<15.0f} {avg_score or 0:<12.1f}")
    else:
        print("\n⚠️ 暂无数据。等待动画推送后数据会被自动记录。")
    
    # 3. 查一些具体的数据样本
    print("\n" + "=" * 60)
    print("📋 最新 5 条记录（原始数据）")
    print("=" * 60)
    cursor.execute("""
        SELECT videoSn, animeSn, episode_num, views, score, recorded_at
        FROM episode_statistics
        ORDER BY recorded_at DESC
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        print(f"VideoSn: {row[0]}, AnimeSn: {row[1]}, Episode: {row[2]}")
        print(f"  Views: {row[3]}, Score: {row[4]}, Time: {row[5]}")
        print()
    
    conn.close()
    
except Exception as e:
    print(f"❌ 错误: {e}")
