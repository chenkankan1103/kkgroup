#!/usr/bin/env python3
"""完整驗證：檢查所有置物櫃 embed 是否已移除 image_source field"""
import sqlite3
import requests
import re
import sys
import time

DB = '/home/e193752468/kkgroup/user_data.db'
ENV = '/home/e193752468/kkgroup/.env'

def get_token():
    try:
        s = open(ENV, encoding='utf-8').read()
    except Exception:
        return None
    for key in ('UI_DISCORD_BOT_TOKEN', 'DISCORD_BOT_TOKEN'):
        m = re.search(rf'^{key}\s*=\s*([A-Za-z0-9_\-\.]+)', s, flags=re.M)
        if m:
            return m.group(1).strip()
    return None

token = get_token()
if not token:
    print('ERROR: bot token not found')
    sys.exit(1)

hdr = {'Authorization': f'Bot {token}', 'User-Agent': 'verifier/1.0'}

try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT user_id, thread_id, locker_message_id FROM users WHERE locker_message_id IS NOT NULL AND locker_message_id<>0"
    ).fetchall()
    conn.close()
except Exception as e:
    print(f"DB error: {e}")
    sys.exit(1)

print(f"TOTAL LOCKERS={len(rows)}")
print("-" * 60)

ok = 0  # 已更新（無 image_source field，有 image URL）
no_image_source_no_image = 0  # 已更新但沒圖片（異常）
has_image_source = 0  # 未更新（仍有 image_source field）
errors = 0

for i, (user_id, thread_id, msg_id) in enumerate(rows, 1):
    url = f'https://discord.com/api/v10/channels/{thread_id}/messages/{msg_id}'
    try:
        r = requests.get(url, headers=hdr, timeout=10)
        if r.status_code == 429:
            retry_after = float(r.headers.get('Retry-After', 1))
            time.sleep(retry_after + 0.1)
            r = requests.get(url, headers=hdr, timeout=10)
        
        if r.status_code != 200:
            errors += 1
            continue
        
        msg = r.json()
        embeds = msg.get('embeds', [])
        if not embeds:
            errors += 1
            continue
        
        embed = embeds[0]
        fields = embed.get('fields', [])
        
        # 檢查 image_source field
        has_src_field = any(f.get('name') == 'image_source' for f in fields)
        has_image = embed.get('image') is not None
        
        if has_src_field:
            has_image_source += 1
        elif has_image:
            ok += 1
        else:
            no_image_source_no_image += 1
        
        if i % 50 == 0:
            print(f"Progress: {i}/{len(rows)}")
        
        time.sleep(0.05)
        
    except Exception as e:
        errors += 1

print("-" * 60)
print(f"✅ 已更新（無 image_source field）: {ok}")
print(f"⚠️ 已更新但無圖片: {no_image_source_no_image}")
print(f"❌ 未更新（仍有 image_source field）: {has_image_source}")
print(f"⚠️ 驗證錯誤: {errors}")
print("-" * 60)
if has_image_source == 0 and errors == 0:
    print("✅ 所有置物櫃都已成功更新！")
else:
    print("⚠️ 有些置物櫃還需要更新")
