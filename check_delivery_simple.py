#!/usr/bin/env python3
import requests, os, json
from dotenv import load_dotenv
load_dotenv('/home/e193752468/kkgroup/.env')
token = os.getenv('GITHUB_TOKEN')
url = 'https://api.github.com/repos/chenkankan1103/kkgroup/hooks/606339810/deliveries'
headers = {'Authorization': f'token {token}'}
resp = requests.get(url, headers=headers, timeout=10).json()
print('最近 3 筆 webhook 遞送:')
for i, d in enumerate(resp[:3], 1):
    status = d.get('status', 'UNKNOWN')
    resp_status = d.get('response', {}).get('status', 'N/A')
    created = d.get('created_at', 'N/A')
    print(f"{i}. Status={status} RespCode={resp_status} Time={created}")
