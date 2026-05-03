#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""檢查 GitHub Webhook 當前配置"""

import os
import requests
from dotenv import load_dotenv
from pathlib import Path

# 加載 .env
load_dotenv(Path(__file__).parent / '.env')

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_OWNER = 'chenkankan1103'
REPO_NAME = 'kkgroup'

if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN 未設置")
    exit(1)

url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks"
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code != 200:
        print(f"❌ API 返回 {response.status_code}")
        print(response.text)
        exit(1)
    
    webhooks = response.json()
    print(f"✅ 找到 {len(webhooks)} 個 webhooks\n")
    
    for i, hook in enumerate(webhooks, 1):
        print(f"[{i}] ID: {hook['id']}")
        hook_url = hook.get('config', {}).get('url', 'N/A')
        print(f"    URL: {hook_url}")
        print(f"    Event: {', '.join(hook.get('events', []))}")
        print(f"    Active: {hook.get('active', False)}")
        print()

except Exception as e:
    print(f"❌ 錯誤: {e}")
    exit(1)
