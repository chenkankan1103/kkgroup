#!/usr/bin/env python3
"""
Force all locker message embeds to use MapleStory.io API image URL.
- Reads DB for users with `locker_message_id`
- Builds MapleStory API URL from stored user fields
- PATCHes message.embeds[0].image -> API URL (preserve components)
- Writes `embed_image_source` = API URL into users table

Run on the production VM as the app user:
  sudo -u e193752468 bash -lc "python3 /home/e193752468/kkgroup/tools/force_set_api_image_embeds.py"
"""
import os, re, sqlite3, requests, json, time
DB='/home/e193752468/kkgroup/user_data.db'
ENV='/home/e193752468/kkgroup/.env'

# copy of logic from image_utils.build_maplestory_api_url
def build_maplestory_api_url(user_data: dict, animated: bool = True) -> str:
    items = [
        {"itemId": 2000, "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('skin', 12000), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('face', 20005), "animationName": "default", "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('hair', 30120), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('top', 1040014), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('bottom', 1060096), "region": "TWMS", "version": "256"},
        {"itemId": user_data.get('shoes', 1072005), "region": "TWMS", "version": "256"}
    ]
    if user_data.get('is_stunned', 0) == 1:
        items.append({"itemId": 1005411, "region": "TWMS", "version": "256"})
    item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
    pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
    if animated:
        return f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"
    return f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"

# load token from repo .env
with open(ENV, 'r', encoding='utf-8') as f:
    env = f.read()
m = re.search(r"UI_DISCORD_BOT_TOKEN\s*=\s*([A-Za-z0-9_\-\.]+)", env)
if not m:
    print('Bot token not found in .env')
    raise SystemExit(1)
TOKEN = m.group(1)
HEADERS = {'Authorization': f'Bot {TOKEN}', 'User-Agent': 'kkgroup-force-api-image/1.0', 'Content-Type': 'application/json'}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
rows = cur.execute("SELECT user_id, thread_id, locker_message_id, face, hair, skin, top, bottom, shoes, is_stunned FROM users WHERE locker_message_id IS NOT NULL AND locker_message_id<>0").fetchall()
print('found', len(rows), 'users with locker_message_id')
fixed = 0
skipped = 0
failed = 0

for r in rows:
    user_id = r['user_id']
    thread_id = r['thread_id']
    msg_id = r['locker_message_id']
    if not thread_id or not msg_id:
        skipped += 1
        continue

    user_data = {k: r[k] for k in ['face','hair','skin','top','bottom','shoes','is_stunned']}
    api_url = build_maplestory_api_url(user_data, animated=True)

    url = f'https://discord.com/api/v10/channels/{thread_id}/messages/{msg_id}'
    try:
        gr = requests.get(url, headers=HEADERS, timeout=10)
    except Exception as ex:
        print('GET failed', user_id, ex)
        failed += 1
        continue

    if gr.status_code != 200:
        print('GET non-200', user_id, gr.status_code)
        skipped += 1
        continue

    msg = gr.json()
    embeds = msg.get('embeds') or []
    if not embeds:
        # message doesn't contain an embed we expect to update — skip
        print('no embed to update for', user_id)
        skipped += 1
        continue

    e = embeds[0]
    # overwrite/set image to MapleStory API URL
    e['image'] = {'url': api_url}

    components = msg.get('components') or []
    payload = {'embeds': [e], 'components': components}
    try:
        pr = requests.patch(url, headers=HEADERS, json=payload, timeout=10)
        if pr.status_code == 200:
            # persist embed_image_source in DB
            try:
                cur.execute('UPDATE users SET embed_image_source=? WHERE user_id=?', (api_url, user_id))
                conn.commit()
            except Exception:
                pass
            print('set API image for user', user_id)
            fixed += 1
        else:
            print('patch failed', user_id, pr.status_code, pr.text[:200])
            failed += 1
    except Exception as ex:
        print('patch exception', user_id, ex)
        failed += 1

    # small throttle
    time.sleep(0.25)

print('done fixed=', fixed, 'skipped=', skipped, 'failed=', failed)
conn.close()
