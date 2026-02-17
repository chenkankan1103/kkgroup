#!/usr/bin/env python3
"""Debug: fetch a Discord message JSON for a given channel/message id using .env token (local)."""
import os, sys, json, requests
ENV = os.path.join(os.path.dirname(__file__), '..', '.env')
if not os.path.exists(ENV):
    ENV = os.path.join(os.path.dirname(__file__), '.env')

def get_token():
    try:
        s = open(ENV, encoding='utf-8').read()
    except Exception:
        return os.environ.get('UI_DISCORD_BOT_TOKEN') or os.environ.get('DISCORD_BOT_TOKEN')
    for line in s.splitlines():
        for key in ('UI_DISCORD_BOT_TOKEN','DISCORD_BOT_TOKEN'):
            if line.strip().startswith(key + "="):
                val = line.split('=',1)[1].strip()
                # strip trailing comments and whitespace
                if '#' in val:
                    val = val.split('#',1)[0].strip()
                return val.strip().strip('\"').strip("\'")
    return os.environ.get('UI_DISCORD_BOT_TOKEN') or os.environ.get('DISCORD_BOT_TOKEN')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: debug_fetch_message_local.py <channel_id> <message_id>')
        sys.exit(1)
    channel_id = sys.argv[1]
    message_id = sys.argv[2]
    token = get_token()
    if not token:
        print('No token found')
        sys.exit(1)
    url = f'https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}'
    hdr = {'Authorization': f'Bot {token}', 'User-Agent': 'debug/1.0'}
    r = requests.get(url, headers=hdr, timeout=15)
    print('HTTP', r.status_code)
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    except Exception as e:
        print('Response text:', r.text)
