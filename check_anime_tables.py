#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 user_data.db 中是否有动画表"""

import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "user_data.db"

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# 获取所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("📊 user_data.db 中的所有表:")
print()

anime_tables = [
    "anime_notified",
    "anime_bootstrap", 
    "anime_details",
    "anime_statistics",
    "episode_statistics",
    "anime_votes",
    "anime_rewards"
]

for table_name, in tables:
    is_anime = "🎬" if table_name in anime_tables else "  "
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    count = cursor.fetchone()[0]
    print(f"{is_anime} {table_name:<30} ({count} 行)")

print()
print("🔍 动画相关表的状态:")
for table in anime_tables:
    cursor.execute(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';"
    )
    exists = cursor.fetchone() is not None
    status = "✅ 存在" if exists else "❌ 不存在"
    print(f"   {status} - {table}")

conn.close()
