#!/usr/bin/env python3
"""
清理重複置物櫃 Forum Thread

原因：bot 啟動時 get_thread() 只查快取，archived thread 不在快取內，
誤以為不存在而重新建立，造成同一使用者擁有多條置物櫃 thread。

執行步驟：
1. 掃描 Forum Channel 所有 active + archived threads
2. 以使用者 user_id（從 DB thread_id 比對）找出重複
3. 保留 DB 記錄的 thread_id，刪除其餘重複
4. 若 DB 的 thread_id 不存在（已被刪）則選最新 thread 作為正本

在 GCP VM 上執行：
  cd ~/kkgroup && venv/bin/python3 tools/cleanup_duplicate_lockers.py

加上 --dry-run 只列出重複但不刪除：
  venv/bin/python3 tools/cleanup_duplicate_lockers.py --dry-run
"""

import os
import re
import sys
import json
import sqlite3
import time
import requests
from typing import Optional

# ── 環境設定 ───────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'user_data.db')
ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')

DRY_RUN = '--dry-run' in sys.argv

# ── 讀取 .env ──────────────────────────────────────────────
def load_env(path: str) -> dict:
    env = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                env[key.strip()] = val.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

env = load_env(ENV_PATH)

BOT_TOKEN  = (env.get('UI_DISCORD_BOT_TOKEN')
           or env.get('DISCORD_BOT_TOKEN')
           or env.get('SHOP_DISCORD_BOT_TOKEN')
           or os.getenv('UI_DISCORD_BOT_TOKEN')
           or os.getenv('DISCORD_BOT_TOKEN'))

FORUM_CHANNEL_ID = env.get('FORUM_CHANNEL_ID') or os.getenv('FORUM_CHANNEL_ID')

if not BOT_TOKEN:
    print('❌ 找不到 Bot Token，請確認 .env 中有 UI_DISCORD_BOT_TOKEN')
    sys.exit(1)

if not FORUM_CHANNEL_ID:
    print('❌ 找不到 FORUM_CHANNEL_ID，請確認 .env 中有設定')
    sys.exit(1)

FORUM_CHANNEL_ID = int(FORUM_CHANNEL_ID)
API = 'https://discord.com/api/v10'
HEADERS = {'Authorization': f'Bot {BOT_TOKEN}', 'Content-Type': 'application/json'}


def api_get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    """帶速率限制保護的 GET"""
    while True:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if resp.status_code == 429:
            retry = float(resp.headers.get('Retry-After', '2'))
            print(f'  ⏳ 速率限制，等待 {retry:.1f}s...')
            time.sleep(retry + 0.5)
            continue
        return resp.json() if resp.status_code in (200, 201) else None


def api_delete(url: str) -> bool:
    """帶速率限制保護的 DELETE"""
    while True:
        resp = requests.delete(url, headers=HEADERS, timeout=10)
        if resp.status_code == 429:
            retry = float(resp.headers.get('Retry-After', '2'))
            print(f'  ⏳ 速率限制，等待 {retry:.1f}s...')
            time.sleep(retry + 0.5)
            continue
        if resp.status_code == 204:
            return True
        if resp.status_code == 404:
            return True  # 已被刪，視為成功
        print(f'  ⚠️  DELETE 失敗 {resp.status_code}: {resp.text[:100]}')
        return False


def fetch_all_threads() -> list[dict]:
    """取得 Forum Channel 所有活躍 + 已封存的 thread"""
    threads = []

    # 1. active threads（透過 guild active threads API）
    channel_info = api_get(f'{API}/channels/{FORUM_CHANNEL_ID}')
    if not channel_info:
        print(f'❌ 無法取得頻道資訊 (ID={FORUM_CHANNEL_ID})')
        sys.exit(1)

    guild_id = channel_info.get('guild_id')
    print(f'📡 Guild ID: {guild_id}  |  Forum Channel ID: {FORUM_CHANNEL_ID}')

    active = api_get(f'{API}/guilds/{guild_id}/threads/active')
    if active:
        for t in active.get('threads', []):
            if int(t.get('parent_id', 0)) == FORUM_CHANNEL_ID:
                threads.append(t)
    print(f'  活躍 thread: {len(threads)} 條')

    # 2. archived public threads
    before = None
    page = 0
    while True:
        params = {'limit': 100}
        if before:
            params['before'] = before
        data = api_get(f'{API}/channels/{FORUM_CHANNEL_ID}/threads/archived/public', params=params)
        if not data:
            break
        batch = data.get('threads', [])
        threads.extend(batch)
        page += 1
        if not data.get('has_more', False) or not batch:
            break
        before = batch[-1]['id']
        time.sleep(0.3)

    print(f'  含封存共 {len(threads)} 條 thread')
    return threads


