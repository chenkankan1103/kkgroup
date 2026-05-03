#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 直接更新 GitHub Webhook 端點 URL (緊急修復)
當自動更新失敗時使用
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# 設置路徑
PROJECT_DIR = Path('/home/e193752468/kkgroup')
env_path = PROJECT_DIR / '.env'
config_path = PROJECT_DIR / 'config' / 'config.json'

# 加載環境變量
load_dotenv(env_path)

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', '321qwe321')

if not GITHUB_TOKEN:
    print('❌ GITHUB_TOKEN 未設置')
    sys.exit(1)

# 讀取 config.json 獲取當前隧道 URL
import json
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
        current_url = config.get('url')
        print(f'✅ 讀取 config.json: {current_url}')
except Exception as e:
    print(f'❌ 讀取 config.json 失敗: {e}')
    sys.exit(1)

# 構造完整的 webhook URL
webhook_url = f'{current_url}/webhook/github'

# GitHub API 配置
REPO_OWNER = 'chenkankan1103'
REPO_NAME = 'kkgroup'
API_BASE = 'https://api.github.com'

# 1. 獲取 webhook 列表
print('\n[1/3] 查詢 GitHub webhook 列表...')
url = f'{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/hooks'
headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        print(f'❌ API 失敗: {response.status_code}')
        print(response.text)
        sys.exit(1)
    
    webhooks = response.json()
    print(f'✅ 找到 {len(webhooks)} 個 webhooks')
    
    # 2. 找到目標 webhook
    webhook_id = None
    for hook in webhooks:
        hook_url = hook.get('config', {}).get('url', '')
        if '/webhook/github' in hook_url:
            webhook_id = hook['id']
            print(f'✅ 找到目標 webhook ID: {webhook_id}')
            print(f'   舊 URL: {hook_url}')
            break
    
    if not webhook_id:
        print('❌ 未找到 webhook')
        sys.exit(1)
    
    # 3. 更新 webhook URL
    print(f'\n[2/3] 更新 webhook URL...')
    print(f'   新 URL: {webhook_url}')
    
    update_url = f'{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}'
    payload = {
        'config': {
            'url': webhook_url,
            'content_type': 'json',
            'secret': GITHUB_WEBHOOK_SECRET
        }
    }
    
    response = requests.patch(update_url, json=payload, headers=headers, timeout=10)
    if response.status_code != 200:
        print(f'❌ 更新失敗: {response.status_code}')
        print(response.text)
        sys.exit(1)
    
    print('✅ Webhook URL 已更新')
    
    # 4. 驗證
    print(f'\n[3/3] 驗證更新...')
    response = requests.get(f'{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}', 
                           headers=headers, timeout=10)
    if response.status_code == 200:
        hook = response.json()
        updated_url = hook.get('config', {}).get('url', '')
        if updated_url == webhook_url:
            print(f'✅ 驗證成功: {updated_url}')
        else:
            print(f'⚠️ URL 不匹配: {updated_url} != {webhook_url}')
    
    print('\n✅ 所有操作完成！')

except requests.exceptions.RequestException as e:
    print(f'❌ 請求失敗: {e}')
    sys.exit(1)
except Exception as e:
    print(f'❌ 未知錯誤: {e}')
    sys.exit(1)
