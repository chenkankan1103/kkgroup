#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将旧的 uibot_anime.db 中的所有表迁移到 user_data.db
"""

import sqlite3
from pathlib import Path

# 数据库路径
old_db = Path(__file__).parent / "cogs" / "uibot_anime.db"
new_db = Path(__file__).parent / "user_data.db"

print(f"🔄 开始迁移动画数据库...")
print(f"   源: {old_db}")
print(f"   目标: {new_db}")
print()

if not old_db.exists():
    print(f"❌ 错误：找不到旧数据库 {old_db}")
    exit(1)

if not new_db.exists():
    print(f"❌ 错误：找不到目标数据库 {new_db}")
    exit(1)

try:
    # 连接两个数据库
    old_conn = sqlite3.connect(str(old_db))
    new_conn = sqlite3.connect(str(new_db))
    
    old_cursor = old_conn.cursor()
    new_cursor = new_conn.cursor()
    
    # 获取旧数据库中的所有表
    old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    old_tables = [row[0] for row in old_cursor.fetchall()]
    
    print(f"📋 旧数据库中找到的表 ({len(old_tables)}):")
    for table in old_tables:
        print(f"   ✓ {table}")
    print()
    
    # 获取新数据库中的所有表
    new_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    new_tables = [row[0] for row in new_cursor.fetchall()]
    
    print(f"📋 新数据库中现有的表 ({len(new_tables)}):")
    for table in new_tables:
        print(f"   • {table}")
    print()
    
    # 迁移每个表
    migrated_count = 0
    for table in old_tables:
        print(f"📤 正在迁移表: {table}")
        
        # 获取创建语句
        old_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}';")
        create_sql = old_cursor.fetchone()[0]
        
        if table not in new_tables:
            # 表不存在，创建新表
            print(f"   → 创建新表...")
            new_cursor.execute(create_sql)
            new_conn.commit()
        else:
            print(f"   → 表已存在，跳过创建")
        
        # 获取所有数据
        old_cursor.execute(f"SELECT * FROM {table};")
        columns_cursor = old_cursor.description
        column_names = [desc[0] for desc in columns_cursor]
        rows = old_cursor.fetchall()
        
        if rows:
            placeholders = ", ".join(["?" for _ in column_names])
            insert_sql = f"INSERT OR IGNORE INTO {table} ({', '.join(column_names)}) VALUES ({placeholders});"
            
            new_cursor.executemany(insert_sql, rows)
            new_conn.commit()
            print(f"   ✓ 迁移了 {len(rows)} 行数据")
            migrated_count += 1
        else:
            print(f"   → 表为空，无数据迁移")
        print()
    
    # 关闭连接
    old_conn.close()
    new_conn.close()
    
    print(f"✅ 迁移完成！")
    print(f"   - 迁移了 {migrated_count} 个表")
    print(f"   - 新数据库已更新: {new_db}")

except Exception as e:
    print(f"❌ 迁移失败: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
