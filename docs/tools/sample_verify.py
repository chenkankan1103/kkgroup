#!/usr/bin/env python3
"""驗證置物櫃 embed 是否已更新（無 image_source field）"""
import sqlite3, requests, re, sys, time, os, random

DB = '/home/e193752468/kkgroup/user_data.db'
ENV_PATH = '/home/e193752468/kkgroup/.env'

# 提取 token
def get_token_from_env():
    try:
        with open(ENV_PATH) as f:
            content = f.read()
        for line in content.split('\n'):
            for key in ('UI_DISCORD_BOT_TOKEN', 'DISCORD_BOT_TOKEN'):
                if key in line and '=' in line:
                    val = line.split('=')[1].strip().strip('"').strip("'")
                    if val and len(val) > 20:
                        return val
    except:
        pass
    return None

token = get_token_from_env()
if not token:
    print('⚠️ Token not found, trying env var...')
    token = os.environ.get('UI_DISCORD_BOT_TOKEN') or os.environ.get('DISCORD_BOT_TOKEN')
    if not token:
        print('❌ No token found')
        sys.exit(1)

hdr = {'Authorization': f'Bot {token}', 'User-Agent': 'sampler/1.0'}

# 讀 DB
try:
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT user_id, thread_id, locker_message_id FROM users WHERE locker_message_id IS NOT NULL"
    ).fetchall()
    conn.close()
except Exception as e:
    print(f'❌ DB error: {e}')
    sys.exit(1)

print(f'📊 採樣 {min(50, len(rows))} 個置物櫃...')
sample = random.sample(rows, min(50, len(rows)))

ok_count = 0
fail_count = 0

for i, (uid, tid, mid) in enumerate(sample, 1):
    try:
        r = requests.get(
            f'https://discord.com/api/v10/channels/{tid}/messages/{mid}',
            headers=hdr, timeout=10
        )
        if r.status_code != 200:
            fail_count += 1
            continue
        
        msg = r.json()
        if not msg.get('embeds'):
            fail_count += 1
            continue
        
        # 檢查是否有 image_source field
        has_src = any(f.get('name') == 'image_source' for f in msg['embeds'][0].get('fields', []))
        
        if has_src:
            print(f'{i}. ❌ user_id={uid}: still has image_source field')
            fail_count += 1
        else:
            ok_count += 1
            if i <= 10 or i % 10 == 0:
                print(f'{i}. ✅ user_id={uid}: updated')
        
        time.sleep(0.05)
    except Exception as e:
        fail_count += 1

print(f'\n結果：✅ {ok_count} 個已更新，❌ {fail_count} 個異常')
print('Done!')
