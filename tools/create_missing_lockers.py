#!/usr/bin/env python3
"""
Create missing canonical locker messages in threads and update users.locker_message_id.

Usage:
  - Place this file in the repository on the production VM and run with the same Python environment the bot uses.
  - Requires bot token present in the repo .env as DISCORD_BOT_TOKEN or UI_DISCORD_BOT_TOKEN.

What it does (safe, idempotent):
  - Finds users with thread_id but no locker_message_id
  - Posts a minimal MapleStory.io-powered embed into the thread
  - Writes the new message id back to users.locker_message_id

Run on the VM as the app user (example):
  sudo -u e193752468 bash -lc "python3 /home/e193752468/kkgroup/tools/create_missing_lockers.py"
"""
import sqlite3
import requests
import json
import re
import os

DB = '/home/e193752468/kkgroup/user_data.db'
ENV = '/home/e193752468/kkgroup/.env'

if not os.path.exists(DB):
    print('DB not found:', DB)
    raise SystemExit(1)
if not os.path.exists(ENV):
    print('.env not found:', ENV)
    raise SystemExit(1)

with open(ENV, encoding='utf-8') as f:
    s = f.read()
    m = re.search(r'^(?:UI_DISCORD_BOT_TOKEN|DISCORD_BOT_TOKEN)\s*=\s*([A-Za-z0-9_.-]+)', s, flags=re.M)
    if not m:
        print('bot token not found in .env')
        raise SystemExit(1)
    token = m.group(1)

HEAD = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('''
SELECT user_id, user_name, face, hair, skin, top, bottom, shoes, thread_id
FROM users
WHERE thread_id IS NOT NULL AND (locker_message_id IS NULL OR locker_message_id = 0)
''')
rows = cur.fetchall()
print('candidates:', len(rows))
for row in rows:
    user_id, user_name, face, hair, skin, top, bottom, shoes, thread_id = row
    user_name = user_name or f'user{user_id}'

    # Build a best-effort MapleStory.io character image URL from available fields
    items = []
    if skin:
        items.append({'itemId': skin, 'region': 'GMS', 'version': '217'})
    if face:
        items.append({'itemId': face, 'region': 'GMS', 'version': '217'})
    if hair:
        items.append({'itemId': hair, 'region': 'GMS', 'version': '217'})

    # fallback defaults if no appearance fields
    if not items:
        items = [
            {'itemId': 12000, 'region': 'GMS', 'version': '217'},
            {'itemId': 20005, 'region': 'GMS', 'version': '217'},
            {'itemId': 30120, 'region': 'GMS', 'version': '217'},
        ]

    for val in (top, bottom, shoes):
        if val:
            items.append({'itemId': val, 'region': 'GMS', 'version': '217'})

    item_path = ','.join([json.dumps(it, separators=(',', ':')) for it in items])
    pose = 'stand1'
    maplestory_url = f'https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true'

    embed = {
        'title': f'📦 {user_name} 的個人置物櫃',
        'description': '自動建立的 canonical locker message（MapleStory.io 圖像）',
        'color': 3066993,
        'image': {'url': maplestory_url},
        'footer': {'text': '由 MapleStory.io 提供角色外觀（自動回填）'}
    }

    url = f'https://discord.com/api/v10/channels/{thread_id}/messages'
    payload = {'embeds': [embed]}
    try:
        r = requests.post(url, headers=HEAD, json=payload, timeout=15)
        print('send', user_id, '->', r.status_code)
        if r.status_code in (200, 201):
            mid = r.json().get('id')
            cur.execute('UPDATE users SET locker_message_id=? WHERE user_id=?', (mid, user_id))
            conn.commit()
            print('updated db', user_id, mid)
        else:
            print('failed send', user_id, r.status_code, r.text[:200])
    except Exception as e:
        print('exception send', user_id, e)

conn.close()
