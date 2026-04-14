#!/usr/bin/env python3
"""快速檢查幾個置物櫃 embed 是否已移除 image_source field"""
import sqlite3
import requests
import re
import sys

DB='/home/e193752468/kkgroup/user_data.db'
ENV='/home/e193752468/kkgroup/.env'

def get_token():
    try:
        s = open(ENV, encoding='utf-8').read()
    except Exception:
        return None
    for key in ('UI_DISCORD_BOT_TOKEN', 'DISCORD_BOT_TOKEN', 'SHOP_DISCORD_BOT_TOKEN'):
        m = re.search(rf'^{key}\s*=\s*([A-Za-z0-9_\-\.]+)', s, flags=re.M)
        if m:
            return m.group(1).strip()
    return None

token = get_token()
if not token:
    print('❌ bot token not found')
    sys.exit(1)

hdr = {'Authorization': f'Bot {token}', 'User-Agent': 'kkgroup-checker/1.0'}

try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT user_id, thread_id, locker_message_id FROM users WHERE locker_message_id IS NOT NULL LIMIT 5"
    ).fetchall()
    conn.close()
except Exception as e:
    print(f"❌ DB error: {e}")
    sys.exit(1)

print(f"📊 檢查 {len(rows)} 個置物櫃...\n")

has_image_source = 0
no_image_source = 0

for i, (user_id, thread_id, msg_id) in enumerate(rows, 1):
    url = f'https://discord.com/api/v10/channels/{thread_id}/messages/{msg_id}'
    try:
        r = requests.get(url, headers=hdr, timeout=10)
        if r.status_code != 200:
            print(f"{i}. user_id={user_id}: ❌ HTTP {r.status_code}")
            continue
        
        msg = r.json()
        embeds = msg.get('embeds', [])
        if not embeds:
            print(f"{i}. user_id={user_id}: ⚠️ no embeds")
            continue
        
        embed = embeds[0]
        fields = embed.get('fields', [])
        
        # 檢查是否有 image_source field
        has_src_field = any(f.get('name') == 'image_source' for f in fields)
        has_image = embed.get('image') is not None
        
        if has_src_field:
            has_image_source += 1
            src_val = next((f.get('value', '')[:50] for f in fields if f.get('name') == 'image_source'), '???')
            print(f"{i}. user_id={user_id}: ❌ 有 image_source field: {src_val}...")
        else:
            no_image_source += 1
            img_url = (embed.get('image', {}).get('url', '') if has_image else 'N/A')[:60]
            print(f"{i}. user_id={user_id}: ✅ 無 image_source field, 圖片={('有' if has_image else '無')} {img_url}...")
        
    except Exception as e:
        print(f"{i}. user_id={user_id}: ⚠️ {type(e).__name__}")

print(f"\n📈 摘要：has_image_source={has_image_source}, no_image_source={no_image_source}")
