#!/usr/bin/env python
"""快速檢查置物櫃數據庫的 user_id"""
import sqlite3
from pathlib import Path

db_path = './shop_commands/merchant/cannabis.db'

if not Path(db_path).exists():
    print(f"❌ {db_path} 不存在")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 檢查 cannabis_plants
print("=== Cannabis Plants ===")
c.execute('SELECT COUNT(*) FROM cannabis_plants')
print(f"總植物數: {c.fetchone()[0]}")

c.execute('SELECT MIN(user_id), MAX(user_id), COUNT(DISTINCT user_id) FROM cannabis_plants')
result = c.fetchone()
print(f"最小ID: {result[0]}, 最大ID: {result[1]}, 不同用戶: {result[2]}")

c.execute('SELECT user_id, COUNT(*) FROM cannabis_plants GROUP BY user_id LIMIT 10')
print("\n用戶ID及其植物數:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}株")

# 檢查 cannabis_inventory
print("\n=== Cannabis Inventory ===")
c.execute('SELECT COUNT(*) FROM cannabis_inventory')
print(f"總項目數: {c.fetchone()[0]}")

c.execute('SELECT MIN(user_id), MAX(user_id), COUNT(DISTINCT user_id) FROM cannabis_inventory')
result = c.fetchone()
print(f"最小ID: {result[0]}, 最大ID: {result[1]}, 不同用戶: {result[2]}")

c.execute('SELECT user_id, COUNT(*) FROM cannabis_inventory GROUP BY user_id LIMIT 10')
print("\n用戶ID及其庫存項目")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}項")

conn.close()

print("\n✅ 診斷完成")
