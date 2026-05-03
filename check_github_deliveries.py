#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查詢 GitHub Webhook 遞送日誌 (最近 deliveries)"""

import requests
import os
from dotenv import load_dotenv
from pathlib import Path

PROJECT_DIR = Path('/home/e193752468/kkgroup')
load_dotenv(PROJECT_DIR / '.env')

TOKEN = os.getenv('GITHUB_TOKEN')
WEBHOOK_ID = 606339810  # 從前面的查詢得到

if not TOKEN:
    print("❌ GITHUB_TOKEN not found")
    exit(1)

try:
    url = f"https://api.github.com/repos/chenkankan1103/kkgroup/hooks/{WEBHOOK_ID}/deliveries"
    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    print(f"🔍 查詢最近 webhook deliveries (ID: {WEBHOOK_ID})...")
    resp = requests.get(url, headers=headers, timeout=10)
    
    if resp.status_code != 200:
        print(f"❌ API 返回 {resp.status_code}: {resp.text[:100]}")
        exit(1)
    
    deliveries = resp.json()
    print(f"✅ 找到 {len(deliveries)} 筆遞送記錄\n")
    
    for d in deliveries[:10]:  # 只顯示最近 10 筆
        print(f"ID: {d.get('id')}")
        print(f"  Event: {d.get('event')}")
        print(f"  Status: {d.get('status')} | Response Status: {d.get('response', {}).get('status', 'N/A')}")
        print(f"  Timestamp: {d.get('created_at')}")
        if d.get('response', {}).get('body'):
            print(f"  Body: {d['response']['body'][:100]}...")
        print()

except Exception as e:
    print(f"❌ 錯誤: {e}")
    exit(1)
