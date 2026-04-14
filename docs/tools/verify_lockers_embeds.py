#!/usr/bin/env python3
import sqlite3, re, requests, time, json, sys
DB='/home/e193752468/kkgroup/user_data.db'
ENV='/home/e193752468/kkgroup/.env'


def get_token():
    try:
        s = open(ENV, encoding='utf-8').read()
    except Exception:
        return None
    # match token value only (ignore inline comments or trailing text)
    for key in ('UI_DISCORD_BOT_TOKEN', 'DISCORD_BOT_TOKEN', 'SHOP_DISCORD_BOT_TOKEN'):
        m = re.search(rf'^{key}\s*=\s*([A-Za-z0-9_\-\.]+)', s, flags=re.M)
        if m:
            return m.group(1).strip()
    return None


token=get_token()
if not token:
    print('ERROR: bot token not found in', ENV)
    sys.exit(1)
# debug: show which token key was picked (prefix only)
try:
    print('TOKEN_PREFIX=', token[:8])
except Exception:
    pass
hdr={'Authorization':f'Bot {token}', 'User-Agent':'kkgroup-verifier/1.0'}

conn=sqlite3.connect(DB)
cur=conn.cursor()
rows=cur.execute("SELECT user_id, thread_id, locker_message_id FROM users WHERE locker_message_id IS NOT NULL AND locker_message_id<>0").fetchall()
total=len(rows)
print(f"TOTAL={total}")
counts={'ok':0,'missing_embed':0,'no_image':0,'no_footer':0,'title_mismatch':0,'fetch_error':0}
status_counts = {}
issues=[]
MAX_DISPLAY=30

for user_id, thread_id, msg_id in rows:
    url=f'https://discord.com/api/v10/channels/{thread_id}/messages/{msg_id}'
    try:
        r=requests.get(url, headers=hdr, timeout=10)
    except Exception as e:
        counts['fetch_error']+=1
        issues.append({'user_id':user_id,'thread_id':thread_id,'message_id':msg_id,'error_type': e.__class__.__name__, 'error': repr(e)})
        time.sleep(0.15)
        continue

    if r.status_code==429:
        try:
            j=r.json()
            ra=j.get('retry_after', 1)
            time.sleep(max(1, float(ra)))
        except Exception:
            time.sleep(2)
        r=requests.get(url, headers=hdr, timeout=10)

    if r.status_code!=200:
        counts['fetch_error']+=1
        status_counts[r.status_code] = status_counts.get(r.status_code, 0) + 1
        issues.append({'user_id':user_id,'thread_id':thread_id,'message_id':msg_id,'status':r.status_code})
        time.sleep(0.15)
        continue

    j=r.json()
    embeds=j.get('embeds') or []
    if not embeds:
        counts['missing_embed']+=1
        issues.append({'user_id':user_id,'thread_id':thread_id,'message_id':msg_id,'reason':'missing_embed'})
        time.sleep(0.15)
        continue

    e=embeds[0]
    title=(e.get('title') or '').strip()
    image_url=(e.get('image') or {}).get('url') or ''
    footer_text=(e.get('footer') or {}).get('text') or ''
    ok_title = ('置物櫃' in title) or ('個人置物櫃' in title) or title.startswith('📦')
    ok_image = bool(image_url)
    ok_footer = ('MapleStory.io' in footer_text) or ('MapleStory' in footer_text)
    if not ok_title:
        counts['title_mismatch']+=1
    if not ok_image:
        counts['no_image']+=1
    if not ok_footer:
        counts['no_footer']+=1
    if ok_title and ok_image:
        counts['ok']+=1
    else:
        reason=[]
        if not ok_title: reason.append('bad_title')
        if not ok_image: reason.append('no_image')
        if not ok_footer: reason.append('no_footer')
        # only store minimal, ASCII-safe failure info
        issues.append({'user_id':user_id,'thread_id':thread_id,'message_id':msg_id,'reasons':reason})

summary={'summary':counts,'status_counts': status_counts, 'total':total,'issues_count':len(issues)}
print(json.dumps(summary))
# print a short readable list of failures (ASCII-safe)
for i,iss in enumerate(issues[:MAX_DISPLAY]):
    print(f"{i+1}. user={iss.get('user_id')} thread={iss.get('thread_id')} msg={iss.get('message_id')} reasons={iss.get('reasons')}")

# list any HTTP-status errors (e.g. 404)
for iss in issues:
    if iss.get('status'):
        print(f"HTTP_ERROR: user={iss.get('user_id')} thread={iss.get('thread_id')} msg={iss.get('message_id')} status={iss.get('status')}")

# if there were fetch exceptions, show sample exception types/messages (escaped)
err_shown = 0
for iss in issues:
    if iss.get('error') and err_shown < 10:
        et = iss.get('error_type') or '<unknown>'
        err_msg = iss.get('error')
        safe = err_msg.encode('ascii', 'backslashreplace').decode()
        print(f'ERROR_SAMPLE: type={et} msg={safe[:300]}')
        err_shown += 1

print('DONE')
