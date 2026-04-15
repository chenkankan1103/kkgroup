#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在 GCP 上迁移 uibot_anime.db 到 user_data.db
"""

import sqlite3
from pathlib import Path

old_db = Path('/home/e193752468/kkgroup/uibot_anime.db')
new_db = Path('/home/e193752468/kkgroup/user_data.db')

print('🔄 开始迁移动画数据库...')
print(f'   源: {old_db}')
print(f'   目标: {new_db}')
print()

if not old_db.exists():
    print(f'❌ 错误：找不到旧数据库 {old_db}')
    exit(1)

if not new_db.exists():
    print(f'❌ 错误：找不到目标数据库 {new_db}')
    exit(1)

try:
    old_conn = sqlite3.connect(str(old_db))
    new_conn = sqlite3.connect(str(new_db))
    
    old_cursor = old_conn.cursor()
    new_cursor = new_conn.cursor()
    
    # 获取旧数据库中的所有表
    old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    old_tables = [row[0] for row in old_cursor.fetchall()]
    
    print(f'📋 旧数据库中找到的表 ({len(old_tables)}):')
    for table in old_tables:
        print(f'   ✓ {table}')
    print()
    
    # 迁移每个表
    migrated_count = 0
    for table in old_tables:
        print(f'📤 正在迁移表: {table}')
        
        # 获取创建语句
        old_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}';")
        result = old_cursor.fetchone()
        if result:
            create_sql = result[0]
            
            # 尝试在新数据库中创建表
            try:
                new_cursor.execute(create_sql)
                new_conn.commit()
                print(f'   → 创建新表')
            except Exception as e:
                print(f'   → 表已存在或其他: {str(e)[:50]}')
        
        # 获取所有数据
        old_cursor.execute(f'SELECT * FROM {table};')
        rows = old_cursor.fetchall()
        
        if rows:
            # 获取列名
            col_names = [desc[0] for desc in old_cursor.description]
            placeholders = ', '.join(['?' for _ in col_names])
            col_str = ', '.join(col_names)
            insert_sql = f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({placeholders});"
            
            new_cursor.executemany(insert_sql, rows)
            new_conn.commit()
            print(f'   ✓ 迁移了 {len(rows)} 行数据')
            migrated_count += 1
        else:
            print(f'   → 表为空')
        print()
    
    old_conn.close()
    new_conn.close()
    
    print(f'✅ 迁移完成！共迁移 {migrated_count} 个有数据的表')

except Exception as e:
    print(f'❌ 错误: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
