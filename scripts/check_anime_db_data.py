#!/usr/bin/env python3
"""檢查 anime.db 中的資料格式"""
import sqlite3, json

db = sqlite3.connect("user_data.db")

# 0. 列出所有表
print("=== 所有表 ===")
cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
for r in cur.fetchall():
    print(f"  {r[0]}")

# 1. 檢查 notified_anime 表 (或類似名稱)
table_names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
notified_table = [t for t in table_names if 'notified' in t.lower() or 'anime' in t.lower() and 'schedule' not in t.lower()]
print(f"\n=== 可能包含通知記錄的表: {notified_table} ===")
for t in notified_table[:3]:
    try:
        cur = db.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 3")
        cols = [d[0] for d in cur.description]
        print(f"  表 {t} 欄位: {cols}")
        for r in cur.fetchall():
            print(f"    {dict(zip(cols, r))}")
    except Exception as e:
        print(f"  查詢 {t} 失敗: {e}")

# 2. 檢查 anime_details 表
print("\n=== anime_details (最近 5 筆) ===")
try:
    cur = db.execute("SELECT * FROM anime_details ORDER BY animeSn DESC LIMIT 5")
    cols = [d[0] for d in cur.description]
    print(f"  欄位: {cols}")
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        if 'content' in d and d['content']:
            d['content_preview'] = d['content'][:100]
        print(f"    {d}")
except Exception as e:
    print(f"  查詢失敗: {e}")

# 3. 檢查 anime_stats 表
print("\n=== anime_stats (最近 5 筆) ===")
try:
    cur = db.execute("SELECT * FROM anime_stats ORDER BY animeSn DESC LIMIT 5")
    cols = [d[0] for d in cur.description]
    print(f"  欄位: {cols}")
    for r in cur.fetchall():
        print(f"    {dict(zip(cols, r))}")
except Exception as e:
    print(f"  查詢失敗: {e}")

# 4. 檢查 episode_stats 表
print("\n=== episode_stats (最近 5 筆) ===")
try:
    cur = db.execute("SELECT * FROM episode_stats ORDER BY videoSn DESC LIMIT 5")
    cols = [d[0] for d in cur.description]
    print(f"  欄位: {cols}")
    for r in cur.fetchall():
        print(f"    {dict(zip(cols, r))}")
except Exception as e:
    print(f"  查詢失敗: {e}")

db.close()