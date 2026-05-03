#!/usr/bin/env python3
"""查詢 GitHub webhook 配置"""
import requests
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / '.env')

TOKEN = os.getenv('GITHUB_TOKEN')
if not TOKEN:
    print("❌ GITHUB_TOKEN not found")
    exit(1)

try:
    url = "https://api.github.com/repos/chenkankan1103/kkgroup/hooks"
    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    print(f"🔍 查詢 GitHub webhook (Token: {TOKEN[:20]}...)")
    resp = requests.get(url, headers=headers, timeout=10)
    
    if resp.status_code == 401:
        print(f"❌ 認證失敗 (401)")
        print(f"   Response: {resp.text}")
        exit(1)
    
    if resp.status_code != 200:
        print(f"❌ API 返回 {resp.status_code}")
        print(resp.text)
        exit(1)
    
    webhooks = resp.json()
    print(f"✅ 找到 {len(webhooks)} 個 webhooks\n")
    
    for hook in webhooks:
        print(f"ID: {hook['id']}")
        print(f"URL: {hook['config']['url']}")
        print(f"Active: {hook['active']}")
        print(f"Events: {', '.join(hook['events'])}")
        print()

except Exception as e:
    print(f"❌ 錯誤: {e}")
    exit(1)
