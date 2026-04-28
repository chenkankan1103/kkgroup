#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import requests

# 獲取 Swagger 文檔
swagger_url = 'https://maplestory.io/swagger/V3/swagger.json'
try:
    response = requests.get(swagger_url, timeout=10)
    swagger_doc = response.json()
    
    # 提取所有 paths
    paths = swagger_doc.get('paths', {})
    
    print('=== MapleStory API V3 所有 Character 相關端點 ===\n', flush=True)
    
    character_endpoints = {k: v for k, v in paths.items() if 'character' in k.lower()}
    
    for endpoint, methods in sorted(character_endpoints.items()):
        print(f'{endpoint}', flush=True)
        for method in methods:
            if method in ['get', 'post', 'put', 'delete']:
                print(f'  → {method.upper()}', flush=True)
        print()
    
except Exception as e:
    print(f'Error: {str(e)[:200]}', flush=True)
