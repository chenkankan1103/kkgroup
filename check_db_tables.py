#!/usr/bin/env python3
"""
查询 kkgroup.db 数据库中的表
"""
import sqlite3
import os

db_path = "/home/e193752468/kkgroup/kkgroup.db"

try:
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        exit(1)
    
    # 检查文件大小
    size = os.path.getsize(db_path)
    print(f"📁 数据库文件大小: {size} bytes")
    
    if size == 0:
        print("❌ 数据库文件为空（0 字节），AnimeTracker 还未初始化数据库")
        exit(1)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    if not tables:
        print("❌ 数据库中没有表")
    else:
        print(f"✅ 数据库中有 {len(tables)} 个表：")
        for (table_name,) in tables:
            print(f"  - {table_name}")
    
    conn.close()

except Exception as e:
    print(f"❌ 查询失败: {e}")
    import traceback
    traceback.print_exc()