def load_db_thread_ids() -> dict[int, int]:
    """從 DB 讀取 {user_id: thread_id}，只取有 thread_id 的紀錄"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, thread_id FROM users WHERE thread_id IS NOT NULL AND thread_id != 0")
    rows = cur.fetchall()
    conn.close()
    return {int(uid): int(tid) for uid, tid in rows}


def update_db_thread_id(user_id: int, thread_id: int):
    """更新 DB 中的 thread_id"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET thread_id = ? WHERE user_id = ?", (thread_id, user_id))
    conn.commit()
    conn.close()


# ─────────── 主邏輯 ─────────────────────────────────────────
print('='*60)
print('🧹 重複置物櫃 Thread 清理工具')
if DRY_RUN:
    print('ℹ️   dry-run 模式：只列出，不刪除')
print('='*60)

all_threads = fetch_all_threads()
db_map = load_db_thread_ids()  # {user_id: thread_id}

# 把 DB thread_id → user_id 建立反查
db_reverse = {tid: uid for uid, tid in db_map.items()}

# 置物櫃 thread 命名規則：「📦 {名字} 的置物櫃」
LOCKER_PATTERN = re.compile(r'^📦 .+ 的置物櫃$')

# 以名稱分組（名稱相同的 thread → 同一使用者的重複）
by_name: dict[str, list[dict]] = {}
for t in all_threads:
    name = t.get('name', '')
    if LOCKER_PATTERN.match(name):
        by_name.setdefault(name, []).append(t)

duplicates_found = 0
deleted_count = 0

for name, group in by_name.items():
    if len(group) <= 1:
        continue

    duplicates_found += 1
    print(f'\n🔴 重複：「{name}」共 {len(group)} 個 thread')

    # 按建立時間排序（snowflake ID 越大越新）
    group_sorted = sorted(group, key=lambda t: int(t['id']), reverse=True)

    # 決定「正本」：優先選 DB 記錄的 thread_id
    db_thread_id = None
    for t in group_sorted:
        tid = int(t['id'])
        if tid in db_reverse:
            db_thread_id = tid
            break

    if db_thread_id:
        canonical = next(t for t in group_sorted if int(t['id']) == db_thread_id)
    else:
        # DB 沒記這些 thread（可能都是舊的孤立 thread），選最新的
        canonical = group_sorted[0]

    canonical_id = int(canonical['id'])
    print(f'  ✅ 保留 thread_id={canonical_id}  (archived={canonical.get("thread_metadata", {}).get("archived", False)})')

    # 如果 DB 沒指向這個正本，更新 DB
    owner_uid = db_reverse.get(canonical_id)
    if not owner_uid:
        # 嘗試從其他 group member 找 user_id
        for t in group_sorted:
            uid = db_reverse.get(int(t['id']))
            if uid:
                owner_uid = uid
                break

    if owner_uid and db_map.get(owner_uid) != canonical_id:
        if not DRY_RUN:
            update_db_thread_id(owner_uid, canonical_id)
            print(f'  📝 DB 已更新：user_id={owner_uid} → thread_id={canonical_id}')
        else:
            print(f'  📝 [dry-run] 將更新 DB：user_id={owner_uid} → thread_id={canonical_id}')

    # 刪除非正本的重複 thread
    for t in group_sorted:
        tid = int(t['id'])
        if tid == canonical_id:
            continue
        archived = t.get('thread_metadata', {}).get('archived', False)
        print(f'  🗑️  刪除 thread_id={tid}  archived={archived}')
        if not DRY_RUN:
            ok = api_delete(f'{API}/channels/{tid}')
            if ok:
                deleted_count += 1
                print(f'     ✓ 已刪除')
            else:
                print(f'     ✗ 刪除失敗')
            time.sleep(0.5)
        else:
            deleted_count += 1

print('\n' + '='*60)
if duplicates_found == 0:
    print('✅ 沒有發現重複的置物櫃 thread！')
else:
    if DRY_RUN:
        print(f'🔍 發現 {duplicates_found} 個使用者有重複，預計刪除 {deleted_count} 個 thread')
        print('   加上 --dry-run 是模擬模式，實際執行請移除該參數')
    else:
        print(f'✅ 清理完成：共刪除 {deleted_count} 個重複 thread')
print('='*60)
